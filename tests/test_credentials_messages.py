"""A new user is shown the generic JIRA_* names; IC_JIRA_* is one person's own alias, read but never advertised."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT
from jkan import cli, config

SKILLS = (".", "standup", "em", "ops")
GENERIC = {"base_url": "JIRA_BASE_URL", "email": "JIRA_EMAIL", "token": "JIRA_API_TOKEN"}


class CredentialsMessagesTest(unittest.TestCase):
    def test_the_missing_credentials_error_names_the_generic_variables_and_not_the_personal_ones(self):
        bare = {k: v for k, v in os.environ.items() if "JIRA" not in k}  # the shell running the suite may hold real ones
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, bare, clear=True), \
                self.assertRaises(SystemExit) as raised:
            cli._client(Path(tmp))  # no .env.local, no .spec-kit/.env
        message = str(raised.exception)
        self.assertIn("JIRA_API_TOKEN", message)
        self.assertNotIn("IC_JIRA", message)

    def test_no_skill_tells_the_agent_about_the_personal_variables(self):
        for folder in SKILLS:
            text = (ROOT / folder / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("IC_JIRA", text, folder)

    def test_the_personal_alias_is_still_read_and_wins_over_the_generic_name(self):
        # WayOfWork resolves the IC_ names too: removing them here would break whoever already has them set.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            aliased = {"IC_JIRA_BASE_URL": "https://ic.example", "IC_JIRA_USER_EMAIL": "ic@x", "IC_JIRA_API_TOKEN": "ic-t"}
            self.assertEqual(config.credentials(project, aliased), ("https://ic.example", "ic@x", "ic-t"))
            both = dict(aliased, JIRA_BASE_URL="https://g.example", JIRA_EMAIL="g@x", JIRA_API_TOKEN="g-t")
            self.assertEqual(config.credentials(project, both), ("https://ic.example", "ic@x", "ic-t"))
            generic = {"JIRA_BASE_URL": "https://g.example", "JIRA_EMAIL": "g@x", "JIRA_API_TOKEN": "g-t"}
            self.assertEqual(config.credentials(project, generic), ("https://g.example", "g@x", "g-t"))
        self.assertEqual({k: v[1] for k, v in config.KEYS.items()}, GENERIC)
        self.assertTrue(all(v[0].startswith("IC_JIRA_") for v in config.KEYS.values()))


if __name__ == "__main__":
    unittest.main()
