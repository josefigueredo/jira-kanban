from __future__ import annotations

import unittest

from helpers import make_project
from jkan import kanban

ISSUE = {"key": "PLATE-601", "kind": "story", "issuetype": "Story (migrated)", "status": "Backlog",
         "summary": "[FE] Ver el tablero", "parent": "PLATE-600", "description": "Como analista quiero algo\n\n- AC1: x",
         "url": "https://example.atlassian.net/browse/PLATE-601"}


class FormatTest(unittest.TestCase):
    def test_render_and_parse_round_trip(self):
        text = kanban.render(ISSUE)
        self.assertTrue(text.startswith("---\nkey: PLATE-601\nkind: story\n"))
        self.assertIn("\n# [FE] Ver el tablero\n", text)
        parsed = kanban.parse(text)
        for field in ("key", "kind", "issuetype", "status", "summary", "parent", "description", "url"):
            self.assertEqual(parsed[field], ISSUE[field], field)

    def test_the_card_comes_from_the_issue_template_byte_for_byte(self):
        # Same bytes as before the template existed, so a pull never rewrites the cards already on disk.
        full = dict(ISSUE, category="todo", blocked="false", summary="[FE] Ver", description="Como x\n\n- AC1: y")
        self.assertEqual(kanban.render(full),
                         "---\nkey: PLATE-601\nkind: story\nissuetype: Story (migrated)\nstatus: Backlog\ncategory: todo\n"
                         "blocked: false\nparent: PLATE-600\nurl: https://example.atlassian.net/browse/PLATE-601\n---\n\n"
                         "# [FE] Ver\n\nComo x\n\n- AC1: y\n")
        bare = dict(full, parent="", description="")
        self.assertTrue(kanban.render(bare).endswith("parent: \nurl: https://example.atlassian.net/browse/PLATE-601\n"
                                                     "---\n\n# [FE] Ver\n"))

    def test_the_writer_uses_the_shipped_template(self):
        from unittest import mock
        from jkan import template
        self.assertEqual(set(template.placeholders(template.load("issue.md"))),
                         set(kanban.FRONT) | {"summary", "description"})
        shipped = template.load("issue.md")
        with mock.patch.object(template, "load", lambda name: shipped.replace("# {{summary}}", "## {{summary}}")):
            self.assertIn("\n## [FE] Ver el tablero\n", kanban.render(ISSUE))

    def test_no_sync_time_in_the_file_and_old_files_still_parse(self):
        text = kanban.render(ISSUE)
        self.assertNotIn("synced", text)
        old = text.replace("url: ", "synced: 2026-10-05T19:00:00Z\nurl: ", 1)
        self.assertEqual(kanban.parse(old)["key"], "PLATE-601")

    def test_title_edited_in_the_heading_wins(self):
        text = kanban.render(ISSUE).replace("# [FE] Ver el tablero", "# [FE] Ver el tablero nuevo")
        self.assertEqual(kanban.parse(text)["summary"], "[FE] Ver el tablero nuevo")


class LayoutTest(unittest.TestCase):
    def test_paths_follow_jira_levels(self):
        project = make_project()
        epic = kanban.epic_dir(project, "PLATE-600")
        self.assertEqual(epic, project / ".jira-team-kit" / "PLATE-600")
        self.assertEqual(kanban.item_file(epic, "story", "PLATE-601"), epic / "stories" / "PLATE-601" / "story.md")
        self.assertEqual(kanban.item_file(epic, "task", "PLATE-603"), epic / "tasks" / "PLATE-603" / "task.md")
        parent = kanban.item_file(epic, "story", "PLATE-601").parent
        self.assertEqual(kanban.subtask_file(parent, "PLATE-602"), parent / "subtasks" / "PLATE-602" / "subtask.md")


if __name__ == "__main__":
    unittest.main()
