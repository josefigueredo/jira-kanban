from __future__ import annotations

import unittest

from helpers import CONVENTIONS, described
from jkan import description, spec

GOOD = {
    "epic": {"summary": "Kanban local de Jira", "why": "El equipo sigue el trabajo en Jira pero lo edita desde el repo.",
             "what": "La épica y sus hijos, como carpetas locales.", "done_when": "Un pull y un push dejan Jira igual."},
    "items": [
        {"type": "story", "area": "FE", "summary": "Ver el tablero",
         "user_story": "Como analista quiero ver el tablero para decidir",
         "why": "Hoy el avance solo se ve entrando a Jira issue por issue.", "what": "Un tablero por categoría de estado.",
         "done_when": "Los criterios de aceptación se cumplen.",
         "acceptance": ["AC1: Dado un tablero Cuando lo abro Entonces veo las columnas"],
         "subtasks": [{"summary": "Armar la vista", "why": "La historia necesita una vista.", "what": "Una columna por estado.",
                       "done_when": "Se ve el tablero."}]},
        {"type": "task", "area": "DEVOPS", "summary": "Pipeline", "why": "Nada corre los tests.", "what": "CI con gate.",
         "done_when": "Un PR rojo no se puede mergear."},
    ],
}


class ValidateTest(unittest.TestCase):
    def test_good_spec_has_no_findings(self):
        self.assertEqual(spec.validate(GOOD, CONVENTIONS), [])

    def test_every_issue_needs_why_what_and_done_when(self):
        bare = {"epic": {"summary": "e"},
                "items": [{"type": "task", "summary": "t", "why": "  ", "subtasks": [{"summary": "s"}]}]}
        findings = spec.validate(bare, CONVENTIONS)
        for ref in ("epic", "items[0]", "items[0].subtasks[0]"):
            self.assertIn(f"{ref}: why is required (the problem or need, as observed)", findings)
            self.assertIn(f"{ref}: what is required (the change and its scope; what stays out goes in out_of_scope)", findings)
            self.assertIn(f"{ref}: done_when is required (how a person checks it without asking)", findings)

    def test_a_free_description_is_refused_with_the_fields_to_use(self):
        loose = described({"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t"}]})
        loose["items"][0]["description"] = "Rama fix/telemetria."
        self.assertIn("items[0]: description is built from why, what and done_when (templates/description.md); "
                      "split it into those fields", spec.validate(loose, CONVENTIONS))

    def test_story_needs_a_user_story_and_task_does_not(self):
        bad = described({"epic": {"summary": "x"}, "items": [{"type": "story", "summary": "Sin historia"}]})
        self.assertIn("items[0]: a story needs user_story (Como … quiero … para …); use a task if no one benefits",
                      spec.validate(bad, CONVENTIONS))

    def test_unknown_type_area_and_priority(self):
        bad = described({"epic": {"summary": "x"}, "items": [{"type": "subtask", "summary": "y"},
                                                    {"type": "task", "summary": "z", "area": "UX", "priority": "Urgent"}]})
        findings = spec.validate(bad, CONVENTIONS)
        self.assertIn("items[0]: type must be story or task, not 'subtask'", findings)
        self.assertIn("items[1]: area 'UX' is not one of FE, BE, BO, QA, DEVOPS, INFRA, BFF, AI", findings)
        self.assertIn("items[1]: priority 'Urgent' is not one of Highest, High, Medium, Low, Lowest", findings)

    def test_needs_an_epic_summary_and_items(self):
        self.assertEqual(spec.validate({"epic": {}, "items": []}, CONVENTIONS),
                         ["epic: summary is required",
                          "epic: why is required (the problem or need, as observed)",
                          "epic: what is required (the change and its scope; what stays out goes in out_of_scope)",
                          "epic: done_when is required (how a person checks it without asking)",
                          "items: at least one story or task"])


class OptionalSectionsTest(unittest.TestCase):
    def test_the_cheap_sections_are_optional(self):
        self.assertEqual(spec.validate(GOOD, CONVENTIONS), [])

    def test_a_list_becomes_bullets_and_prose_stays_as_written(self):
        fields = spec.sections({"why": "a", "what": "b", "done_when": "c", "how": "Leer el preflight.",
                                "out_of_scope": ["El epic", "Los labels"], "assumptions": ["PLATE tiene el campo"],
                                "edge_cases": ["Sin campo"], "references": ["jira.exporter.ts:594"]})
        self.assertEqual(fields["how"], "Leer el preflight.")
        self.assertEqual(fields["out_of_scope"], "- El epic\n- Los labels")
        self.assertEqual(fields["assumptions"], "- PLATE tiene el campo")
        self.assertEqual(fields["edge_cases"], "- Sin campo")
        self.assertEqual(fields["references"], "- jira.exporter.ts:594")

    def test_they_reach_the_description(self):
        item = dict(GOOD["items"][1], how="Un job de CI.", out_of_scope=["Deploy"])
        text = spec.plan(dict(GOOD, items=[item]), CONVENTIONS)[1]["description"]
        self.assertIn("Cómo: Un job de CI.", text)
        self.assertIn("Fuera de alcance:\n- Deploy", text)

    def test_a_wrong_type_is_reported(self):
        item = dict(GOOD["items"][1], references={"a": 1})
        self.assertIn("items[0]: references must be text or a list of strings",
                      spec.validate(dict(GOOD, items=[item]), CONVENTIONS))


class PlanTest(unittest.TestCase):
    def test_titles_carry_the_area_prefix_and_descriptions_carry_the_story(self):
        ops = spec.plan(GOOD, CONVENTIONS)
        self.assertEqual([(o["ref"], o["kind"], o["parent"], o["summary"]) for o in ops], [
            ("epic", "epic", None, "Kanban local de Jira"),
            ("items[0]", "story", "epic", "[FE] Ver el tablero"),
            ("items[0].subtasks[0]", "subtask", "items[0]", "Armar la vista"),
            ("items[1]", "task", "epic", "[DEVOPS] Pipeline"),
        ])
        story = ops[1]
        self.assertEqual(story["description"], description.render({
            "intro": "Como analista quiero ver el tablero para decidir",
            "why": "Hoy el avance solo se ve entrando a Jira issue por issue.", "what": "Un tablero por categoría de estado.",
            "done_when": "Los criterios de aceptación se cumplen.",
            "acceptance": "- AC1: Dado un tablero Cuando lo abro Entonces veo las columnas"}))
        self.assertEqual(description.check(story["description"]), [])
        self.assertEqual(story["priority"], "Medium")

    def test_existing_prefix_is_not_doubled(self):
        one = described({"epic": {"summary": "e"}, "items": [{"type": "task", "area": "FE", "summary": "[FE] Ya prefijada"}]})
        self.assertEqual(spec.plan(one, CONVENTIONS)[1]["summary"], "[FE] Ya prefijada")


if __name__ == "__main__":
    unittest.main()
