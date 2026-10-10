"""Fixtures for the plan and apply tests: a workflow where every status of a fixture board can go to every other one, and
issues registered both in the fake Jira (what snapshot() sees) and in the shape a search returns (what plan selects)."""
from __future__ import annotations

import team_fixtures as fx
from jkan import roles


def workflow(jira, required=None) -> None:
    """Transition ids are '<from>><to>' (1>2 is Backlog -> En curso); `required` maps a transition id to its required fields."""
    for base in fx.BASE.values():
        ids = {str(base + n + 1): name for n, (_, name, _) in enumerate(fx.STATUSES)}
        for src in ids:
            jira.workflow[src] = [{"id": f"{src}>{dst}", "name": f"to {name}", "to": {"id": dst, "name": name},
                                   "required": list((required or {}).get(f"{src}>{dst}", []))}
                                  for dst, name in ids.items() if dst != src]


def put(jira, key: str, role: str, assignee=None, **over) -> dict:
    project = roles.project_of(key)
    status_id = str(fx.BASE[project] + fx.IDS[role])
    jira.put(key, status_id, fx.STATUSES[fx.IDS[role] - 1][1], assignee)
    return fx.at(key, role, assignee=assignee, **over)
