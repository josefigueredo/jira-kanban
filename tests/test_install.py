from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


def install(home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(["bash", str(ROOT / "install.sh")], env=env, capture_output=True, text=True)


class InstallTest(unittest.TestCase):
    def test_both_skills_are_linked_for_every_host(self):
        home = Path(tempfile.mkdtemp(prefix="jk-home-"))
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-kanban"), str(ROOT))
        self.assertEqual(os.readlink(home / ".agents/skills/jira-standup"), str(ROOT / "standup"))
        for host in (".claude", ".codex", ".cursor"):
            for name in ("jira-kanban", "jira-standup"):
                self.assertEqual(os.readlink(home / host / "skills" / name), f"../../.agents/skills/{name}")
        self.assertEqual(install(home).returncode, 0)  # re-running is safe

    def test_a_real_directory_is_never_replaced(self):
        home = Path(tempfile.mkdtemp(prefix="jk-home-"))
        (home / ".agents/skills/jira-standup").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)


if __name__ == "__main__":
    unittest.main()
