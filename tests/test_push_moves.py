from __future__ import annotations

import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import kanban, sync
from test_cli import run


def set_status(path, status):
    text = path.read_text(encoding="utf-8")
    path.write_text("\n".join(f"status: {status}" if ln.startswith("status:") else ln for ln in text.split("\n")),
                    encoding="utf-8")


class PushMovesTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.epic = epic_with_children(self.jira)  # PLATE-601 story > PLATE-602 subtask; PLATE-603 task
        sync.pull(self.jira, self.project, self.epic)
        self.root = kanban.epic_dir(self.project, self.epic)

    def test_a_parent_closes_after_its_subtasks(self):
        set_status(self.root / "stories/PLATE-601/story.md", "Done")
        set_status(self.root / "stories/PLATE-601/subtasks/PLATE-602/subtask.md", "Done")
        result = sync.push(self.jira, self.project, self.epic, apply=True)
        self.assertEqual(result["errors"], [])
        self.assertEqual([w[1] for w in self.jira.writes if w[0] == "transition"], ["PLATE-602", "PLATE-601"])

    def test_a_rejected_move_is_reported_and_the_others_still_go(self):
        self.jira.refuse_moves = {"PLATE-602": "none"}
        set_status(self.root / "stories/PLATE-601/subtasks/PLATE-602/subtask.md", "Done")
        set_status(self.root / "stories/PLATE-601/story.md", "Done")
        set_status(self.root / "tasks/PLATE-603/task.md", "Done")
        result = sync.push(self.jira, self.project, self.epic, apply=True)
        self.assertEqual(self.jira.issues["PLATE-603"]["status"], "Done")
        self.assertEqual(len(result["errors"]), 2)
        self.assertIn("PLATE-602: no transition to 'Done'", result["errors"])
        self.assertTrue(any(e.startswith("PLATE-601:") and "open sub-tasks" in e for e in result["errors"]))

    def test_cli_exits_1_and_names_the_failed_moves(self):
        self.jira.refuse_moves = {"PLATE-603": "raise"}
        set_status(self.root / "tasks/PLATE-603/task.md", "Done")
        code, _, err = run(["push", self.epic, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("PLATE-603", err + _)


if __name__ == "__main__":
    unittest.main()
