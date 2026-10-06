"""A description edited in the local kanban goes back to Jira only if it still follows templates/description.md.

Only what changed is checked: a card mirrored from Jira with free text can still move or be renamed.
"""
from __future__ import annotations

import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import description, sync
from test_cli import run

GOOD = description.render({"why": "Nada corre los tests.", "what": "CI con gate.", "done_when": "Un PR rojo no entra."})


class PushCheckTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        sync.pull(self.jira, self.project, self.key)
        self.epic = self.project / ".jira-kanban" / self.key
        self.task = self.epic / "tasks/PLATE-603/task.md"

    def set_description(self, path, text):
        head = path.read_text(encoding="utf-8").split("\n# ", 1)
        title = head[1].split("\n", 1)[0]
        path.write_text(f"{head[0]}\n# {title}\n\n{text}\n", encoding="utf-8")

    def test_an_edited_description_that_breaks_the_template_is_not_sent(self):
        self.set_description(self.task, "Por qué: x\n\nQué: y")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("invalid PLATE-603 description: missing: Hecho cuando (see templates/description.md)", out)
        self.assertEqual(self.jira.issues["PLATE-603"]["description"], "CI")

    def test_an_edited_description_that_follows_it_is_sent(self):
        self.set_description(self.task, GOOD)
        code, _, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(self.jira.issues["PLATE-603"]["description"], GOOD)

    def test_a_free_text_card_can_still_change_status_and_title(self):
        text = self.task.read_text(encoding="utf-8")
        self.task.write_text(text.replace("status: Backlog", "status: Done").replace("# [DEVOPS] Pipeline", "# [DEVOPS] CI"),
                             encoding="utf-8")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.jira.issues["PLATE-603"]["summary"], "[DEVOPS] CI")

    def test_a_new_subtask_with_a_placeholder_left_is_not_created(self):
        new = self.epic / "tasks/PLATE-603/subtasks/_new-gate/subtask.md"
        new.parent.mkdir(parents=True)
        new.write_text("# Gate de cobertura\n\nPor qué: {{why}}\n\nQué: un gate.\n\nHecho cuando: falla bajo 80%.\n",
                       encoding="utf-8")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply", "--assign-open"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("invalid _new-gate description: not filled in: Por qué (see templates/description.md)", out)
        self.assertFalse(any(w[0] == "create" and w[2]["summary"] == "Gate de cobertura" for w in self.jira.writes))
        self.assertTrue(new.is_file())

    def test_a_new_subtask_that_follows_the_template_is_created(self):
        new = self.epic / "tasks/PLATE-603/subtasks/_new-gate/subtask.md"
        new.parent.mkdir(parents=True)
        new.write_text(f"# Gate de cobertura\n\n{GOOD}\n", encoding="utf-8")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply", "--assign-open"], self.jira)
        self.assertEqual(code, 0, out)
        self.assertTrue(any(w[0] == "create" and w[2]["description"] == GOOD for w in self.jira.writes))


if __name__ == "__main__":
    unittest.main()
