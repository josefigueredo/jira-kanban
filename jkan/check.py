"""`jtk create --check`: what the skill needs to know before it drafts a spec, measured offline in one call.

Three facts, each a (check, result, detail) row: whether a WayOfWork plan owns the epics, which Jira project applies, and
whether an epic already covers the work (a `**Jira Epic:** KEY` in specs/*/spec.md, or a key in the branch name). A key
that only appears in the conversation is the one thing a script cannot see; the detail says so."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

KEY = r"[A-Z][A-Z0-9]+-\d+"
DECLARED = re.compile(r"\*\*Jira Epic:\*\*\s*\[?(" + KEY + ")")
IN_BRANCH = re.compile(r"\b(" + KEY + r")\b", re.IGNORECASE)

Row = Tuple[str, str, str]


def _branch(project: Path) -> str:
    try:
        done = subprocess.run(["git", "branch", "--show-current"], cwd=project, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _epics(project: Path, branch: str) -> List[Tuple[str, str]]:
    """(key, where) in the order found, each key once: the specs first, then the branch."""
    found: List[Tuple[str, str]] = []
    for spec in sorted(project.glob("specs/*/spec.md")):
        for key in DECLARED.findall(spec.read_text(encoding="utf-8", errors="replace")):
            found.append((key, spec.relative_to(project).as_posix()))
    for key in IN_BRANCH.findall(branch):
        found.append((key.upper(), f"branch {branch}"))
    return found


def preflight(project: Path, conv: dict, branch: Optional[str] = None, flag: Optional[str] = None) -> List[Row]:
    branch = _branch(project) if branch is None else branch
    rows: List[Row] = []
    if (project / "wow" / "plan" / "manifest.json").is_file():
        rows.append(("wow plan", "yes", "wow/plan/manifest.json: Product Brain's export creates the epics; ask before using jtk create"))
    else:
        rows.append(("wow plan", "no", "no wow/plan/manifest.json"))
    if flag:
        rows.append(("jira project", flag, "--jira-project"))
    elif conv.get("project"):
        rows.append(("jira project", conv["project"], ".jira-team-kit/conventions.json"))
    else:
        rows.append(("jira project", "none", "ask the person which project and pass --jira-project KEY"))
    where: dict = {}
    for key, source in _epics(project, branch):
        if source not in where.setdefault(key, []):
            where[key].append(source)
    if where:
        rows.append(("existing epic", ", ".join(where), "; ".join(f"{key} in {', '.join(s)}" for key, s in where.items())
                     + ". If one covers the work, ask before creating; to mirror it run jtk pull KEY"))
    else:
        rows.append(("existing epic", "none", "none in specs/*/spec.md or the branch; a key in the conversation is not checked here"))
    return rows
