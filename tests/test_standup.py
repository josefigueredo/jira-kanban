from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, FakeJira, issue
from jkan import standup

TODAY, UNTIL = date(2026, 10, 8), date(2026, 10, 10)
EPIC = {"key": "PLATE-100", "summary": "Épica", "issuetype": "Epic"}


class BlockedTest(unittest.TestCase):
    def test_a_link_beats_a_flag_and_a_flag_beats_a_status(self):
        open_issues = [
            issue("PLATE-1", flagged=True),
            issue("PLATE-2", status="Blocked", category="in_progress"),
            issue("PLATE-3", blocked_by=[
                {"key": "PLATE-8", "summary": "Okta", "status": "En curso", "category": "in_progress", "assignee": "Ana"},
                {"key": "PLATE-9", "summary": "Ya está", "status": "Done", "category": "done", "assignee": "Beto"}]),
            issue("PLATE-4", flagged=True, category="done"),
            issue("PLATE-5"),
        ]
        rows = standup.blocked_rows(open_issues, CONVENTIONS)
        self.assertEqual([(r["issue"]["key"], r["by"], r["owner"]) for r in rows], [
            ("PLATE-1", "Flagged, sin link", ""),
            ("PLATE-2", "Estado Blocked, sin link", ""),
            ("PLATE-3", "PLATE-8", "Ana")])

    def test_a_blocker_nobody_owns_says_so(self):
        row = standup.blocked_rows([issue("PLATE-3", blocked_by=[
            {"key": "PLATE-8", "summary": "", "status": "", "category": "", "assignee": ""}])], CONVENTIONS)[0]
        self.assertEqual(row["owner"], "sin dueño")


class NextTest(unittest.TestCase):
    OPEN = [
        issue("PLATE-1", priority="Low", duedate="2026-10-09"),
        issue("PLATE-2", priority="High"),
        issue("PLATE-3", priority="High", duedate="2026-10-05"),
        issue("PLATE-4", priority="Highest", flagged=True),
        issue("PLATE-5", priority="Medium", status="Blocked", category="in_progress", duedate="2026-10-10"),
        issue("PLATE-6", priority=""),
    ]

    def test_ready_is_ordered_by_priority_then_due_date_and_leaves_blocked_out(self):
        tables = standup.next_tables(self.OPEN, [], TODAY, UNTIL, CONVENTIONS)
        self.assertEqual([i["key"] for i in tables["ready"]], ["PLATE-3", "PLATE-2", "PLATE-1", "PLATE-6"])

    def test_due_lists_the_window_marking_overdue_and_blocked(self):
        tables = standup.next_tables(self.OPEN, [], TODAY, UNTIL, CONVENTIONS)
        self.assertEqual([(r["issue"]["key"], r["overdue"], r["blocked"]) for r in tables["due"]], [
            ("PLATE-3", True, False), ("PLATE-1", False, False), ("PLATE-5", False, True)])

    def test_unowned_is_sorted_by_priority(self):
        tables = standup.next_tables([], [issue("PLATE-7", priority="Low", assignee=None),
                                          issue("PLATE-8", priority="High", assignee=None)], TODAY, UNTIL, CONVENTIONS)
        self.assertEqual([i["key"] for i in tables["unowned"]], ["PLATE-8", "PLATE-7"])

    def test_epic_keys_come_from_parents_and_owned_epics(self):
        keys = standup.epic_keys([issue("PLATE-1", parent=EPIC), issue("PLATE-2", parent={**EPIC, "key": "PLATE-9", "issuetype": "Tarea"})],
                                 [issue("PLATE-101", issuetype="Epic")], "Epic")
        self.assertEqual(keys, ["PLATE-100", "PLATE-101"])


class GatherTest(unittest.TestCase):
    def test_gather_next_asks_for_unowned_work_in_the_epics_it_found(self):
        jira = FakeJira()
        mine = [issue("PLATE-1", parent=EPIC), issue("PLATE-101", issuetype="Epic", summary="Mi épica")]
        jira.search_answer = lambda jql: [issue("PLATE-7", assignee=None)] if jql.startswith("parent in") else mine
        tables = standup.gather_next(jira, None, UNTIL, TODAY, CONVENTIONS)
        self.assertEqual([i["key"] for i in tables["ready"]], ["PLATE-1"])  # the epic is a container, not work
        self.assertEqual([i["key"] for i in tables["unowned"]], ["PLATE-7"])
        self.assertTrue(jira.jqls[1].startswith("parent in (PLATE-100, PLATE-101)"))

    def test_gather_next_skips_the_unowned_query_when_there_are_no_epics(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1")]
        standup.gather_next(jira, None, UNTIL, TODAY, CONVENTIONS)
        self.assertEqual(len(jira.jqls), 1)

    def test_gather_blocked_ignores_epics(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", flagged=True), issue("PLATE-2", issuetype="Epic", flagged=True)]
        rows = standup.gather_blocked(jira, "acc-ana", CONVENTIONS)
        self.assertEqual([r["issue"]["key"] for r in rows], ["PLATE-1"])
        self.assertIn('assignee = "acc-ana"', jira.jqls[0])


if __name__ == "__main__":
    unittest.main()
