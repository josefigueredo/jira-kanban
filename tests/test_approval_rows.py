"""The approval window must never hide what a person approves: a long value cannot push the rest off a 520 pt window.

A new subtask used to be listed under its local file path as the «key» chip (145 characters on a real kanban), which
overflowed the window and pushed the title, the action and the footer out of sight."""
from __future__ import annotations

import re
import unittest

from helpers import CONVENTIONS, FakeJira, epic_with_children, make_project
from jkan import approval, sync
from test_legacy_guard import Asked, run as run_guarded

NEW = "# Gate de cobertura\n\nPor qué: Nada mide la cobertura.\n\nQué: Un gate de cobertura en CI.\n\nHecho cuando: Falla bajo 80%.\n"
LONG = "/Users/someone/CurrentCode/ITTICLOUD/Harness/idp-component/.jira-team-kit/PLATE-697/tasks/PLATE-700/subtasks/_new-x/subtask.md"


def rule(css, selector):
    """The declarations of the first CSS rule that starts with `selector` followed by « {»-less `{`."""
    found = re.search(r"(?:^|\n|\})" + re.escape(selector) + r"\{([^}]*)\}", css)
    return found.group(1) if found else ""


class NewSubtaskRowTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        sync.pull(self.jira, self.project, self.key)
        new = self.project / ".jira-team-kit" / self.key / "tasks/PLATE-603/subtasks/_new-gate/subtask.md"
        new.parent.mkdir(parents=True)
        new.write_text(NEW, encoding="utf-8")

    def window_rows(self):
        asked = Asked()
        run_guarded(["push", self.key, "--project", str(self.project), "--apply", "--assign-open"], self.jira, asked)
        return asked.calls[0][1].rows

    def test_a_new_subtask_is_never_listed_under_a_file_path(self):
        [row] = [r for r in self.window_rows() if r[1] == "Gate de cobertura"]
        self.assertNotIn("/", row[0])
        self.assertLessEqual(len(row[0]), 20)

    def test_a_new_subtask_row_says_its_type_and_under_which_issue_it_is_created(self):
        [row] = [r for r in self.window_rows() if r[1] == "Gate de cobertura"]
        self.assertEqual(row[0], CONVENTIONS["issue_types"]["subtask"])
        self.assertIn("PLATE-603", row[2])


class LongValueTest(unittest.TestCase):
    CSS = approval.render_html(approval.Summary("T", "h", [("A-1", "t", "c")]), 1).split("</style>")[0]

    def test_a_long_key_wraps_instead_of_stretching_the_card(self):
        self.assertIn("overflow-wrap:anywhere", rule(self.CSS, ".key"))
        self.assertIn("min-width:0", rule(self.CSS, ".key"))
        self.assertIn("flex-wrap:wrap", rule(self.CSS, ".top"))

    def test_the_type_square_keeps_its_size_when_a_long_key_wraps(self):
        self.assertIn("flex:none", rule(self.CSS, '.key[class*=" k-"]::before'))

    def test_a_long_change_wraps_too(self):
        self.assertIn("overflow-wrap:anywhere", rule(self.CSS, ".chg"))

    def test_the_window_is_taller_when_a_key_has_to_wrap(self):
        short = approval.Summary("T", "h", [("A-1", "t", "create")])
        long = approval.Summary("T", "h", [(LONG, "t", "create")])
        self.assertGreater(approval.window_height(long), approval.window_height(short))


if __name__ == "__main__":
    unittest.main()
