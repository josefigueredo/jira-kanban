from __future__ import annotations

import re
import unittest

from helpers import CONVENTIONS, FakeJira, make_project
from jkan import preview, spec, sync
from test_jira import client

SPEC = {"epic": {"summary": "e"}, "items": [
    {"type": "task", "summary": "Repo", "started": True, "subtasks": [{"summary": "Crear el repo"}]},
    {"type": "task", "summary": "Hecha", "done": True},
    {"type": "task", "summary": "Abierta"}]}


class StartedSpecTest(unittest.TestCase):
    def test_started_is_carried_and_subtasks_do_not_inherit_it(self):
        ops = {op["ref"]: op for op in spec.plan(SPEC, CONVENTIONS)}
        self.assertTrue(ops["items[0]"]["started"])
        self.assertFalse(ops["items[0].subtasks[0]"]["started"])
        self.assertFalse(ops["items[2]"]["started"])

    def test_started_and_done_together_or_not_bool_are_findings(self):
        bad = {"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "x", "started": True, "done": True},
                                                    {"type": "task", "summary": "y", "started": "yes"}]}
        findings = spec.validate(bad, CONVENTIONS)
        self.assertIn("items[0]: started and done exclude each other", findings)
        self.assertIn("items[1]: started must be true or false", findings)


class StartedCreateTest(unittest.TestCase):
    def test_started_items_go_in_progress_and_are_assigned_without_asking(self):
        ops = spec.plan(SPEC, CONVENTIONS)
        self.assertEqual(sync.assignment(ops, None), 3)  # epic, the subtask and the open task still ask
        self.assertEqual({op["ref"]: op["assignee"] for op in ops}["items[0]"], "me-started")

        jira = FakeJira()
        result = sync.create(jira, make_project(), SPEC, CONVENTIONS, apply=True, assign_open=False)
        repo = result["keys"]["items[0]"]
        self.assertEqual(jira.issues[repo]["category"], "in_progress")
        self.assertEqual(jira.issues[repo]["assignee"], "acc-me")
        self.assertEqual(jira.issues[result["keys"]["items[0].subtasks[0]"]]["category"], "todo")
        self.assertEqual(jira.issues[result["keys"]["items[1]"]]["category"], "done")


class StartTransitionTest(unittest.TestCase):
    def test_start_prefers_a_working_status_over_review_or_blocked(self):
        transitions = {"transitions": [
            {"id": "5", "to": {"name": "Blocked", "statusCategory": {"key": "indeterminate"}}},
            {"id": "6", "to": {"name": "Review", "statusCategory": {"key": "indeterminate"}}},
            {"id": "7", "to": {"name": "PROCESANDO", "statusCategory": {"key": "indeterminate"}}},
            {"id": "8", "to": {"name": "Done", "statusCategory": {"key": "done"}}}]}
        jira, rec = client({("GET", "/rest/api/3/issue/PLATE-1/transitions"): transitions,
                            ("POST", "/rest/api/3/issue/PLATE-1/transitions"): {}})
        self.assertEqual(jira.transition_start("PLATE-1", ["Blocked"]), "PROCESANDO")
        self.assertEqual(rec.calls[-1][2], {"transition": {"id": "7"}})

    def test_start_without_an_in_progress_transition_returns_none(self):
        transitions = {"transitions": [{"id": "8", "to": {"name": "Done", "statusCategory": {"key": "done"}}}]}
        jira, _ = client({("GET", "/rest/api/3/issue/PLATE-1/transitions"): transitions})
        self.assertIsNone(jira.transition_start("PLATE-1", []))


class StartedPreviewTest(unittest.TestCase):
    def test_preview_shows_the_status_each_issue_will_end_in(self):
        ops = spec.plan(SPEC, CONVENTIONS)
        sync.assignment(ops, None)
        html = preview.render(ops, CONVENTIONS)
        page = lambda n: re.search(rf'id="NUEVO-{n}".*?</section>', html, re.S).group(0)  # noqa: E731
        self.assertIn('class="status">En progreso', page(2))
        self.assertIn('class="status">Backlog', page(3))
        self.assertIn('class="status">Done', page(4))
        self.assertIn("Vos · en curso", page(2))


if __name__ == "__main__":
    unittest.main()
