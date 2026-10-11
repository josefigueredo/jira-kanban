"""`jtk update`: is this install the latest, and bring it up to date. The install is a git clone that the skills and the CLI
both point at, so «latest» means «my HEAD is origin/main». Real git repositories, no doubles: a bare remote, the install
and a second clone that publishes."""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (isolates JTK_STATE_DIR)
from jkan import cli, update

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(where, *args):
    done = subprocess.run(["git", "-c", "core.fsync=none", "-c", "gc.auto=0", *args], cwd=where, env=GIT_ENV,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def commit(where, name, title):
    Path(where, name).write_text(title, encoding="utf-8")
    git(where, "add", "-A")
    git(where, "commit", "-q", "--no-verify", "-m", title)


TEMPLATE = {}


def setUpModule():
    """origin <- install and other, built once: ten git calls per test would triple the suite's time."""
    base = Path(tempfile.mkdtemp(prefix="jtk-update-template-"))
    origin, other, install = base / "origin.git", base / "other", base / "install"
    git(base, "init", "-q", "--bare", "-b", "main", str(origin))
    git(base, "clone", "-q", str(origin), str(other))
    git(other, "checkout", "-q", "-B", "main")
    commit(other, "a.txt", "first")
    git(other, "push", "-q", "origin", "main")
    git(base, "clone", "-q", str(origin), str(install))
    TEMPLATE["base"] = base


def tearDownModule():
    shutil.rmtree(TEMPLATE["base"], True)


class Repos(unittest.TestCase):
    """origin (bare) <- install (what the skills point at) and other (someone who publishes)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jtk-update-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for name in ("origin.git", "other", "install"):
            shutil.copytree(TEMPLATE["base"] / name, self.tmp / name)
        self.origin, self.other, self.install = self.tmp / "origin.git", self.tmp / "other", self.tmp / "install"
        for clone in (self.other, self.install):
            git(clone, "remote", "set-url", "origin", str(self.origin))
        self.cache = self.tmp / "update-check.json"
        self.clock = 1_000_000.0

    def publish(self, *titles):
        for title in titles:
            commit(self.other, f"{title}.txt", title)
        git(self.other, "push", "-q", "origin", "main")

    def check(self, **kw):
        return update.check(self.install, cache=self.cache, now=lambda: self.clock, **kw)


class CheckTest(Repos):
    def test_an_install_at_origin_main_is_up_to_date(self):
        result = self.check()
        self.assertEqual(result.state, "up to date")
        self.assertEqual(result.detail, "")

    def test_an_install_behind_says_how_many_and_what(self):
        self.publish("second", "third")
        result = self.check()
        self.assertEqual(result.state, "behind")
        self.assertIn("2 commits", result.detail)
        self.assertLess(result.detail.index("third"), result.detail.index("second"))  # newest first

    def test_one_commit_is_not_plural(self):
        self.publish("second")
        self.assertIn("1 commit:", self.check().detail)

    def test_at_most_five_titles_are_listed(self):
        self.publish(*[f"c{i}" for i in range(8)])
        detail = self.check().detail
        self.assertIn("8 commits", detail)
        self.assertEqual(len(re.findall(r"\bc\d\b", detail)), 5)

    def test_local_commits_nobody_published_are_ahead_not_behind(self):
        commit(self.install, "mine.txt", "mine")
        result = self.check()
        self.assertEqual(result.state, "ahead")
        self.assertIn("1 local commit", result.detail)

    def test_both_sides_moved_is_diverged(self):
        commit(self.install, "mine.txt", "mine")
        self.publish("theirs")
        self.assertEqual(self.check().state, "diverged")

    def test_a_folder_that_is_not_a_clone_is_unknown_and_says_why(self):
        loose = self.tmp / "loose"
        loose.mkdir()
        result = update.check(loose, cache=self.cache, now=lambda: self.clock)
        self.assertEqual(result.state, "unknown")
        self.assertIn("not a git clone", result.detail)

    def test_an_unreachable_remote_is_unknown_and_never_raises(self):
        git(self.install, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        result = self.check()
        self.assertEqual(result.state, "unknown")
        self.assertIn("could not reach", result.detail)

    def test_a_hostile_commit_title_reaches_the_detail_clean_and_short(self):
        # The detail is read by an agent and printed in a terminal: a title is data from whoever can push, not text to trust.
        commit(self.other, "x.txt", "feat: \x1b[31mred\x1b[0m\ttab \u202eevil " + "z" * 300)
        git(self.other, "push", "-q", "origin", "main")
        detail = self.check().detail
        title = detail.split(": ", 1)[1]
        self.assertNotRegex(detail, r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]")
        self.assertLessEqual(len(title), 72)
        self.assertTrue(title.endswith("…"))
        self.assertIn("red", title)

    def test_a_short_clean_title_is_left_alone(self):
        self.publish("fix: a plain title")
        self.assertIn("fix: a plain title", self.check().detail)

    def test_an_install_on_another_branch_is_unknown_without_asking_the_remote(self):
        git(self.install, "checkout", "-q", "-b", "feat/x")
        shutil.rmtree(self.origin)  # if it asked, the answer would be «could not reach»
        result = self.check()
        self.assertEqual(result.state, "unknown")
        self.assertIn("feat/x", result.detail)
        self.assertIn("not main", result.detail)

    def test_a_detached_head_is_unknown_too(self):
        git(self.install, "checkout", "-q", "--detach")
        result = self.check()
        self.assertEqual(result.state, "unknown")
        self.assertIn("detached", result.detail)

    def test_the_version_is_the_short_commit_and_its_date(self):
        self.assertRegex(update.version(self.install), r"^[0-9a-f]{7,} \d{4}-\d{2}-\d{2}$")
        self.assertEqual(update.version(self.tmp / "nowhere"), "unknown")


class CacheTest(Repos):
    def test_a_second_check_inside_the_window_does_not_ask_the_remote(self):
        self.assertEqual(self.check().state, "up to date")
        shutil.rmtree(self.origin)
        self.clock += 3600
        self.assertEqual(self.check().state, "up to date")  # answered from the cache: the remote is gone

    def test_fresh_asks_again_whatever_the_cache_says(self):
        self.check()
        shutil.rmtree(self.origin)
        self.assertEqual(self.check(fresh=True).state, "unknown")

    def test_after_twelve_hours_it_asks_again(self):
        self.check()
        shutil.rmtree(self.origin)
        self.clock += update.TTL + 1
        self.assertEqual(self.check().state, "unknown")

    def test_a_failed_lookup_is_not_cached(self):
        git(self.install, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        self.assertEqual(self.check().state, "unknown")
        self.assertFalse(self.cache.exists())
        git(self.install, "remote", "set-url", "origin", str(self.origin))
        self.assertEqual(self.check().state, "up to date")

    def test_the_cache_knows_the_remote_not_the_verdict_so_pulling_flips_it(self):
        self.publish("second")
        self.assertEqual(self.check().state, "behind")
        git(self.install, "pull", "-q", "--ff-only", "origin", "main")
        shutil.rmtree(self.origin)
        self.assertEqual(self.check().state, "up to date")  # same cached remote sha, new local HEAD

    def test_a_broken_cache_file_is_ignored(self):
        self.cache.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.check().state, "up to date")


class ApplyTest(Repos):
    def apply(self):
        return update.apply(self.install)

    def test_it_fast_forwards_to_origin_main_and_says_to_start_a_new_conversation(self):
        self.publish("second")
        code, message = self.apply()
        self.assertEqual(code, 0)
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), git(self.other, "rev-parse", "HEAD"))
        self.assertIn("new conversation", message)

    def test_when_already_current_it_changes_nothing(self):
        before = git(self.install, "rev-parse", "HEAD")
        code, message = self.apply()
        self.assertEqual((code, git(self.install, "rev-parse", "HEAD")), (0, before))
        self.assertIn("already", message)

    def test_uncommitted_changes_stop_it_and_are_left_alone(self):
        self.publish("second")
        Path(self.install, "a.txt").write_text("edited", encoding="utf-8")
        before = git(self.install, "rev-parse", "HEAD")
        code, message = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("uncommitted", message)
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), before)
        self.assertEqual(Path(self.install, "a.txt").read_text(encoding="utf-8"), "edited")

    def test_another_branch_stops_it(self):
        self.publish("second")
        git(self.install, "checkout", "-q", "-b", "feat/x")
        code, message = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("feat/x", message)

    def test_a_diverged_install_stops_it_and_never_rewrites_history(self):
        commit(self.install, "mine.txt", "mine")
        self.publish("theirs")
        mine = git(self.install, "rev-parse", "HEAD")
        code, message = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("diverged", message)
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), mine)

    def test_an_unreachable_remote_is_reported_not_raised(self):
        git(self.install, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        code, message = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("could not reach", message)

    def test_a_folder_that_is_not_a_clone_cannot_be_updated(self):
        loose = self.tmp / "loose"
        loose.mkdir()
        code, message = update.apply(loose)
        self.assertEqual(code, 1)
        self.assertIn("not a git clone", message)


class RunTest(Repos):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = update.run(list(argv), root=self.install, cache=self.cache, now=lambda: self.clock)
        return code, out.getvalue()

    def test_check_prints_version_state_and_detail_in_aligned_columns(self):
        self.publish("second")
        code, out = self.run_cli("--check")
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["Version", "State", "Detail"])
        self.assertIn("behind", lines[1])
        self.assertEqual(code, 1)  # behind is a finding, like the other reports

    def test_check_exits_zero_when_current_and_when_unknown(self):
        self.assertEqual(self.run_cli("--check")[0], 0)
        git(self.install, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        code, out = self.run_cli("--check", "--fresh")
        self.assertEqual(code, 0)
        self.assertIn("unknown", out)

    def test_without_flags_it_updates(self):
        self.publish("second")
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), git(self.other, "rev-parse", "HEAD"))
        self.assertIn("new conversation", out)


class WiringTest(unittest.TestCase):
    def test_version_flag_prints_the_install_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--version"]), 0)
        self.assertRegex(out.getvalue().strip(), r"^jtk ([0-9a-f]{7,} \d{4}-\d{2}-\d{2}|unknown)$")

    def test_update_is_dispatched_with_its_own_arguments_and_needs_no_jira(self):
        def no_credentials(project):
            raise AssertionError("update must not build a Jira client")
        with mock.patch.object(update, "run", return_value=1) as run:
            self.assertEqual(cli.main(["update", "--check", "--fresh"], client=no_credentials), 1)
        run.assert_called_once_with(["--check", "--fresh"])


if __name__ == "__main__":
    unittest.main()
