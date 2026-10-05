"""Evidence for finished work: commits, remote branches or URLs, resolved to links before anything is written.

A commit counts only if it is reachable from the remote's default branch (merged and pushed), and a branch only if it
exists on the remote. Nothing goes to the network: it reads the local refs of origin, so fetch first if they are stale.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
REMOTE_RE = re.compile(r"^(?:git@([^:]+):|https?://([^/]+)/)(.+?)(?:\.git)?/?$")


def web_base(remote_url: str) -> Optional[str]:
    match = REMOTE_RE.match(remote_url.strip())
    if not match:
        return None
    return f"https://{match.group(1) or match.group(2)}/{match.group(3)}"


def _git(repo: Path, *args: str) -> Optional[str]:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def _default_branch(repo: Path) -> Optional[str]:
    head = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head
    return next((ref for ref in ("origin/main", "origin/master")
                 if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}")), None)


def resolve(entries: List[str], repo: Path) -> Tuple[List[str], List[str]]:
    """Links for the entries that resolve, and one finding per entry that does not."""
    links: List[str] = []
    findings: List[str] = []
    in_git = _git(repo, "rev-parse", "--git-dir") is not None
    base = web_base(_git(repo, "remote", "get-url", "origin") or "") if in_git else None
    default = _default_branch(repo) if in_git else None
    for entry in entries:
        entry = entry.strip()
        if entry.startswith(("https://", "http://")):
            links.append(entry)
        elif not in_git:
            findings.append(f"{entry}: not a git repository ({repo}); give a URL instead")
        elif SHA_RE.match(entry):
            full = _git(repo, "rev-parse", "--verify", "--quiet", f"{entry}^{{commit}}")
            if not full:
                findings.append(f"{entry}: no such commit in {repo}")
            elif not default or _git(repo, "merge-base", "--is-ancestor", full, default) is None:
                findings.append(f"{entry}: not on {default or 'the remote default branch'}; push it (or fetch) first")
            elif not base:
                findings.append(f"{entry}: origin has no web URL to link to; give a URL instead")
            else:
                links.append(f"{base}/commit/{full}")
        elif base and _git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{entry}"):
            links.append(f"{base}/tree/{entry}")
        else:
            findings.append(f"{entry}: neither a commit, a branch on origin nor a URL")
    return links, findings
