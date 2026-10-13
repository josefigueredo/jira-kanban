from __future__ import annotations

import json
import unittest

from helpers import CONVENTIONS, FakeJira, described, make_project
from jkan import sync
from test_cli import run

# Creation order: epic PLATE-600, Hecha 601, its subtask 602, En curso 603, Otra hecha 604.
SPEC = described({"epic": {"summary": "e"}, "items": [
    {"type": "task", "summary": "Hecha", "done": True, "evidence": ["https://example.com/pr/1"], "subtasks": [{"summary": "hija"}]},
    {"type": "task", "summary": "En curso", "started": True},
    {"type": "task", "summary": "Otra hecha", "done": True, "evidence": ["https://example.com/pr/1"]}]})


class TransitionFailureTest(unittest.TestCase):
    def test_a_rejected_move_does_not_stop_the_others_and_the_kanban_is_written(self):
        jira, project = FakeJira(refuse_moves={"PLATE-602": "raise", "PLATE-603": "none"}), make_project()
        result = sync.create(jira, project, SPEC, CONVENTIONS, apply=True, assign_open=True)
        self.assertEqual(jira.issues["PLATE-601"]["category"], "done")  # its parent still moves
        self.assertEqual(jira.issues["PLATE-604"]["category"], "done")
        self.assertEqual(jira.issues["PLATE-602"]["category"], "todo")
        self.assertEqual(jira.issues["PLATE-603"]["category"], "todo")
        self.assertEqual([e["key"] for e in result["errors"]], ["PLATE-602", "PLATE-603"])
        self.assertIn("HTTP 400", result["errors"][0]["reason"])
        self.assertEqual(result["errors"][1], {"key": "PLATE-603", "to": "in progress",
                                               "reason": "no transition into that category"})
        self.assertTrue((project / ".jira-team-kit" / "PLATE-600" / "epic.md").is_file())
        self.assertEqual(list((project / ".jira-team-kit").glob(".create-progress-*.json")), [])

    def test_cli_reports_the_failed_moves_and_how_to_finish_them_with_push(self):
        jira, project = FakeJira(refuse_moves={"PLATE-604": "raise"}), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps(SPEC), encoding="utf-8")
        code, out, err = run(["create", "--spec", str(path), "--project", str(project), "--jira-project", "PLATE",
                              "--apply", "--assign-open"], jira)
        self.assertEqual(code, 1)
        self.assertIn("created PLATE-600", out)
        self.assertIn("PLATE-604: not moved to Done (HTTP 400 on transition of PLATE-604)", err)
        self.assertIn("jtk push PLATE-600", err)
        self.assertIn("do not run create again", err)


if __name__ == "__main__":
    unittest.main()
