"""A card's description comes from templates/description.md and reads back into the same fields.

Python builds it from the spec's why / what / done_when and checks any edited one before it goes to Jira, so a card
without its reason, its scope or its finish line never reaches the board.
"""
from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import description
from jkan.template import TemplateError

FIELDS = {"why": "El export manda los story points a otro campo.", "what": "Elegir el campo por nombre.",
          "done_when": "El preflight informa customfield_10016."}


class RenderTest(unittest.TestCase):
    def test_a_task_renders_the_three_sections_in_order(self):
        self.assertEqual(description.render(FIELDS),
                         "Por qué: El export manda los story points a otro campo.\n\n"
                         "Qué: Elegir el campo por nombre.\n\n"
                         "Hecho cuando: El preflight informa customfield_10016.")

    def test_a_story_adds_its_user_story_acceptance_and_evidence(self):
        text = description.render(dict(FIELDS, intro="Como analista quiero x para y",
                                       acceptance="- AC1: Dado a Cuando b Entonces c",
                                       evidence="- https://github.com/org/repo/pull/7"))
        self.assertTrue(text.startswith("Como analista quiero x para y\n\nPor qué:"))
        self.assertIn("Criterios de aceptación:\n- AC1: Dado a Cuando b Entonces c", text)
        self.assertTrue(text.endswith("Evidencia:\n- https://github.com/org/repo/pull/7"))

    def test_a_missing_section_is_refused(self):
        with self.assertRaises(TemplateError) as caught:
            description.render({"why": "x", "what": "y"})
        self.assertIn("done_when", str(caught.exception))


    def test_optional_sections_render_in_order_when_given(self):
        text = description.render(dict(FIELDS, how="Leer el campo del preflight.", out_of_scope="Los otros campos.",
                                       assumptions="- El campo existe en PLATE.", edge_cases="- Un proyecto sin el campo.",
                                       references="- jira.exporter.ts:594", acceptance="- AC1: a",
                                       evidence="- abc1234"))
        labels = [line.split(":")[0] for line in text.split("\n\n")]
        self.assertEqual(labels, ["Por qué", "Qué", "Cómo", "Fuera de alcance", "Supuestos", "Casos borde",
                                  "Hecho cuando", "Criterios de aceptación", "Referencias", "Evidencia"])

    def test_optional_sections_left_empty_are_omitted(self):
        self.assertEqual(description.render(dict(FIELDS, how="", out_of_scope="", references="")),
                         description.render(FIELDS))


class ParseTest(unittest.TestCase):
    def test_parse_reads_back_what_render_wrote(self):
        fields = dict(FIELDS, intro="Como analista quiero x para y", acceptance="- AC1: a\n- AC2: b",
                      evidence="- abc1234")
        self.assertEqual(description.parse(description.render(fields)), fields)

    def test_parse_reads_back_the_optional_sections(self):
        fields = dict(FIELDS, how="Leer el preflight.", out_of_scope="Los otros campos.", assumptions="- uno",
                      edge_cases="- dos", references="- tres")
        self.assertEqual(description.parse(description.render(fields)), fields)

    def test_a_section_may_span_lines_and_bullets(self):
        text = "Por qué: dos causas:\n- una;\n- otra.\n\nQué: arreglarlas.\n\nHecho cuando: pasan los tests.\n\nPR #49: url"
        parsed = description.parse(text)
        self.assertEqual(parsed["why"], "dos causas:\n- una;\n- otra.")
        self.assertEqual(parsed["done_when"], "pasan los tests.\n\nPR #49: url")

    def test_text_before_the_first_label_is_the_intro(self):
        parsed = description.parse("Objetivo: corregir PB.\n\nPor qué: x\n\nQué: y\n\nHecho cuando: z")
        self.assertEqual(parsed["intro"], "Objetivo: corregir PB.")


class CheckTest(unittest.TestCase):
    def test_a_complete_description_passes_even_with_braces_in_prose(self):
        text = description.render(dict(FIELDS, why="B quedó en {{api_b_name}} en el panel."))
        self.assertEqual(description.check(text), [])

    def test_a_card_without_the_optional_sections_still_passes(self):
        self.assertEqual(description.check("Por qué: x\n\nQué: y\n\nHecho cuando: z"), [])

    def test_missing_and_empty_sections_are_reported(self):
        self.assertEqual(description.check("Notas sueltas\n\nPor qué: x\n\nQué:"),
                         ["empty: Qué", "missing: Hecho cuando"])

    def test_an_unfilled_placeholder_is_reported(self):
        self.assertEqual(description.check("Por qué: {{why}}\n\nQué: y\n\nHecho cuando: z"), ["not filled in: Por qué"])

    def test_a_free_text_description_names_every_section(self):
        self.assertEqual(description.check("Rama fix/telemetria. Pide recompilar."),
                         ["missing: Por qué", "missing: Qué", "missing: Hecho cuando"])


if __name__ == "__main__":
    unittest.main()
