"""The three skills that ship in this repo: each is where install.sh says, is named like its folder, can be told apart by
its description, and the commands the team skill tells the agent to run exist."""
from __future__ import annotations

import re
import unittest

from helpers import ROOT
from jkan import board_cli, plan_cli, team_cli

SKILLS = ((".", "jira-team-kit"), ("standup", "jira-standup"), ("em", "jira-em"), ("ops", "jira-em-ops"))


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
        description = re.sub(r"\bjira-[a-z-]+", "", frontmatter("standup")["description"].lower())  # skill names are not claims
        self.assertIsNone(re.search(r"\bteams?\b", description))  # «a teammate» is fine; «the team» is jira-em's
        self.assertNotIn("equipo", description)

    def test_the_team_skill_is_about_the_team_and_points_to_the_other_two(self):
        description = frontmatter("em")["description"]
        self.assertIn("team", description)
        self.assertIn("not about themselves", description)
        self.assertIn("jira-standup", description)
        self.assertIn("jira-team-kit", description)

    def test_the_team_skill_calls_only_jk_and_never_writes_to_jira(self):
        text = (ROOT / "em" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("jtk.py", text)
        self.assertNotIn("jtk create", text)
        self.assertNotIn("jtk push", text)
        self.assertNotIn("jtk assign", text)

    def test_every_team_and_board_command_the_team_skill_mentions_exists(self):
        text = (ROOT / "em" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jtk team (\w+)", text):
            self.assertIn(verb, team_cli.VERBS, verb)
        for verb in re.findall(r"jtk board (\w+)", text):
            self.assertIn(verb, board_cli.VERBS, verb)

    def test_the_ops_skill_is_about_changing_the_team_and_points_to_the_read_only_ones(self):
        description = frontmatter("ops")["description"]
        self.assertIn("team", description)
        self.assertIn("jira-em", description)
        self.assertIn("jira-team-kit", description)

    def test_the_ops_skill_applies_only_when_asked_through_the_window_and_never_retries_a_cancel(self):
        text = (ROOT / "ops" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("jtk.py", text)
        for forbidden in ("jtk create", "jtk push", "jtk assign"):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("Never run `jtk apply`", text)
        self.assertIn("Run `jtk apply <id>` only after the person asked to apply that plan", text)
        self.assertIn("Apruebo <n>", text)
        self.assertIn("never run it again", text)

    def test_every_plan_command_the_ops_skill_mentions_exists(self):
        text = (ROOT / "ops" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jtk plan (\w+)", text):
            self.assertIn(verb, plan_cli.VERBS, verb)
        for verb in re.findall(r"jtk team (\w+)", text):
            self.assertIn(verb, team_cli.VERBS, verb)

    def test_every_skill_says_jira_goes_through_jtk_and_not_through_an_atlassian_mcp(self):
        # Cursor suggests Atlassian's MCP when someone types «jira»; its write tools would skip the approval window.
        for folder, name in SKILLS:
            description = frontmatter(folder)["description"]
            self.assertIn("jtk", description, name)
            self.assertIn("Atlassian MCP", description, name)

    def test_the_write_skill_forbids_the_atlassian_mcp_in_its_rules(self):
        rules = (ROOT / "SKILL.md").read_text(encoding="utf-8").split("## Rules")[1]
        self.assertIn("Atlassian MCP", rules)
        self.assertIn("approval", rules)

    def test_the_report_skills_name_the_window_instead_of_asking_the_agent_to_count_days(self):
        for folder in ("standup", "em"):
            text = (ROOT / folder / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("--when", text, folder)
            self.assertNotIn("Turn the user's words into dates", text, folder)
        standup = (ROOT / "standup" / "SKILL.md").read_text(encoding="utf-8")
        for name in ("yesterday", "last-week", "next-week"):
            self.assertIn(name, standup)

    def test_the_descriptions_do_not_overlap_on_the_phrases_that_pick_a_skill(self):
        self.assertNotIn("Read only", frontmatter("ops")["description"])
        self.assertNotIn("assign", frontmatter("em")["description"].lower())

    def test_the_personal_skill_mentions_only_commands_that_exist(self):
        text = (ROOT / "standup" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jtk board (\w+)", text):
            self.assertIn(verb, board_cli.VERBS, verb)


if __name__ == "__main__":
    unittest.main()
