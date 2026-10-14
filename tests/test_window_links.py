"""Every approval row about an issue that already exists links it, so a person can open it before approving; the
link opens in the browser and never navigates the approval window."""
from __future__ import annotations

import unittest

from helpers import ROOT, FakeJira, epic_with_children, make_project
from jkan import approval, plan
from test_legacy_guard import Asked, run as run_guarded

BROWSE = "https://example.atlassian.net/browse/"
MOVE = {"id": "x" * 12, "version": 1, "kind": "move", "view": "plataforma", "created": "2026-10-14T12:00:00Z",
        "options": {"to_role": "delivered", "to_status": None, "allow_close": True},
        "items": [{"key": "TEAM-1", "title": "Uno", "from": {"id": "1", "name": "Backlog"},
                   "to": {"id": "3", "name": "Done", "role": "delivered"}, "transition": "1>3"}],
        "skipped": []}


class RenderTest(unittest.TestCase):
    def test_a_linked_row_shows_its_title_as_a_link_that_opens_outside(self):
        summary = approval.Summary("t", "Cambiar estado", [("TEAM-1", "Uno", "Backlog -> Done")],
                                   links=[BROWSE + "TEAM-1"])
        page = approval.render_html(summary, 1)
        self.assertIn(f'<a class="name" href="{BROWSE}TEAM-1" target="_blank">Uno</a>', page)
        self.assertIn('a.name::after{content:" 🔗"', page)

    def test_only_https_links_are_rendered(self):
        summary = approval.Summary("t", "h", [("A-1", "x", "y")], links=["javascript:alert(1)"])
        page = approval.render_html(summary, 1)
        self.assertNotIn("<a ", page)
        self.assertNotIn("javascript", page)

    def test_alert_js_opens_links_in_the_browser(self):
        js = (ROOT / "jkan" / "alert.js").read_text(encoding="utf-8")
        self.assertIn("'webView:createWebViewWithConfiguration:forNavigationAction:windowFeatures:'", js)
        self.assertIn("web.UIDelegate = ", js)
        self.assertIn("openURL", js)
        self.assertIn("'https'", js)


class WritersTest(unittest.TestCase):
    def test_a_plan_apply_links_each_issue(self):
        summary = plan.summary(MOVE, browse=lambda key: BROWSE + key)
        self.assertEqual(summary.links, [BROWSE + "TEAM-1"])

    def test_assign_attach_and_push_link_existing_issues_and_not_new_ones(self):
        jira, project = FakeJira(), make_project()
        epic = epic_with_children(jira)
        asked = Asked()
        run_guarded(["assign", "PLATE-603", "Matias Andres Fernandez", "--project", str(project), "--apply"], jira, asked)
        self.assertEqual(asked.calls[0][1].links, ["https://example.atlassian.net/browse/PLATE-603"])
        doc = project / "a.md"
        doc.write_text("hola\n", encoding="utf-8")
        asked = Asked()
        run_guarded(["attach", "PLATE-603", str(doc), "--project", str(project), "--apply"], jira, asked)
        self.assertEqual(asked.calls[0][1].links, ["https://example.atlassian.net/browse/PLATE-603"])
        from jkan import kanban, sync
        from test_push_moves import set_status
        sync.pull(jira, project, epic)
        set_status(kanban.epic_dir(project, epic) / "tasks/PLATE-603/task.md", "Done")
        asked = Asked()
        run_guarded(["push", epic, "--project", str(project), "--apply", "--assign-open"], jira, asked)
        summary = asked.calls[0][1]
        row = summary.rows.index(next(r for r in summary.rows if r[0] == "PLATE-603"))
        self.assertTrue(summary.rows[row][1])  # the issue's title, so the link has something to show
        self.assertEqual(summary.links[row], "https://example.atlassian.net/browse/PLATE-603")


if __name__ == "__main__":
    unittest.main()
