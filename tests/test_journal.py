"""Every write jtk makes to Jira is kept in ./.jira-team-kit/jira-writes.jsonl, in the same shape as WayOfWork's log.

With one Jira token shared by several tools and by hand, Jira's changelog cannot say which tool made a change. A log
of this skill's own successful writes at least lets a change be ruled in or out as jtk's.
"""
from __future__ import annotations

import json
import unittest

from helpers import make_project
from jkan import journal
from jkan.jira import Jira
from test_jira import FakeResponse


def Response(payload):
    return FakeResponse(json.dumps(payload).encode())


class ClientJournalTest(unittest.TestCase):
    def test_writes_are_journaled_and_reads_are_not(self):
        seen = []

        def opener(request, timeout):
            if request.get_method() == "POST" and request.full_url.endswith("/issue"):
                return Response({"key": "PLATE-700"})
            if request.get_method() == "GET":
                return Response({"transitions": [{"id": "31", "to": {"name": "Done",
                                                                       "statusCategory": {"key": "done"}}}]})
            return Response({})

        jira = Jira("https://acme.atlassian.net", "dev@acme.io", "tok-SECRET-1", opener=opener, journal=seen.append)
        jira.create({"summary": "Ver el tablero", "issuetype": {"name": "Tarea"}})
        jira.update("PLATE-700", {"summary": "Ver el tablero nuevo"})
        jira.transition_done("PLATE-700")
        self.assertEqual(seen, [
            {"action": "create", "key": "PLATE-700", "fields": {"summary": "Ver el tablero", "issuetype": {"name": "Tarea"}}},
            {"action": "update", "key": "PLATE-700", "fields": {"summary": "Ver el tablero nuevo"}},
            {"action": "transition", "key": "PLATE-700", "to": "Done"}])


class JournalFileTest(unittest.TestCase):
    def test_entries_append_with_time_tool_and_command(self):
        project = make_project()
        write = journal.journal(project, "create", now=lambda: "2026-10-05T12:00:00Z")
        write({"action": "transition", "key": "PLATE-700", "to": "Done"})
        [line] = (project / ".jira-team-kit" / "jira-writes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(line), {"ts": "2026-10-05T12:00:00Z", "tool": "jira-kanban", "command": "create",
                                            "action": "transition", "key": "PLATE-700", "to": "Done"})

    def test_a_journal_that_cannot_write_never_breaks_the_command(self):
        project = make_project()
        (project / ".jira-team-kit").write_text("not a directory", encoding="utf-8")
        journal.journal(project, "push")({"action": "update", "key": "PLATE-700", "fields": {}})


if __name__ == "__main__":
    unittest.main()
