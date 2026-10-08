"""JQL for the reports. Pure string builders: nothing here talks to Jira.

Everything that comes from outside (an account id, a project, issue keys) is checked before it is placed in a query.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Iterable, Optional

KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
PROJECT = re.compile(r"^[A-Z][A-Z0-9_]*$")
ACCOUNT = re.compile(r"^[A-Za-z0-9:_-]+$")


def _who(person: Optional[str]) -> str:
    if person is None:
        return "assignee = currentUser()"
    if not ACCOUNT.match(person):
        raise ValueError(f"not an account id: {person!r}")
    return f'assignee = "{person}"'


def _scope(project: Optional[str]) -> str:
    if not project:
        return ""
    if not PROJECT.match(project):
        raise ValueError(f"not a project key: {project!r}")
    return f" AND project = {project}"


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
