from __future__ import annotations

import unittest

from helpers import CONVENTIONS
from jkan import spec

GOOD = {
    "epic": {"summary": "Kanban local de Jira", "description": "Objetivo y alcance"},
    "items": [
        {"type": "story", "area": "FE", "summary": "Ver el tablero",
         "user_story": "Como analista quiero ver el tablero para decidir",
         "acceptance": ["AC1: Dado un tablero Cuando lo abro Entonces veo las columnas"],
         "subtasks": [{"summary": "Armar la vista"}]},
        {"type": "task", "area": "DEVOPS", "summary": "Pipeline", "description": "CI con gate"},
    ],
}


class ValidateTest(unittest.TestCase):
    def test_good_spec_has_no_findings(self):
        self.assertEqual(spec.validate(GOOD, CONVENTIONS), [])

    def test_story_needs_a_user_story_and_task_does_not(self):
        bad = {"epic": {"summary": "x"}, "items": [{"type": "story", "summary": "Sin historia"}]}
        self.assertIn("items[0]: a story needs user_story (Como … quiero … para …); use a task if no one benefits",
                      spec.validate(bad, CONVENTIONS))

    def test_unknown_type_area_and_priority(self):
        bad = {"epic": {"summary": "x"}, "items": [{"type": "subtask", "summary": "y"},
                                                    {"type": "task", "summary": "z", "area": "UX", "priority": "Urgent"}]}
        findings = spec.validate(bad, CONVENTIONS)
        self.assertIn("items[0]: type must be story or task, not 'subtask'", findings)
        self.assertIn("items[1]: area 'UX' is not one of FE, BE, BO, QA, DEVOPS, INFRA, BFF, AI", findings)
        self.assertIn("items[1]: priority 'Urgent' is not one of Highest, High, Medium, Low, Lowest", findings)

    def test_needs_an_epic_summary_and_items(self):
        self.assertEqual(spec.validate({"epic": {}, "items": []}, CONVENTIONS),
                         ["epic: summary is required", "items: at least one story or task"])


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
        self.assertTrue(story["description"].startswith("Como analista quiero ver el tablero para decidir"))
        self.assertIn("- AC1: Dado un tablero Cuando lo abro Entonces veo las columnas", story["description"])
        self.assertEqual(story["priority"], "Medium")

    def test_existing_prefix_is_not_doubled(self):
        one = {"epic": {"summary": "e"}, "items": [{"type": "task", "area": "FE", "summary": "[FE] Ya prefijada"}]}
        self.assertEqual(spec.plan(one, CONVENTIONS)[1]["summary"], "[FE] Ya prefijada")


if __name__ == "__main__":
    unittest.main()
