"""The skills of this repo follow the Agent Skills format (https://agentskills.io/specification), checked offline with
the port in skillspec.py.

Three of the four skills live in a folder that is not their name (standup/ is jira-standup) and `jtk update` is only a
`git pull --ff-only`, so renaming folders would leave the installed ~/.agents/skills/jira-* links dangling. Each skill is
therefore checked against the name install.sh publishes it under, read from its SKILLS table: that is the folder the
agent sees. `skills-ref validate standup/` run straight on the repo would fail the folder-name rule on purpose."""
from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from skillspec import check_skill, parse_frontmatter

VALID = """---
name: good-skill
description: >-
  Use when something happens
  and a folded block spans lines.
compatibility: Needs a tool.
metadata:
  author: someone
---
# Body
"""


def published_skills() -> "dict[str, str]":
    """{name: folder inside the repo ("" is the repo itself)} from the SKILLS=(...) / SKILLS+=(...) lines of install.sh."""
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    entries = [e for group in re.findall(r"SKILLS\+?=\(([^)]*)\)", text) for e in re.findall(r'"([^"]+)"', group)]
    return dict(entry.split(":", 1) for entry in entries)


def repo_skill_folders() -> "set[str]":
    found = {""} if (ROOT / "SKILL.md").is_file() else set()
    return found |{p.parent.name for p in ROOT.glob("*/SKILL.md")}


class ReferenceCheckerTest(unittest.TestCase):
    """The checker has to bite: each rule is exercised against a skill broken on purpose."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skillspec-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def errors(self, text: "str | None", folder: str = "good-skill") -> "list[str]":
        skill = self.tmp / folder
        skill.mkdir(exist_ok=True)
        if text is not None:
            (skill / "SKILL.md").write_text(text, encoding="utf-8")
        return check_skill(skill)

    def front(self, **fields: str) -> str:
        base = {"name": "good-skill", "description": "Use when testing."}
        base.update(fields)
        return "---\n" + "".join(f"{k}: {v}\n" for k, v in base.items() if v is not None) + "---\nbody\n"

    def test_a_valid_skill_with_a_folded_block_and_metadata_passes(self):
        self.assertEqual(self.errors(VALID), [])
        self.assertEqual(parse_frontmatter(VALID)["description"], "Use when something happens and a folded block spans lines.")

    def test_each_rule_rejects_its_broken_skill(self):
        cases = {
            "field outside the spec": (self.front(version="1"), "unexpected frontmatter fields"),
            "uppercase": (self.front(name="Good-skill"), "lowercase"),
            "double hyphen": (self.front(name="good--skill"), "consecutive hyphens"),
            "hyphen at the edge": (self.front(name="-good-skill"), "starts or ends with a hyphen"),
            "name differs from the folder": (self.front(name="other-skill"), "does not match"),
            "no description": (self.front(description=None), "missing required field: description"),
            "description over 1024": (self.front(description="x" * 1025), "description is 1025"),
            "compatibility over 500": (self.front(compatibility="x" * 501), "compatibility is 501"),
            "no frontmatter": ("# just a body\n", "no YAML frontmatter"),
            "name over 64": (self.front(name="a" * 65), "max 64"),
        }
        for label, (text, expected) in cases.items():
            with self.subTest(label):
                folder = "a" * 65 if label == "name over 64" else "good-skill"
                found = self.errors(text, folder)
                self.assertTrue(any(expected in e for e in found), f"{expected!r} not in {found}")

    def test_a_published_name_replaces_the_folder_name(self):
        skill = self.tmp / "clone-of-the-repo"
        skill.mkdir()
        (skill / "SKILL.md").write_text(self.front(), encoding="utf-8")
        self.assertTrue(check_skill(skill))  # by folder it fails ...
        self.assertEqual(check_skill(skill, published_name="good-skill"), [])  # ... by the published name it conforms
        self.assertTrue(check_skill(skill, published_name="another-name"))


class RepoSkillsTest(unittest.TestCase):
    def test_install_sh_publishes_the_four_skills(self):
        self.assertEqual(set(published_skills()), {"jira-team-kit", "jira-standup", "jira-em", "jira-em-ops"})

    def test_every_skill_of_the_repo_is_published_and_every_published_skill_exists(self):
        self.assertEqual(repo_skill_folders(), set(published_skills().values()))

    def test_each_skill_conforms_under_the_name_it_is_published_with(self):
        for name, folder in published_skills().items():
            with self.subTest(name):
                self.assertEqual(check_skill(ROOT / folder if folder else ROOT, published_name=name), [])

    def test_the_root_skill_is_judged_by_its_published_name_not_by_the_clone_folder(self):
        root_name = next(n for n, f in published_skills().items() if f == "")
        self.assertEqual(root_name, "jira-team-kit")
        self.assertEqual(parse_frontmatter((ROOT / "SKILL.md").read_text(encoding="utf-8"))["name"], root_name)
        # whoever clones the repo may call the folder anything: only the published name counts
        clone = Path(tempfile.mkdtemp(prefix="some-other-clone-name-"))
        self.addCleanup(shutil.rmtree, clone, True)
        shutil.copy(ROOT / "SKILL.md", clone / "SKILL.md")
        self.assertEqual(check_skill(clone, published_name=root_name), [])


if __name__ == "__main__":
    unittest.main()
