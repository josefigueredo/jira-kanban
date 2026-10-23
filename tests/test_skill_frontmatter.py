"""Every SKILL.md frontmatter must parse as strict YAML (Copilot CLI rejects what Claude Code tolerates)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def frontmatter(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return []
    end = lines.index("---", 1)
    return lines[1:end]


class SkillFrontmatterTest(unittest.TestCase):
    def test_plain_values_have_no_colon_space(self):
        skills = [p for p in ROOT.rglob("SKILL.md") if ".worktrees" not in p.parts]
        self.assertTrue(skills)
        for path in skills:
            for line in frontmatter(path):
                match = re.match(r"^([A-Za-z_-]+): (.*)$", line)
                if not match or match.group(2).startswith((">", "|", '"', "'")):
                    continue
                with self.subTest(skill=str(path.relative_to(ROOT)), key=match.group(1)):
                    self.assertNotIn(": ", match.group(2))
                    self.assertFalse(match.group(2).rstrip().endswith(":"))


if __name__ == "__main__":
    unittest.main()
