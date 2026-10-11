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
    return Path(tempfile.mkdtemp(prefix="jtk-home-"))


class InstallTest(unittest.TestCase):
    def test_by_default_the_team_skill_is_linked_for_every_host_too(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-em"), str(ROOT / "em"))
        for host in (".claude", ".codex", ".cursor"):
            self.assertEqual(os.readlink(home / host / "skills/jira-em"), "../../.agents/skills/jira-em")

    def test_by_default_only_the_read_only_skills_are_linked_for_every_host(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-standup"), str(ROOT / "standup"))
        for host in (".claude", ".codex", ".cursor"):
            self.assertEqual(os.readlink(home / host / "skills/jira-standup"), "../../.agents/skills/jira-standup")
        self.assertFalse(os.path.lexists(home / ".agents/skills/jira-team-kit"))
        self.assertFalse(os.path.lexists(home / ".agents/skills/jira-em-ops"))
        self.assertEqual(install(home).returncode, 0)  # re-running is safe

    def test_with_write_adds_the_skill_that_writes_to_jira(self):
        home = fresh_home()
        self.assertEqual(install(home, "--with-write").returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-team-kit"), str(ROOT))
        self.assertEqual(os.readlink(home / ".agents/skills/jira-em-ops"), str(ROOT / "ops"))
        for host in (".claude", ".codex", ".cursor"):
            for name in ("jira-team-kit", "jira-standup", "jira-em-ops"):
                self.assertEqual(os.readlink(home / host / "skills" / name), f"../../.agents/skills/{name}")

    def test_running_it_again_without_the_flag_does_not_remove_a_skill_installed_before(self):
        home = fresh_home()
        install(home, "--with-write")
        install(home)
        self.assertTrue(os.path.islink(home / ".agents/skills/jira-team-kit"))

    def test_the_old_skill_names_are_removed_only_when_they_point_to_this_repo(self):
        for old in ("jira-kanban", "jira-toolkit"):
            home = fresh_home()
            mine = home / f".agents/skills/{old}"
            mine.parent.mkdir(parents=True)
            os.symlink(str(ROOT), mine)
            for host in (".claude", ".codex", ".cursor"):
                (home / host / "skills").mkdir(parents=True)
                os.symlink(f"../../.agents/skills/{old}", home / host / f"skills/{old}")
            result = install(home, "--with-write")
            self.assertEqual(result.returncode, 0, old)
            self.assertFalse(os.path.lexists(mine), old)
            for host in (".claude", ".codex", ".cursor"):
                self.assertFalse(os.path.lexists(home / host / f"skills/{old}"), old)
            self.assertEqual(os.readlink(home / ".agents/skills/jira-team-kit"), str(ROOT))
            self.assertIn("jira-team-kit", result.stdout)

    def test_a_skill_named_jira_kanban_that_is_not_this_repo_is_left_alone(self):
        home = fresh_home()
        other = home / "elsewhere"
        other.mkdir()
        (home / ".agents/skills").mkdir(parents=True)
        os.symlink(str(other), home / ".agents/skills/jira-kanban")
        result = install(home, "--with-write")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-kanban"), str(other))

    def test_jk_is_put_on_the_path_and_is_executable(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".local/bin/jtk"), str(ROOT / "jtk.py"))
        self.assertTrue(os.access(ROOT / "jtk.py", os.X_OK))

    def test_a_real_file_named_jk_is_never_replaced(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/jtk").write_text("mine", encoding="utf-8")
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)
        self.assertEqual((home / ".local/bin/jtk").read_text(encoding="utf-8"), "mine")

    def test_a_real_directory_is_never_replaced(self):
        home = fresh_home()
        (home / ".agents/skills/jira-standup").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)

    def test_an_old_jk_link_to_this_repo_is_removed(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        os.symlink(str(ROOT / "jk.py"), home / ".local/bin/jk")
        self.assertEqual(install(home).returncode, 0)
        self.assertFalse(os.path.lexists(home / ".local/bin/jk"))
        self.assertEqual(os.readlink(home / ".local/bin/jtk"), str(ROOT / "jtk.py"))

    def test_a_jk_that_is_not_this_repos_link_is_left_alone(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        os.symlink("/elsewhere/jk.py", home / ".local/bin/jk")
        result = install(home)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(os.readlink(home / ".local/bin/jk"), "/elsewhere/jk.py")
        self.assertIn("left alone", result.stderr)

    def test_old_data_is_announced_with_the_exact_mv_and_never_moved(self):
        home = fresh_home()
        (home / ".config/jk/profiles").mkdir(parents=True)
        (home / ".local/state/jk").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 0)
        self.assertIn("mv ~/.config/jk ~/.config/jtk", result.stdout)
        self.assertIn("mv ~/.local/state/jk ~/.local/state/jtk", result.stdout)
        self.assertTrue((home / ".config/jk/profiles").is_dir())
        self.assertFalse((home / ".config/jtk").exists())

    def test_no_migration_notice_when_there_is_nothing_to_migrate_or_the_new_folder_exists(self):
        home = fresh_home()
        self.assertNotIn("mv ", install(home).stdout)
        (home / ".config/jk").mkdir(parents=True)
        (home / ".config/jtk").mkdir(parents=True)
        result = install(home)
        self.assertNotIn("mv ~/.config/jk", result.stdout)
        self.assertIn("both ~/.config/jk and ~/.config/jtk exist", result.stderr)

    def test_old_environment_variables_are_called_out(self):
        home = fresh_home()
        env = dict(os.environ, HOME=str(home), JK_STATE_DIR="/somewhere", JK_CONFIG_DIR="/else")
        result = subprocess.run(["bash", str(ROOT / "install.sh")], env=env, capture_output=True, text=True)
        self.assertIn("JK_STATE_DIR is no longer read; use JTK_STATE_DIR", result.stderr)
        self.assertIn("JK_CONFIG_DIR is no longer read; use JTK_CONFIG_DIR", result.stderr)

    def test_an_unknown_argument_is_refused(self):
        self.assertEqual(install(fresh_home(), "--wat").returncode, 2)


if __name__ == "__main__":
    unittest.main()
