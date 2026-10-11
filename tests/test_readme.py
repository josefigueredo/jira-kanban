"""The README is what a new install reads: where each credential comes from, and why this skill sits next to Atlassian's MCP."""
from __future__ import annotations

import unittest

from helpers import ROOT
from jkan import config

README = (ROOT / "README.md").read_text(encoding="utf-8")


class ReadmeTest(unittest.TestCase):
    def section(self, title: str) -> str:
        return README.split(title, 1)[1].split("\n## ", 1)[0]

    def test_credentials_name_every_variable_and_link_to_where_to_get_it(self):
        text = self.section("### Credenciales")
        for names in config.KEYS.values():
            self.assertIn(names[0], text)
        self.assertIn("https://id.atlassian.com/manage-profile/security/api-tokens", text)
        self.assertIn("https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/", text)

    def test_credentials_warn_that_the_token_must_not_have_scopes(self):
        # jtk calls <site>.atlassian.net with basic auth; a token with scopes only works through api.atlassian.com
        text = self.section("### Credenciales")
        self.assertIn("sin alcance", text)
        self.assertIn("api.atlassian.com", text)

    def test_credentials_have_a_check_that_needs_no_write(self):
        self.assertIn("jtk who", self.section("### Credenciales"))

    def test_the_readme_compares_with_the_atlassian_mcp_and_links_it(self):
        text = self.section("## Frente al MCP de Atlassian")
        self.assertIn("https://github.com/atlassian/atlassian-mcp-server", text)
        self.assertIn("https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/", text)
        self.assertIn("ventana", text)  # the approval window is the difference that matters
        self.assertIn("no instales", text.lower())


if __name__ == "__main__":
    unittest.main()
