"""`jtk update`: is this install the latest, and bring it up to date.

The skills and the CLI are symlinks to one git clone (see install.sh), so «latest» means «my HEAD is origin/main». The
check asks the remote for the sha of main (one `git ls-remote`, about two seconds) and compares it with HEAD locally. The
answer to the question is cached for twelve hours as the remote's sha, not as a verdict, so pulling flips it at once; a
failed lookup is never cached. Updating is `git pull --ff-only` on a clean checkout of main: it never resets, merges or
force-pushes anything, and it stops with the reason when it cannot fast-forward."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Tuple

from . import render, state

TTL = 12 * 3600
BRANCH = "main"
TITLES = 5
TITLE_WIDTH = 72
FINDINGS_STATES = ("behind", "diverged")


class Result(NamedTuple):
    version: str
    state: str
    detail: str


def root() -> Path:
    """The clone this code runs from."""
    return Path(__file__).resolve().parent.parent


def _git(where: Path, *args: str, timeout: int = 20) -> Tuple[int, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # a credential prompt would hang a command that must answer
    try:
        done = subprocess.run(["git", *args], cwd=where, env=env, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout.strip() if done.returncode == 0 else (done.stderr or done.stdout).strip()


def _is_clone(where: Path) -> bool:
    return where.is_dir() and _git(where, "rev-parse", "--is-inside-work-tree")[1] == "true"


def version(where: Path) -> str:
    """«61f15ab 2026-10-11»: the short commit and its date, which is all a version means without tags."""
    code, out = _git(where, "log", "-1", "--format=%h %cs")
    return out if code == 0 and out else "unknown"


def _remote_sha(where: Path) -> Optional[str]:
    code, out = _git(where, "ls-remote", "origin", f"refs/heads/{BRANCH}")
    return out.split()[0] if code == 0 and out else None


def _cached(cache: Path, at: float) -> Optional[str]:
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        sha, when = data["remote_sha"], float(data["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return sha if isinstance(sha, str) and 0 <= at - when <= TTL else None


def _remember(cache: Path, sha: str, at: float) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"checked_at": at, "remote_sha": sha}), encoding="utf-8")
    except OSError:
        pass  # the cache only saves a round trip; not having it changes nothing


def _count(where: Path, spec: str) -> int:
    code, out = _git(where, "rev-list", "--count", spec)
    return int(out) if code == 0 and out.isdigit() else 0


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _clean(title: str) -> str:
    """A commit title is text from whoever can push, and the detail is read by an agent and printed in a terminal: control
    characters (escape codes, bidi overrides) become spaces and the length is capped."""
    flat = "".join(" " if unicodedata.category(c) in ("Cc", "Cf") else c for c in title)
    flat = " ".join(flat.split())
    return flat if len(flat) <= TITLE_WIDTH else flat[:TITLE_WIDTH - 1].rstrip() + "…"


def _assess(where: Path, sha: str, ver: str) -> Result:
    head = _git(where, "rev-parse", "HEAD")[1]
    if sha == head:
        return Result(ver, "up to date", "")
    if _git(where, "cat-file", "-e", f"{sha}^{{commit}}")[0] != 0 and _git(where, "fetch", "-q", "origin", BRANCH)[0] != 0:
        return Result(ver, "unknown", "could not reach origin to compare")
    behind, ahead = _count(where, f"HEAD..{sha}"), _count(where, f"{sha}..HEAD")
    if behind and ahead:
        return Result(ver, "diverged", f"{_plural(ahead, 'local commit')} and {_plural(behind, 'upstream commit')}; update by hand")
    if ahead:
        return Result(ver, "ahead", f"{_plural(ahead, 'local commit')} not published")
    if not behind:
        return Result(ver, "up to date", "")
    titles = [_clean(t) for t in _git(where, "log", f"-{TITLES}", "--format=%s", f"HEAD..{sha}")[1].splitlines()]
    more = "; …" if behind > TITLES else ""
    return Result(ver, "behind", f"{_plural(behind, 'commit')}: " + "; ".join(titles) + more)


def check(where: Path, cache: Optional[Path] = None, now: Callable[[], float] = time.time, fresh: bool = False) -> Result:
    ver = version(where)
    if not _is_clone(where):
        return Result(ver, "unknown", f"not a git clone ({where}); reinstall with install.sh")
    branch = _git(where, "branch", "--show-current")[1]
    if branch != BRANCH:  # a working branch is not «behind» anything: it was never meant to follow main
        return Result(ver, "unknown", f"on {_clean(branch) if branch else 'a detached HEAD'}, not {BRANCH}; nothing to compare")
    cache = cache or state.state_dir() / "update-check.json"
    sha = None if fresh else _cached(cache, now())
    if sha is None:
        sha = _remote_sha(where)
        if sha is None:
            return Result(ver, "unknown", "could not reach origin; try again later")
        _remember(cache, sha, now())
    return _assess(where, sha, ver)


def apply(where: Path, cache: Optional[Path] = None, now: Callable[[], float] = time.time) -> Tuple[int, str]:
    """Fast-forward the clone to origin/main. (exit code, what to tell the person)."""
    if not _is_clone(where):
        return 1, f"jtk update: {where} is not a git clone; reinstall with install.sh"
    branch = _git(where, "branch", "--show-current")[1]
    if branch != BRANCH:
        return 1, f"jtk update: the install is on {branch or 'a detached HEAD'}, not {BRANCH}; switch to {BRANCH} first"
    if _git(where, "status", "--porcelain")[1]:
        return 1, f"jtk update: uncommitted changes in {where}; commit or stash them first"
    result = check(where, cache=cache, now=now, fresh=True)
    if result.state == "unknown":
        return 1, f"jtk update: {result.detail}"
    if result.state == "diverged":
        return 1, f"jtk update: the install has diverged from origin ({result.detail})"
    if result.state != "behind":
        return 0, "jtk is already up to date" + (f" ({result.detail})" if result.detail else "")
    code, out = _git(where, "pull", "-q", "--ff-only", "origin", BRANCH, timeout=60)
    if code != 0:
        return 1, f"jtk update: git pull failed: {out}"
    return 0, (f"jtk updated to {version(where)}. The skills and the CLI are the same checkout, so the CLI is new now; "
               "start a new conversation so the agent re-reads the skill.")


def run(argv: List[str], root: Optional[Path] = None, cache: Optional[Path] = None,
        now: Callable[[], float] = time.time) -> int:
    parser = argparse.ArgumentParser(prog="jtk update", description=__doc__)
    parser.add_argument("--check", action="store_true", help="only say whether this install is the latest; changes nothing")
    parser.add_argument("--fresh", action="store_true", help="with --check: ask the remote now instead of trusting a check under 12 hours old")
    args = parser.parse_args(argv)
    where = root or globals()["root"]()
    if args.check:
        result = check(where, cache=cache, now=now, fresh=args.fresh)
        print("\n".join(render.columns([("Version", "State", "Detail"), tuple(result)])))
        return 1 if result.state in FINDINGS_STATES else 0
    code, message = apply(where, cache=cache, now=now)
    print(message)
    return code
