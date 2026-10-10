"""The three skills that ship in this repo: each is where install.sh says, is named like its folder, can be told apart by
its description, and the commands the team skill tells the agent to run exist."""
from __future__ import annotations

import re
import unittest

from helpers import ROOT
from jkan import board_cli, team_cli

SKILLS = ((".", "jira-kanban"), ("standup", "jira-standup"), ("em", "jira-em"))


def frontmatter(folder: str) -> dict:
    text = (ROOT / folder / "SKILL.md").read_text(encoding="utf-8")
    block = text.split("---")[1]
    return dict(line.split(": ", 1) for line in block.strip().splitlines())


class SkillsTest(unittest.TestCase):
    def test_each_skill_file_is_named_like_its_skill_and_starts_with_use_when(self):
        for folder, name in SKILLS:
            fm = frontmatter(folder)
            self.assertEqual(fm["name"], name, folder)
            self.assertTrue(fm["description"].startswith("Use when"), name)

    def test_the_personal_skill_never_claims_team_questions(self):
        description = frontmatter("standup")["description"].lower()
        self.assertIsNone(re.search(r"\bteams?\b", description))  # «a teammate» is fine; «the team» is jira-em's
        self.assertNotIn("equipo", description)

    def test_the_team_skill_is_about_the_team_and_points_to_the_other_two(self):
        description = frontmatter("em")["description"]
        self.assertIn("team", description)
        self.assertIn("not about themselves", description)
        self.assertIn("jira-standup", description)
        self.assertIn("jira-kanban", description)

    def test_the_team_skill_calls_only_jk_and_never_writes_to_jira(self):
        text = (ROOT / "em" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("jk.py", text)
        self.assertNotIn("jk create", text)
        self.assertNotIn("jk push", text)
        self.assertNotIn("jk assign", text)

    def test_every_team_and_board_command_the_team_skill_mentions_exists(self):
        text = (ROOT / "em" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jk team (\w+)", text):
            self.assertIn(verb, team_cli.VERBS, verb)
        for verb in re.findall(r"jk board (\w+)", text):
            self.assertIn(verb, board_cli.VERBS, verb)

    def test_the_personal_skill_mentions_only_commands_that_exist(self):
        text = (ROOT / "standup" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jk board (\w+)", text):
            self.assertIn(verb, board_cli.VERBS, verb)


if __name__ == "__main__":
    unittest.main()
