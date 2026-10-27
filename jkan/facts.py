"""What `jtk create` will do to each issue, said once. The console dry run, the --html preview and the approval window show
different amounts (a table, a Jira-like page, two lines a card) but read their words from here, so they cannot disagree:
where the issue ends after the pass, what the pass does to it, who gets it, and what a new issue is called until Jira
gives it a key."""
from __future__ import annotations

from typing import Optional

ME = {"me-done": "Vos · completa", "me-started": "Vos · en curso", "me": "Vos"}
NOBODY = {"none": "Sin asignar", "ask": "A decidir"}
UNCHANGED = "Sin cambios"  # an existing epic (--epic): the pass reads it and writes nothing to it


def status(op: dict, conv: dict) -> str:
    """Where the issue ends after this pass, not where Jira first puts it. An epic is done only when everything under it is (spec.plan)."""
    if op.get("existing"):
        return op["current_status"]
    if op.get("done"):
        return "Done"
    return "En progreso" if op.get("started") else conv.get("initial_status", "Backlog")


def action(op: dict, conv: dict) -> str:
    """«Crear», or «Crear y mover a …» when the pass also moves the issue: that second write is part of what a person approves."""
    if op.get("existing"):
        return UNCHANGED
    if op.get("done") or op.get("started"):
        return f"Crear y mover a {status(op, conv)}"
    return "Crear"


def assignee(op: dict, mine: Optional[str] = None) -> str:
    """Who the issue is for. `mine` is the approver's own name, which the approval window shows instead of «Vos»."""
    kind = op.get("assignee") or "ask"  # a plan nobody has run through sync.assignment yet
    if kind == "existing":
        return UNCHANGED
    if kind == "person":
        return op["person"]["name"] + ("" if op["person"].get("exact", True) else " · coincidencia aproximada")
    if kind in NOBODY:
        return NOBODY[kind]
    return mine or ME[kind]


def unassigned(op: dict) -> bool:
    return (op.get("assignee") or "ask") in NOBODY


def placeholder(position: int) -> str:
    """A new issue's name until Jira assigns the key: its place in the creation order, which is the order of every view."""
    return f"NUEVO-{position}"


def names(ops: list) -> dict:
    """ref -> how every view calls the issue: an existing epic by its key, a new issue NUEVO-n counting only new ones."""
    out, n = {}, 0
    for op in ops:
        if op.get("existing"):
            out[op["ref"]] = op["existing"]
        else:
            n += 1
            out[op["ref"]] = placeholder(n)
    return out
