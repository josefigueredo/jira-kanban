"""Per-board profiles: which role each status plays. One JSON per Jira project under ~/.config/jk/profiles/
(or $JK_CONFIG_DIR/profiles/). Written only by `jk board setup` and `jk board set`; nobody edits them by hand."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import roles

VERSION = 1
KINDS = ("flow", "scrum", "helpdesk")
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


class BadSelection(ValueError):
    pass


class BadProfile(ValueError):
    """A profile file that is not valid JSON or does not have the shape of a profile."""


class NewerProfile(ValueError):
    """A profile written by a newer jk: it must be neither misread nor overwritten."""


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


def _wip_ok(value) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 1)


def set_wip_limit(profile: dict, value: Optional[int]) -> dict:
    """The most work a person should have in flight on this board; None means no limit."""
    if not _wip_ok(value):
        raise BadSelection("the WIP limit must be a whole number of 1 or more, or none")
    profile["wip_limit"] = value
    return profile


def write_json(path: Path, data: dict) -> Path:
    """Write `data` as JSON atomically (a temporary file in the same folder, then a rename); no stray file on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def save(profile: dict, base: Optional[Path] = None) -> Path:
    return write_json(path_of(profile["project"], base), profile)


def _read(path: Path) -> dict:
    """The profile in `path`, or BadProfile / NewerProfile; what the reports use is checked here, once."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BadProfile(f"{path.name} is not valid JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise BadProfile(f"{path.name} is not a profile")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise BadProfile(f"{path.name} is not a profile (no valid version)")
    if version > VERSION:
        raise NewerProfile(f"{path.name} was written by a newer jk (profile version {version}); update jk")
    statuses = data.get("statuses")
    if not (data.get("project") == path.stem and isinstance(statuses, list) and _wip_ok(data.get("wip_limit"))
            and all(isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("name"), str)
                    and (s.get("role") is None or s.get("role") in roles.ROLES) for s in statuses)):
        raise BadProfile(f"{path.name} is not a profile (wrong shape)")
    return data


def load(project: str, base: Optional[Path] = None) -> Optional[dict]:
    path = path_of(project, base)
    return _read(path) if path.is_file() else None


def scan(base: Optional[Path] = None) -> Tuple[Dict[str, dict], Dict[str, Tuple[str, str]]]:
    """(profiles, problems): every readable profile by project key, and for each file that is not, ('newer' | 'bad', why)."""
    folder = (base or config_dir()) / "profiles"
    found: Dict[str, dict] = {}
    problems: Dict[str, Tuple[str, str]] = {}
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                found[path.stem] = _read(path)
            except NewerProfile as exc:
                problems[path.stem] = ("newer", str(exc))
            except (OSError, ValueError) as exc:
                problems[path.stem] = ("bad", str(exc))
    return found, problems


def load_all(base: Optional[Path] = None) -> Dict[str, dict]:
    return scan(base)[0]
