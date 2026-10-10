"""Views: the boards and the team a manager follows. One JSON per view under ~/.config/jtk/views/ (or
$JTK_CONFIG_DIR/views/). Written only by `jtk team setup`; the team reports read them."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from . import board_profile, queries

VERSION = 1
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


class BadView(ValueError):
    pass


def path_of(name: str, base: Optional[Path] = None) -> Path:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise BadView(f"not a view name: {name!r} (lower case letters, digits, - and _)")
    return (base or board_profile.config_dir()) / "views" / f"{name}.json"


def _check_team(team) -> None:
    if not isinstance(team, dict) or len(team) != 1:
        raise BadView("team must be {group: NAME} or {people: [{id, name}]}")
    if "group" in team:
        if not isinstance(team["group"], str) or not queries.GROUP.fullmatch(team["group"]):
            raise BadView(f"not a group name: {team['group']!r}")
    elif "people" in team:
        people = team["people"]
        if not (isinstance(people, list) and people and all(
                isinstance(p, dict) and isinstance(p.get("id"), str) and queries.ACCOUNT.fullmatch(p["id"])
                and isinstance(p.get("name"), str) for p in people)):
            raise BadView("people must be a non-empty list of {id, name}")
    else:
        raise BadView("team must be {group: NAME} or {people: [{id, name}]}")


def build(name: str, boards, team=None, stalled_days=7) -> dict:
    """A view, checked: every value that later goes into a JQL query is validated here, once."""
    path_of(name)
    if not isinstance(boards, list) or not boards:
        raise BadView("a view needs at least one board")
    for board in boards:
        if not isinstance(board, str) or not board_profile.KEY.fullmatch(board):
            raise BadView(f"not a project key: {board!r}")
    if len(set(boards)) != len(boards):
        raise BadView("a board is listed twice")
    if team is not None:
        _check_team(team)
    if isinstance(stalled_days, bool) or not isinstance(stalled_days, int) or not 1 <= stalled_days <= 365:
        raise BadView("stalled days must be a whole number from 1 to 365")
    return {"version": VERSION, "name": name, "boards": list(boards), "team": team, "stalled_days": stalled_days}


def save(view: dict, base: Optional[Path] = None) -> Path:
    return board_profile.write_json(path_of(view["name"], base), view)


def load(name: str, base: Optional[Path] = None) -> dict:
    path = path_of(name, base)
    if not path.is_file():
        raise BadView(f"no view {name!r}: run jtk team setup {name} --boards KEY[,KEY...]")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BadView(f"{path.name} is not valid JSON ({exc.msg})") from exc
    version = data.get("version") if isinstance(data, dict) else None
    if isinstance(version, bool) or not isinstance(version, int):
        raise BadView(f"{path.name} is not a view")
    if version > VERSION:
        raise BadView(f"{path.name} was written by a newer jtk (view version {version}); update jtk")
    if data.get("name") != name:
        raise BadView(f"{path.name} is not a view (wrong name)")
    try:
        return build(name, data.get("boards"), data.get("team"), data.get("stalled_days"))
    except BadView as exc:
        raise BadView(f"{path.name} is not a view ({exc})") from exc


def names(base: Optional[Path] = None) -> List[str]:
    folder = (base or board_profile.config_dir()) / "views"
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if NAME.fullmatch(p.stem))
