"""Per-board profiles: which role each status plays. One JSON per Jira project under ~/.config/jk/profiles/
(or $JK_CONFIG_DIR/profiles/). Written only by `jk board setup` and `jk board set`; nobody edits them by hand."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from . import roles

VERSION = 1
KINDS = ("flow", "scrum", "helpdesk")
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


class BadSelection(ValueError):
    pass


def config_dir() -> Path:
    return Path(os.environ.get("JK_CONFIG_DIR") or Path.home() / ".config" / "jk")


def path_of(project: str, base: Optional[Path] = None) -> Path:
    if not KEY.match(project):
        raise ValueError(f"not a project key: {project!r}")
    return (base or config_dir()) / "profiles" / f"{project}.json"


def fingerprint(statuses: List[dict]) -> str:
    return "sha256:" + hashlib.sha256(",".join(sorted({s["id"] for s in statuses})).encode()).hexdigest()


def build(project: str, groups: List[dict], kind: Optional[str], existing: Optional[dict] = None) -> dict:
    """A profile for what Jira says now. A status a person decided keeps that role (matched by id, so a rename does
    not lose it); every other status is proposed again. Statuses Jira no longer has are dropped."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    decided = {s["id"]: s for s in (existing or {}).get("statuses", []) if s.get("by") == "human"}
    statuses: List[dict] = []
    seen: set = set()
    for group in groups:
        for status in group["statuses"]:
            if status["id"] in seen:
                continue
            seen.add(status["id"])
            if status["id"] in decided:
                statuses.append(dict(decided[status["id"]], name=status["name"], category=status["category"]))
                continue
            p = roles.propose(status)
            statuses.append({"id": status["id"], "name": status["name"], "category": status["category"],
                             "role": p["role"], "by": "proposal" if p["role"] else None,
                             "suggest": p["suggest"], "why": p["why"]})
    return {"version": VERSION, "project": project, "kind": kind or (existing or {}).get("kind") or "flow",
            "access": "full", "wip_limit": (existing or {}).get("wip_limit"), "fingerprint": fingerprint(statuses),
            "workflows": [{"types": g["types"], "status_ids": [s["id"] for s in g["statuses"]]} for g in groups],
            "statuses": statuses}


def open_statuses(profile: dict) -> List[dict]:
    return [s for s in profile["statuses"] if not s["role"]]


def _select(profile: dict, token: str) -> List[dict]:
    if token.startswith("id:"):
        return [s for s in profile["statuses"] if s["id"] == token[3:]]
    wanted = roles.normalize(token)
    return [s for s in profile["statuses"] if roles.normalize(s["name"]) == wanted]


def assign(profile: dict, role: str, tokens: List[str]) -> dict:
    """Give `role` to the statuses named by `tokens` (a name, or id:<id> when two statuses share a name). All or
    nothing: one bad token changes no status."""
    if role not in roles.ROLES:
        raise BadSelection(f"unknown role {role!r}; one of {', '.join(roles.ROLES)}")
    chosen: List[dict] = []
    for token in tokens:
        found = _select(profile, token)
        if not found:
            raise BadSelection(f"no status {token!r} in {profile['project']}")
        if len(found) > 1:
            ids = ", ".join(f"id:{s['id']}" for s in found)
            raise BadSelection(f"{token!r} matches {len(found)} statuses ({ids}); use id:<id>")
        chosen.append(found[0])
    for status in chosen:
        status["role"], status["by"] = role, "human"
    return profile


def save(profile: dict, base: Optional[Path] = None) -> Path:
    path = path_of(profile["project"], base)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a profile")
    if data.get("version", 0) > VERSION:
        raise ValueError(f"{path.name} was written by a newer jk (profile version {data['version']}); update jk")
    return data


def load(project: str, base: Optional[Path] = None) -> Optional[dict]:
    path = path_of(project, base)
    return _read(path) if path.is_file() else None


def load_all(base: Optional[Path] = None) -> Dict[str, dict]:
    """Every readable profile by project key; a file that cannot be read is skipped (its project reads as 'Sin perfil')."""
    folder = (base or config_dir()) / "profiles"
    found: Dict[str, dict] = {}
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                found[path.stem] = _read(path)
            except (OSError, ValueError):
                continue
    return found
