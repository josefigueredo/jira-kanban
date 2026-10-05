from __future__ import annotations

import unittest

from helpers import CONVENTIONS, FakeJira, epic_with_children, make_project
from jkan import kanban, sync
from test_cli import run


def set_status(jira, key, status, category, flagged=False):
    jira.issues[key].update(status=status, category=category, flagged=flagged)


class CategoryTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        set_status(self.jira, "PLATE-601", "PROCESANDO", "in_progress")
        set_status(self.jira, "PLATE-602", "Blocked", "in_progress")
        set_status(self.jira, "PLATE-603", "Done", "done")
        sync.pull(self.jira, self.project, self.key, CONVENTIONS)
        self.epic = kanban.epic_dir(self.project, self.key)

    def front(self, rel):
        return kanban.parse((self.epic / rel).read_text(encoding="utf-8"))

    def test_pull_records_category_and_blocked(self):
        self.assertEqual((self.front("stories/PLATE-601/story.md")["category"],
                          self.front("stories/PLATE-601/story.md")["blocked"]), ("in_progress", "false"))
        self.assertEqual(self.front("stories/PLATE-601/subtasks/PLATE-602/subtask.md")["blocked"], "true")
        self.assertEqual(self.front("tasks/PLATE-603/task.md")["category"], "done")

    def test_flagged_counts_as_blocked_whatever_the_status(self):
        set_status(self.jira, "PLATE-601", "Review", "in_progress", flagged=True)
        sync.pull(self.jira, self.project, self.key, CONVENTIONS)
        self.assertEqual(self.front("stories/PLATE-601/story.md")["blocked"], "true")

    def test_board_groups_by_category_with_blocked_first(self):
        board = sync.board(self.project, self.key, CONVENTIONS)
        self.assertEqual([g["name"] for g in board["groups"]], ["blocked", "todo", "in_progress", "done"])
        counts = {g["name"]: g["count"] for g in board["groups"]}
        self.assertEqual(counts, {"blocked": 1, "todo": 0, "in_progress": 1, "done": 1})
        self.assertEqual(board["total"], 3)          # the epic is the frame, not a card
        self.assertEqual(board["done_pct"], 33)
        blocked = next(g for g in board["groups"] if g["name"] == "blocked")
        self.assertEqual(blocked["statuses"], {"Blocked": 1})

    def test_board_cli_reads_only_the_local_kanban(self):
        code, out, _ = run(["board", self.key, "--project", str(self.project)], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("Bloqueado 1", out)
        self.assertIn("En progreso 1", out)
        self.assertIn("Hecho 1 · 33%", out)
        self.assertIn("PROCESANDO", out)
        self.assertEqual(self.jira.writes, [])


if __name__ == "__main__":
    unittest.main()
