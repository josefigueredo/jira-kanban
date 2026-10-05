from __future__ import annotations

import json
import re
import unittest

from helpers import CONVENTIONS, FakeJira, make_project
from jkan import preview, spec
from test_cli import run
from test_spec import GOOD


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.html = preview.render(spec.plan(GOOD, CONVENTIONS), CONVENTIONS)

    def test_every_issue_has_a_page_and_a_link(self):
        for i, op in enumerate(spec.plan(GOOD, CONVENTIONS), 1):
            self.assertIn(f'id="NUEVO-{i}"', self.html)
            self.assertIn(f'href="#NUEVO-{i}"', self.html)
        self.assertIn("[FE] Ver el tablero", self.html)
        self.assertIn("Story (migrated)", self.html)
        self.assertIn("Subtarea", self.html)

    def test_story_page_shows_its_acceptance_and_its_subtask(self):
        story = re.search(r'id="NUEVO-2".*?</section>', self.html, re.S).group(0)
        self.assertIn("AC1: Dado un tablero Cuando lo abro Entonces veo las columnas", story)
        self.assertIn('href="#NUEVO-3"', story)
        self.assertIn("Backlog", story)

    def test_assignee_shows_the_rule(self):
        ops = spec.plan({"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "done": True},
                                                             {"type": "task", "summary": "u"}]}, CONVENTIONS)
        from jkan import sync
        sync.assignment(ops, None)
        html = preview.render(ops, CONVENTIONS)
        self.assertIn("Vos · completa", html)
        self.assertIn("A decidir", html)

    def test_standalone_and_marked_as_a_preview(self):
        self.assertNotRegex(self.html, r'(src|href)="https?://')
        self.assertIn("Vista previa", self.html)
        self.assertIn("nada se creó en Jira", self.html)

    def test_text_is_escaped(self):
        hostile = {"epic": {"summary": "<script>alert(1)</script>"},
                   "items": [{"type": "task", "summary": "a & b", "description": "<b>x</b>"}]}
        html = preview.render(spec.plan(hostile, CONVENTIONS), CONVENTIONS)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("a &amp; b", html)


class PreviewCliTest(unittest.TestCase):
    def test_create_html_writes_the_preview_without_touching_jira(self):
        jira, project = FakeJira(), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps(GOOD), encoding="utf-8")
        out = project / "vista.html"
        code, stdout, _ = run(["create", "--spec", str(path), "--project", str(project), "--html", str(out)], jira)
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())
        self.assertIn(str(out), stdout)
        self.assertEqual(jira.writes, [])


if __name__ == "__main__":
    unittest.main()
