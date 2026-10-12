"""The docs are what a new install reads: where each credential comes from, why this skill sits next to Atlassian's MCP, and that every link in them lands."""
from __future__ import annotations

import re
import unittest

from pathlib import Path

from helpers import ROOT
from jkan import config

DOCS = ROOT / "docs"
INSTALL = (DOCS / "instalacion.md").read_text(encoding="utf-8")
REFERENCE = (DOCS / "referencia.md").read_text(encoding="utf-8")
PAGES = [ROOT / "README.md", DOCS / "instalacion.md", DOCS / "showcase.md", DOCS / "referencia.md"]


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def anchors(path: Path) -> set:
    return {slug(m.group(2)) for m in re.finditer(r"^(#{1,6}) (.+)$", path.read_text(encoding="utf-8"), re.M)}


class ReadmeTest(unittest.TestCase):
    def section(self, title: str, text: str = INSTALL) -> str:
        return text.split(title, 1)[1].split("\n## ", 1)[0]

    def test_credentials_name_every_variable_and_link_to_where_to_get_it(self):
        text = self.section("## 3. Credenciales de Jira")
        for names in config.KEYS.values():
            self.assertIn(names[0], text)
        self.assertIn("https://id.atlassian.com/manage-profile/security/api-tokens", text)
        self.assertIn("https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/", text)

    def test_credentials_warn_that_the_token_must_not_have_scopes(self):
        # jtk calls <site>.atlassian.net with basic auth; a token with scopes only works through api.atlassian.com
        text = self.section("## 3. Credenciales de Jira")
        self.assertIn("sin alcance", text)
        self.assertIn("api.atlassian.com", text)

    def test_credentials_have_a_check_that_needs_no_write(self):
        self.assertIn("jtk who", self.section("## 3. Credenciales de Jira"))

    def test_the_readme_compares_with_the_atlassian_mcp_and_links_it(self):
        text = self.section("## Frente al MCP de Atlassian", REFERENCE)
        self.assertIn("https://github.com/atlassian/atlassian-mcp-server", text)
        self.assertIn("https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/", text)
        self.assertIn("ventana", text)  # the approval window is the difference that matters
        self.assertIn("no instales", text.lower())

    def test_every_relative_link_and_image_in_the_docs_lands_on_a_file_and_an_anchor(self):
        link = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
        for page in PAGES:
            for target in link.findall(page.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target):  # https:, mailto:
                    continue
                path, _, fragment = target.partition("#")
                dest = (page.parent / path).resolve() if path else page
                self.assertTrue(dest.exists(), f"{page.name} links to {target}, which does not exist")
                if fragment and dest.suffix == ".md":
                    self.assertIn(fragment, anchors(dest), f"{page.name} links to {target}: no such heading")

    def test_the_index_links_each_skill_to_the_showcase_and_the_install_guide(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        rows = [line for line in readme.splitlines() if line.startswith("| **`jira-")]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIn("docs/showcase.md#", row)
            self.assertIn("docs/instalacion.md#", row)


if __name__ == "__main__":
    unittest.main()
