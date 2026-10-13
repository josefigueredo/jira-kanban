from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import make_project, state_dir
from jkan import cli, journal, state


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TeeTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.project = make_project()

    def test_a_write_goes_to_the_project_log_as_before_and_to_the_common_one(self):
        write = journal.journal(self.project, "create", now=lambda: "T1", also=state.log_write)
        write({"action": "update", "key": "PLATE-1", "fields": {"summary": "x"}})
        self.assertEqual(lines(self.project / ".jira-team-kit" / "jira-writes.jsonl"),
                         [{"ts": "T1", "tool": "jtk", "command": "create", "action": "update",
                           "key": "PLATE-1", "fields": {"summary": "x"}}])
        [common] = lines(self.base / "writes.jsonl")
        self.assertEqual((common["tool"], common["command"], common["action"], common["key"], common["result"]),
                         ("jtk", "create", "update", "PLATE-1", "ok"))
        self.assertIn("ts", common)

    def test_the_common_line_has_no_plan_so_it_never_counts_as_an_applied_plan(self):
        journal.journal(self.project, "push", also=state.log_write)({"action": "update", "key": "PLATE-1", "fields": {}})
        [common] = lines(self.base / "writes.jsonl")
        self.assertNotIn("plan", common)
        self.assertEqual(state.applied("abcdef123456"), set())
        self.assertEqual(state.applied(""), set())

    def test_without_a_tee_nothing_goes_to_the_common_log(self):
        journal.journal(self.project, "push")({"action": "update", "key": "PLATE-1", "fields": {}})
        self.assertFalse((self.base / "writes.jsonl").exists())

    def test_a_tee_that_raises_never_breaks_the_write(self):
        def broken(entry):
            raise RuntimeError("boom")

        journal.journal(self.project, "push", also=broken)({"action": "update", "key": "PLATE-1", "fields": {}})
        self.assertEqual(len(lines(self.project / ".jira-team-kit" / "jira-writes.jsonl")), 1)

    def test_a_state_folder_that_cannot_be_written_never_breaks_the_write(self):
        (self.base / "writes.jsonl").mkdir()  # a directory where the file should be
        journal.journal(self.project, "push", also=state.log_write)({"action": "update", "key": "PLATE-1", "fields": {}})
        self.assertEqual(len(lines(self.project / ".jira-team-kit" / "jira-writes.jsonl")), 1)


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.project = make_project()

    def journal_of(self, command):
        with mock.patch.object(cli.config, "credentials", return_value=("https://x.atlassian.net", "e@x", "t")), \
                mock.patch.object(cli, "Jira") as jira:
            cli._client(self.project, command)
        return jira.call_args.kwargs["journal"]

    def test_the_legacy_commands_write_to_both_logs(self):
        self.journal_of("assign")({"action": "assign", "key": "PLATE-2", "accountId": "acc-ana"})
        self.assertEqual(len(lines(self.project / ".jira-team-kit" / "jira-writes.jsonl")), 1)
        [common] = lines(self.base / "writes.jsonl")
        self.assertEqual((common["command"], common["key"], common["accountId"]), ("assign", "PLATE-2", "acc-ana"))

    def test_plan_and_apply_pass_no_journal_so_their_lines_are_not_written_twice(self):
        self.assertIsNone(self.journal_of(None))


if __name__ == "__main__":
    unittest.main()
