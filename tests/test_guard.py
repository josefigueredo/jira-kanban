from __future__ import annotations

import inspect
import os
import pty
import unittest

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import guard


class Tty:
    """A stand-in for /dev/tty: it answers one line and remembers what it was shown."""

    def __init__(self, answer):
        self.answer, self.shown = answer, []

    def write(self, text):
        self.shown.append(text)

    def flush(self):
        pass

    def readline(self):
        return self.answer + "\n"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Stream:
    """stdin/stdout/stderr: reading from it is a bug, because the approval comes from /dev/tty."""

    def __init__(self, tty=True):
        self.tty = tty

    def isatty(self):
        return self.tty

    def readline(self):
        raise AssertionError("the approval must not be read from stdin")


REAL = (Stream(), Stream(), Stream())


def ask(n, answer, streams=REAL):
    tty = Tty(answer)
    guard.confirm(n, "THE SUMMARY", "jtk apply abc", streams=streams, open_tty=lambda: tty)
    return tty


class ApprovalTest(unittest.TestCase):
    def test_the_exact_phrase_with_the_right_number_approves_and_the_person_sees_the_summary(self):
        tty = ask(3, "APRUEBO 3")
        shown = "".join(tty.shown)
        self.assertIn("THE SUMMARY", shown)
        self.assertIn("APRUEBO 3", shown)

    def test_anything_else_is_not_an_approval(self):
        for answer in ("APRUEBO 2", "APRUEBO 4", "aprueba 3", "apruebo 3", "APRUEBO 3 ", " APRUEBO 3", "APRUEBO  3",
                       "APRUEBO 03", "APRUEBO", "si", "yes", ""):
            with self.assertRaisesRegex(guard.NotApproved, "nothing was written", msg=repr(answer)):
                ask(3, answer)

    def test_it_never_reads_stdin(self):
        ask(1, "APRUEBO 1")  # Stream.readline raises if it is touched

    def test_nothing_to_approve_is_a_bug_of_the_caller(self):
        with self.assertRaises(ValueError):
            ask(0, "APRUEBO 0")


class TerminalTest(unittest.TestCase):
    def test_every_standard_stream_must_be_a_terminal(self):
        for streams in ((Stream(False), Stream(), Stream()), (Stream(), Stream(False), Stream()),
                        (Stream(), Stream(), Stream(False))):
            opened = []
            with self.assertRaisesRegex(guard.NotApproved, "Run it yourself"):
                guard.confirm(2, "S", "jtk apply abc", streams=streams, open_tty=lambda: opened.append(1))
            self.assertEqual(opened, [])

    def test_the_refusal_prints_the_exact_command_to_run(self):
        with self.assertRaises(guard.NotApproved) as caught:
            guard.confirm(2, "S", "jtk apply abc123", streams=(Stream(False),) * 3)
        self.assertIn("  jtk apply abc123", str(caught.exception))
        self.assertIn("nothing was written", str(caught.exception))

    def test_a_stream_that_cannot_say_if_it_is_a_terminal_counts_as_not_one(self):
        with self.assertRaises(guard.NotApproved):
            guard.confirm(1, "S", "jtk apply abc", streams=(object(), Stream(), Stream()))

    def test_without_dev_tty_it_refuses(self):
        def no_tty():
            raise OSError("Device not configured")

        with self.assertRaisesRegex(guard.NotApproved, "Run it yourself"):
            guard.confirm(1, "S", "jtk apply abc", streams=REAL, open_tty=no_tty)


class RealTerminalTest(unittest.TestCase):
    """The fakes above never touch /dev/tty. This runs the real guard in a child that has a real terminal (a pty), the
    way a person's window has one: opening /dev/tty read-write in text mode used to fail with «not seekable»."""

    def run_in_terminal(self, typed: str) -> int:
        pid, fd = pty.fork()
        if pid == 0:
            code = 99
            try:
                guard.confirm(1, "SUMMARY", "the command")
                code = 0
            except guard.NotApproved:
                code = 2
            except BaseException:
                code = 1
            os._exit(code)
        os.write(fd, typed.encode())
        while True:  # drain what the terminal echoes: a child cannot exit while its output is unread
            try:
                if not os.read(fd, 1024):
                    break
            except OSError:
                break
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        return os.WEXITSTATUS(status)

    def test_a_person_at_a_real_terminal_can_approve(self):
        self.assertEqual(self.run_in_terminal("APRUEBO 1\n"), 0)

    def test_a_real_terminal_with_a_wrong_answer_does_not_approve(self):
        self.assertEqual(self.run_in_terminal("no\n"), 2)


class NoBypassTest(unittest.TestCase):
    def test_the_only_knobs_are_the_streams_and_the_tty_opener_for_tests(self):
        names = list(inspect.signature(guard.confirm).parameters)
        self.assertEqual(names, ["n", "summary", "command", "streams", "open_tty"])

    def test_no_environment_variable_skips_it(self):
        saved = dict(os.environ)
        try:
            for name in ("JTK_YES", "JTK_APPROVE", "YES", "CI", "FORCE", "JTK_ASSUME_YES"):
                os.environ[name] = "1"
            with self.assertRaises(guard.NotApproved):
                guard.confirm(1, "S", "jtk apply abc", streams=(Stream(False),) * 3)
        finally:
            os.environ.clear()
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main()
