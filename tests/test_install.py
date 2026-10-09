from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


def install(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(["bash", str(ROOT / "install.sh"), *args], env=env, capture_output=True, text=True)


def fresh_home() -> Path:
    return Path(tempfile.mkdtemp(prefix="jk-home-"))


class InstallTest(unittest.TestCase):
    def test_by_default_only_the_read_only_skill_is_linked_for_every_host(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-standup"), str(ROOT / "standup"))
        for host in (".claude", ".codex", ".cursor"):
            self.assertEqual(os.readlink(home / host / "skills/jira-standup"), "../../.agents/skills/jira-standup")
        self.assertFalse(os.path.lexists(home / ".agents/skills/jira-kanban"))
        self.assertEqual(install(home).returncode, 0)  # re-running is safe

    def test_with_write_adds_the_skill_that_writes_to_jira(self):
        home = fresh_home()
        self.assertEqual(install(home, "--with-write").returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-kanban"), str(ROOT))
        for host in (".claude", ".codex", ".cursor"):
            for name in ("jira-kanban", "jira-standup"):
                self.assertEqual(os.readlink(home / host / "skills" / name), f"../../.agents/skills/{name}")

    def test_running_it_again_without_the_flag_does_not_remove_a_skill_installed_before(self):
        home = fresh_home()
        install(home, "--with-write")
        install(home)
        self.assertTrue(os.path.islink(home / ".agents/skills/jira-kanban"))

    def test_jk_is_put_on_the_path_and_is_executable(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".local/bin/jk"), str(ROOT / "jk.py"))
        self.assertTrue(os.access(ROOT / "jk.py", os.X_OK))

    def test_a_real_file_named_jk_is_never_replaced(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/jk").write_text("mine", encoding="utf-8")
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)
        self.assertEqual((home / ".local/bin/jk").read_text(encoding="utf-8"), "mine")

    def test_a_real_directory_is_never_replaced(self):
        home = fresh_home()
        (home / ".agents/skills/jira-standup").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)

    def test_an_unknown_argument_is_refused(self):
        self.assertEqual(install(fresh_home(), "--wat").returncode, 2)


if __name__ == "__main__":
    unittest.main()
