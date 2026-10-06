"""The templates in templates/ fix the shape of every card; jkan.template fills them, strictly and in one pass."""
from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import template
from jkan.template import TemplateError


class RenderTest(unittest.TestCase):
    def test_fills_every_placeholder(self):
        self.assertEqual(template.render("Por qué: {{why}}\n\nQué: {{what}}", {"why": "a", "what": "b"}),
                         "Por qué: a\n\nQué: b")

    def test_an_empty_optional_drops_its_whole_paragraph(self):
        text = "{{?intro}}\n\nPor qué: {{why}}\n\nEvidencia:\n{{?evidence}}"
        self.assertEqual(template.render(text, {"intro": "", "why": "a", "evidence": None}), "Por qué: a")
        self.assertEqual(template.render(text, {"intro": "Como x", "why": "a", "evidence": "- 1d93d8d"}),
                         "Como x\n\nPor qué: a\n\nEvidencia:\n- 1d93d8d")

    def test_an_empty_required_value_is_an_error(self):
        with self.assertRaises(TemplateError) as caught:
            template.render("Por qué: {{why}}", {"why": "  "})
        self.assertIn("why", str(caught.exception))

    def test_a_missing_value_and_an_unused_one_are_errors(self):
        with self.assertRaises(TemplateError):
            template.render("Por qué: {{why}}", {})
        with self.assertRaises(TemplateError) as caught:
            template.render("Por qué: {{why}}", {"why": "a", "whyy": "b"})
        self.assertIn("whyy", str(caught.exception))

    def test_values_are_never_expanded_again(self):
        self.assertEqual(template.render("{{why}}", {"why": "B quedó en {{api_b_name}}"}), "B quedó en {{api_b_name}}")

    def test_escape_applies_except_to_html_fragments(self):
        out = template.render("<h1>{{summary}}</h1>{{body_html}}", {"summary": "a & <b>", "body_html": "<p>x</p>"},
                              escape=template.html_escape)
        self.assertEqual(out, "<h1>a &amp; &lt;b&gt;</h1><p>x</p>")

    def test_a_may_be_empty_value_stays_in_place(self):
        self.assertEqual(template.render("key: {{key}}\nparent: {{~parent}}", {"key": "PLATE-1", "parent": ""}),
                         "key: PLATE-1\nparent: ")
        with self.assertRaises(TemplateError):
            template.render("parent: {{~parent}}", {})

    def test_placeholders_lists_names_and_their_kind(self):
        self.assertEqual(template.placeholders("{{?intro}} {{why}} {{why}} {{~parent}}"),
                         {"intro": "?", "why": "", "parent": "~"})

    def test_the_shipped_templates_load(self):
        for name in ("description.md", "issue.md", "card.html"):
            self.assertTrue(template.placeholders(template.load(name)), name)


if __name__ == "__main__":
    unittest.main()
