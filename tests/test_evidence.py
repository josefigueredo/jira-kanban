from __future__ import annotations

import subprocess
import unittest

from helpers import CONVENTIONS, FakeJira, make_project
from jkan import evidence, spec, sync

REMOTE = "git@github.com:org/repo.git"
WEB = "https://github.com/org/repo"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@x", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def repo_with_remote():
    """Two commits on main, the first one pushed (origin/main), plus a pushed branch origin/feat-x."""
    repo = make_project()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "one")
    pushed = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "-q", "--allow-empty", "-m", "two")
    local_only = git(repo, "rev-parse", "HEAD")
    git(repo, "remote", "add", "origin", REMOTE)
    git(repo, "update-ref", "refs/remotes/origin/main", pushed)
    git(repo, "update-ref", "refs/remotes/origin/feat-x", local_only)
    return repo, pushed, local_only


class WebBaseTest(unittest.TestCase):
    def test_ssh_and_https_remotes_become_the_web_url(self):
        self.assertEqual(evidence.web_base("git@github.com:org/repo.git"), WEB)
        self.assertEqual(evidence.web_base("https://github.com/org/repo"), WEB)
        self.assertIsNone(evidence.web_base("/tmp/bare.git"))


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.pushed, self.local_only = repo_with_remote()

    def test_a_pushed_commit_becomes_a_permalink_to_the_full_sha(self):
        links, findings = evidence.resolve([self.pushed[:7]], self.repo)
        self.assertEqual((links, findings), ([f"{WEB}/commit/{self.pushed}"], []))

    def test_a_commit_not_on_the_remote_default_branch_is_a_finding(self):
        links, findings = evidence.resolve([self.local_only[:7]], self.repo)
        self.assertEqual(links, [])
        self.assertIn(f"{self.local_only[:7]}: not on origin/main", findings[0])

    def test_unknown_commit_and_unknown_branch_are_findings(self):
        _, findings = evidence.resolve(["deadbee", "nope"], self.repo)
        self.assertIn("deadbee: no such commit", findings[0])
        self.assertIn("nope: neither a commit, a branch on origin nor a URL", findings[1])

    def test_a_remote_branch_and_a_url_are_kept(self):
        links, findings = evidence.resolve(["feat-x", "https://example.com/pr/9"], self.repo)
        self.assertEqual((links, findings), ([f"{WEB}/tree/feat-x", "https://example.com/pr/9"], []))

    def test_outside_a_git_repo_only_urls_resolve(self):
        links, findings = evidence.resolve(["abc1234", "https://example.com/x"], make_project())
        self.assertEqual(links, ["https://example.com/x"])
        self.assertIn("abc1234: not a git repository", findings[0])


class EvidenceSpecTest(unittest.TestCase):
    def test_done_needs_evidence_and_a_subtask_inherits_its_parents(self):
        bad = {"epic": {"summary": "e"}, "items": [
            {"type": "task", "summary": "sin", "done": True},
            {"type": "task", "summary": "con", "done": True, "evidence": ["abc1234"], "subtasks": [{"summary": "hereda"}]},
            {"type": "task", "summary": "abierta", "subtasks": [{"summary": "hecha sola", "done": True}]},
            {"type": "task", "summary": "mal", "evidence": "abc1234"}]}
        findings = spec.validate(bad, CONVENTIONS)
        self.assertEqual(findings, [
            "items[0]: done needs evidence: the commits, branch or URL that show it (\"evidence\": [...])",
            "items[2].subtasks[0]: done needs evidence: the commits, branch or URL that show it (\"evidence\": [...])",
            "items[3]: evidence must be a list of commits, branches or URLs"])
        ops = {op["ref"]: op for op in spec.plan(bad, CONVENTIONS)}
        self.assertEqual(ops["items[1].subtasks[0]"]["evidence"], ["abc1234"])


class EvidenceCreateTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.pushed, self.local_only = repo_with_remote()

    def test_the_description_gets_the_permalinks_in_the_dry_run_too(self):
        one = {"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "done": True,
                                                    "evidence": [self.pushed[:7]]}]}
        result = sync.create(FakeJira(), self.repo, one, CONVENTIONS, apply=False)
        self.assertTrue(result["ops"][1]["description"].endswith(f"Evidencia:\n- {WEB}/commit/{self.pushed}"))

    def test_unresolved_evidence_refuses_before_any_write(self):
        one = {"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "done": True,
                                                    "evidence": [self.local_only[:7]]}]}
        jira = FakeJira()
        with self.assertRaises(ValueError) as caught:
            sync.create(jira, self.repo, one, CONVENTIONS, apply=True, assign_open=True)
        self.assertIn("items[0]: " + self.local_only[:7], str(caught.exception))
        self.assertEqual(jira.writes, [])


if __name__ == "__main__":
    unittest.main()
