from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, FakeJira, issue
from jkan import standup

EPIC = {"key": "PLATE-100", "summary": "Épica", "issuetype": "Epic"}
TASK = {"key": "PLATE-102", "summary": "T", "issuetype": "Tarea"}


def shape(tree):
    return [(n["issue"]["key"], n["context"], shape(n["children"])) for n in tree]


class DoneTreeTest(unittest.TestCase):
    def test_a_subtask_reaches_its_epic_through_a_parent_that_did_not_change(self):
        story = issue("PLATE-101", category="done", changed="2026-10-07", parent=EPIC)
        parent_task = issue("PLATE-102", parent=EPIC)
        sub = issue("PLATE-103", issuetype="Subtarea", category="done", changed="2026-10-06", parent=TASK)
        loose = issue("PLATE-104", category="in_progress", changed="2026-10-07")
        tree = standup.done_tree([story, sub, loose], {"PLATE-102": parent_task}, "Epic")
        self.assertEqual(shape(tree), [
            ("PLATE-100", True, [("PLATE-101", False, []), ("PLATE-102", True, [("PLATE-103", False, [])])]),
            ("", True, [("PLATE-104", False, [])])])
        self.assertEqual(tree[1]["issue"]["summary"], "Sin épica")

    def test_children_are_ordered_by_issue_number_not_by_text(self):
        a = issue("PLATE-1000", parent=EPIC, category="done", changed="2026-10-07")
        b = issue("PLATE-999", parent=EPIC, category="done", changed="2026-10-07")
        self.assertEqual([c["issue"]["key"] for c in standup.done_tree([a, b], {}, "Epic")[0]["children"]],
                         ["PLATE-999", "PLATE-1000"])

    def test_a_closed_epic_is_not_context(self):
        epic = issue("PLATE-100", issuetype="Epic", category="done", changed="2026-10-07")
        story = issue("PLATE-101", parent=EPIC, category="done", changed="2026-10-07")
        self.assertEqual(shape(standup.done_tree([epic, story], {}, "Epic")),
                         [("PLATE-100", False, [("PLATE-101", False, [])])])

    def test_an_unreachable_parent_does_not_loop_or_crash(self):
        orphan = issue("PLATE-5", parent={"key": "PLATE-4", "summary": "", "issuetype": "Tarea"}, category="done")
        self.assertEqual(shape(standup.done_tree([orphan], {}, "Epic")),
                         [("", True, [("PLATE-4", True, [("PLATE-5", False, [])])])])


class GatherDoneTest(unittest.TestCase):
    def test_counts_exclude_epics_and_the_missing_parent_is_fetched_once(self):
        sub = issue("PLATE-103", issuetype="Subtarea", category="done", changed="2026-10-06", parent=TASK)
        story = issue("PLATE-101", category="done", changed="2026-10-07", parent=EPIC)
        wip = issue("PLATE-105", category="in_progress", changed="2026-10-07", parent=EPIC)
        epic = issue("PLATE-100", issuetype="Epic", category="in_progress", changed="2026-10-07")
        parent_task = issue("PLATE-102", parent=EPIC)
        jira = FakeJira()
        jira.search_answer = lambda jql: [parent_task] if jql.startswith("key in") else [sub, story, wip, epic]
        result = standup.gather_done(jira, None, date(2026, 10, 1), date(2026, 10, 7), CONVENTIONS)
        self.assertEqual((result["done"], result["in_progress"]), (2, 1))
        self.assertEqual(jira.jqls[1], "key in (PLATE-102)")
        self.assertEqual(len(jira.jqls), 2)

    def test_a_subtask_of_any_type_name_still_reaches_the_epic(self):
        sub = issue("PLATE-103", issuetype="Sub-task", category="done", changed="2026-10-06", parent=TASK)
        parent_task = issue("PLATE-102", parent=EPIC)
        jira = FakeJira()
        jira.search_answer = lambda jql: [parent_task] if jql.startswith("key in") else [sub]
        result = standup.gather_done(jira, None, date(2026, 10, 1), date(2026, 10, 7), CONVENTIONS)
        self.assertEqual(shape(result["tree"]), [("PLATE-100", True, [("PLATE-102", True, [("PLATE-103", False, [])])])])

    def test_empty_window(self):
        jira = FakeJira()
        result = standup.gather_done(jira, None, date(2026, 10, 1), date(2026, 10, 7), CONVENTIONS)
        self.assertEqual(result, {"done": 0, "dropped": 0, "in_progress": 0, "tree": []})
        self.assertEqual(len(jira.jqls), 1)


if __name__ == "__main__":
    unittest.main()
