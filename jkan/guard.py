"""The one gate every write to Jira passes through: a person at a real terminal types «APRUEBO <n>».

The script enforces it, not the model's discipline: with no terminal it writes nothing and prints the command for the
person to run in their own window. The answer is read from /dev/tty (never stdin), once, and must match exactly. There
is no flag, environment variable or config that skips it; tests replace it only through cli.main(confirm=...)."""
from __future__ import annotations

import sys
from typing import Callable, Optional, Sequence

from . import approval

APPROVAL = "APRUEBO"
EXIT_NEEDS_PERSON = 3


class NotApproved(Exception):
    """Nothing was written: there is no terminal, or the person did not type the approval."""


def _is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


class _Tty:
    """/dev/tty as two handles, one to read and one to write: a single read-write text handle on a terminal fails with
    «File or stream is not seekable», which made every approval at a real terminal come out as «none is attached»."""

    def __init__(self):
        self._reader = open("/dev/tty", "r", encoding="utf-8")
        try:
            self._writer = open("/dev/tty", "w", encoding="utf-8")
        except OSError:
            self._reader.close()
            raise

    def write(self, text):
        self._writer.write(text)

    def flush(self):
        self._writer.flush()

    def readline(self):
        return self._reader.readline()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._reader.close()
        self._writer.close()
        return False


def _open_tty():
    return _Tty()


def _needs_terminal(command: str) -> str:
    return ("this write needs a person at an interactive terminal and none is attached; nothing was written.\n"
            f"Run it yourself in a terminal window:\n  {command}")


def _default_dialog():
    return approval.DialogApprover()


def _via_window(n: int, summary: str, command: str, dialog) -> None:
    """No terminal: a person clicks «Apruebo <n>» in a native window. Without a window there is nothing to ask."""
    dialog = dialog if dialog is not None else _default_dialog()
    if not dialog.available():
        raise NotApproved(_needs_terminal(command))
    if not dialog.approve(summary, n):
        raise NotApproved("not approved in the window (cancelled, closed or timed out); nothing was written. "
                          "Do not run it again unless the person asks.")


def confirm(n: int, summary: str, command: str, streams: Optional[Sequence] = None,
            open_tty: Optional[Callable] = None, dialog=None) -> None:
    """Return when a person approved `n` writes; raise NotApproved otherwise. `streams`, `open_tty` and `dialog` exist
    for tests; none of them skips the approval."""
    if n < 1:
        raise ValueError("there is nothing to approve")
    streams = streams if streams is not None else (sys.stdin, sys.stdout, sys.stderr)
    if not all(_is_tty(s) for s in streams):
        return _via_window(n, summary, command, dialog)
    try:
        tty = (open_tty or _open_tty)()
    except OSError:
        return _via_window(n, summary, command, dialog)
    with tty:
        tty.write(f"{summary}\n\nType {APPROVAL} {n} to write {n} change(s) to Jira; anything else cancels: ")
        tty.flush()
        answer = tty.readline().rstrip("\r\n")
    if answer != f"{APPROVAL} {n}":
        raise NotApproved(f"not approved (expected exactly «{APPROVAL} {n}»); nothing was written.")
