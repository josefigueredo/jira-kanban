"""JQL for the reports. Pure string builders: nothing here talks to Jira.

Everything that comes from outside (an account id, a project, issue keys) is checked before it is placed in a query.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Dict, Iterable, List, Optional, Union

KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
PROJECT = re.compile(r"^[A-Z][A-Z0-9_]*$")
ACCOUNT = re.compile(r"^[A-Za-z0-9:_-]+$")
GROUP = re.compile(r"\w[\w ._@:()-]{0,99}")  # letters of any language; never a quote, a backslash or a line break
STATUS_ID = re.compile(r"\d+")


def _who(person: Optional[str]) -> str:
    if person is None:
        return "assignee = currentUser()"
    if not ACCOUNT.match(person):
        raise ValueError(f"not an account id: {person!r}")
    return f'assignee = "{person}"'


def _scope(project: Optional[Union[str, List[str]]]) -> str:
    """One project key, or a view's list of them."""
    if not project:
        return ""
    keys = [project] if isinstance(project, str) else list(project)
    for key in keys:
        if not PROJECT.match(key):
            raise ValueError(f"not a project key: {key!r}")
    return f" AND project = {keys[0]}" if len(keys) == 1 else f" AND project in ({', '.join(keys)})"


def _keys(keys: Iterable[str]) -> str:
    keys = list(keys)
    bad = [k for k in keys if not KEY.match(k)]
    if bad or not keys:
        raise ValueError(f"not issue keys: {bad or 'empty list'}")
    return ", ".join(keys)


def changed_in(person: Optional[str], since: _dt.date, until: _dt.date, project: Optional[str] = None) -> str:
    """Issues of `person` whose status category changed to Done or In Progress between two days, both included."""
    return (f'{_who(person)}{_scope(project)} AND statusCategory in ("Done", "In Progress") '
            f'AND statusCategoryChangedDate >= "{since.isoformat()}" '
            f'AND statusCategoryChangedDate < "{(until + _dt.timedelta(days=1)).isoformat()}" '
            "ORDER BY statusCategoryChangedDate DESC")


def open_of(person: Optional[str], project: Optional[str] = None) -> str:
    return f"{_who(person)}{_scope(project)} AND statusCategory != Done ORDER BY priority DESC, duedate ASC"


def done_since(person: Optional[str], since: _dt.date, project: Optional[str] = None) -> str:
    return (f'{_who(person)}{_scope(project)} AND statusCategory = Done '
            f'AND statusCategoryChangedDate >= "{since.isoformat()}" ORDER BY statusCategoryChangedDate DESC')


def unowned_in(epic_keys: Iterable[str]) -> str:
    return (f"parent in ({_keys(epic_keys)}) AND assignee is EMPTY AND statusCategory != Done "
            "ORDER BY priority DESC")


def by_keys(keys: Iterable[str]) -> str:
    return f"key in ({_keys(keys)})"


# ---- team reports: JQL built from the roles of each board's profile -------------------------------------------------

def _id_list(ids: Iterable[str]) -> str:
    ids = set(ids)
    bad = sorted(i for i in ids if not STATUS_ID.fullmatch(i))
    if bad:
        raise ValueError(f"not status ids: {bad}")
    return ", ".join(sorted(ids, key=int))


def _board(board: str) -> str:
    if not PROJECT.fullmatch(board):
        raise ValueError(f"not a project key: {board!r}")
    return board


def _ids_with(profile: dict, wanted: Iterable[str]) -> List[str]:
    return [s["id"] for s in profile["statuses"] if s["role"] in wanted]


def team_scope(team: Optional[dict], include_unassigned: bool = False) -> Optional[str]:
    """JQL for "assigned to the team"; None when the view has no team (everybody counts)."""
    if not team:
        return None
    if "group" in team:
        if not GROUP.fullmatch(team["group"]):
            raise ValueError(f"not a group name: {team['group']!r}")
        clause = f'assignee in membersOf("{team["group"]}")'
    else:
        ids = [p["id"] for p in team["people"]]
        bad = [i for i in ids if not ACCOUNT.fullmatch(i)]
        if bad:
            raise ValueError(f"not account ids: {bad}")
        clause = "assignee in (" + ", ".join(f'"{i}"' for i in ids) + ")"
    return f"({clause} OR assignee is EMPTY)" if include_unassigned else clause


def team_open(boards: List[str], profiles: Dict[str, dict], team: Optional[dict]) -> str:
    """Open work in the boards: everything that is not delivered or dropped, so statuses without a role come back too
    (as «sin rol»). The team's work and what nobody owns; the ids go unquoted, which is what Jira reads as ids."""
    parts = []
    for board in boards:
        closed = _ids_with(profiles[board], ("delivered", "dropped"))
        parts.append(f"(project = {_board(board)} AND status not in ({_id_list(closed)}))" if closed
                     else f"(project = {_board(board)})")
    scope = team_scope(team, include_unassigned=True)
    return "(" + " OR ".join(parts) + ")" + (f" AND {scope}" if scope else "") + " ORDER BY updated DESC"


def team_closed(boards: List[str], profiles: Dict[str, dict], team: Optional[dict], wanted: Iterable[str],
                since: _dt.date) -> Optional[str]:
    """Issues in a status whose role is in `wanted` (delivered, dropped) and updated since a day, assigned to the team.
    None when no board has such a status. `updated` is a superset of the delivery day: the report narrows it."""
    parts = []
    for board in boards:
        ids = _ids_with(profiles[board], tuple(wanted))
        if ids:
            parts.append(f"(project = {_board(board)} AND status in ({_id_list(ids)}))")
    if not parts:
        return None
    scope = team_scope(team)
    return ("(" + " OR ".join(parts) + f') AND updated >= "{since.isoformat()}"' + (f" AND {scope}" if scope else "")
            + " ORDER BY updated DESC")


def team_created(boards: List[str], since: _dt.date, until: _dt.date) -> str:
    projects = ", ".join(_board(b) for b in boards)
    return (f'project in ({projects}) AND created >= "{since.isoformat()}" '
            f'AND created < "{(until + _dt.timedelta(days=1)).isoformat()}" ORDER BY created DESC')
