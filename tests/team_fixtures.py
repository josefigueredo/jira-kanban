"""Fixtures for the team report tests: two boards with profiles (a flow board TEAM and a help desk DESK), issues that
carry the role of their status, and a router that answers each kind of query the team reports make."""
from __future__ import annotations

from datetime import date

import shapes
from helpers import issue
from jkan import board_profile, roles, views

TODAY = date(2026, 10, 8)  # a Thursday; its week starts on 2026-10-05
ANA = {"id": "acc-ana", "name": "Ana Gómez"}
BETO = {"id": "acc-beto", "name": "Beto Ruiz"}

STATUSES = (("todo", "Backlog", "todo"), ("active", "En curso", "in_progress"), ("blocked", "Blocked", "in_progress"),
            ("waiting", "Esperando al cliente", "in_progress"), ("delivered", "Done", "done"),
            ("dropped", "Cancelado", "done"))
BASE = {"TEAM": 0, "DESK": 10}  # status ids: TEAM 1-6, DESK 11-16
IDS = {role: n + 1 for n, (role, _, _) in enumerate(STATUSES)}


def groups(offset: int) -> list:
    return [{"types": ["Tarea"], "statuses": [shapes.status(offset + n + 1, name, category)
                                                for n, (_, name, category) in enumerate(STATUSES)]}]


def profile(project: str, kind: str = "flow", wip_limit=None, decide_waiting: bool = True) -> dict:
    prof = board_profile.build(project, groups(BASE[project]), kind)
    if decide_waiting:
        board_profile.assign(prof, "waiting", ["Esperando al cliente"])
    return board_profile.set_wip_limit(prof, wip_limit)


def profiles(**limits) -> dict:
    return {"TEAM": profile("TEAM", wip_limit=limits.get("TEAM")), "DESK": profile("DESK", kind="helpdesk")}


def view(boards=("TEAM", "DESK"), team=None, name="plataforma", stalled_days=7) -> dict:
    return views.build(name, list(boards), {"group": "team"} if team is None else team, stalled_days)


def at(key: str, role, **over) -> dict:
    """An issue in the status that plays `role` on its board, already annotated (as team._fetch leaves it)."""
    project = roles.project_of(key)
    if role is None:  # a status the profile has not decided
        fields = {"status": "Revisión", "status_id": str(BASE[project] + 90), "category": "in_progress"}
    else:
        _, name, category = STATUSES[IDS[role] - 1]
        fields = {"status": name, "status_id": str(BASE[project] + IDS[role]), "category": category}
    fields.update(role=role, role_source="profile")
    fields.update(over)
    return issue(key, **fields)


def answers(open_=(), delivered=(), dropped=(), created=()):
    """A FakeJira.search_answer: tells the four kinds of team query apart by their text."""
    def answer(jql: str) -> list:
        if "created >=" in jql:
            return list(created)
        if "updated >=" in jql:
            return list(delivered if "status in (5)" in jql else dropped)
        return list(open_)
    return answer
