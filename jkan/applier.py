"""Apply: runs a saved plan exactly, after a person approved it. Before each write it rereads the issue and leaves alone
anything that is no longer as planned. One issue never stops the others; the log makes running it again safe."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from . import plan as plan_mod
from . import state

GOOD = ("applied", "already there", "already applied")


def _move(jira, item: dict) -> str:
    key, snap = item["key"], jira.snapshot(item["key"])
    if snap["status_id"] == item["to"]["id"]:
        return "already there"
    if snap["status_id"] != item["from"]["id"]:
        return "changed"
    if not any(t["id"] == item["transition"] and t["to"]["id"] == item["to"]["id"] for t in jira.transitions(key)):
        return "changed"
    jira.transition_by_id(key, item["transition"])
    return "applied"


def _assign(jira, item: dict) -> str:
    owner = jira.snapshot(item["key"])["assignee"]
    now_id = owner["id"] if owner else None
    target = item["to"]["id"] if item["to"] else None
    if now_id == target:
        return "already there"
    if now_id != (item["from"]["id"] if item["from"] else None):
        return "changed"
    jira.assign(item["key"], target)
    return "applied"


def _parent(jira, item: dict) -> str:
    current = jira.get(item["key"]).get("parent")
    if current == item["to"]["key"]:
        return "already there"
    if current != (item["from"]["key"] if item["from"] else None):
        return "changed"
    jira.set_parent(item["key"], item["to"]["key"])
    return "applied"


def _one(jira, plan: dict, item: dict) -> str:
    try:
        if plan["kind"] == "move":
            return _move(jira, item)
        if plan["kind"] == "assign":
            return _assign(jira, item)
        if plan["kind"] == "parent":
            return _parent(jira, item)
        jira.add_comment(item["key"], plan["options"]["text"])
        return "applied"
    except Exception as exc:  # noqa: BLE001 — one issue never stops the rest; the reason goes to the table and the log
        return f"error: {exc}"


def _entry(plan: dict, item: dict, result: str) -> dict:
    base = {"command": "apply", "plan": plan["id"], "key": item["key"], "action": plan["kind"], "result": result}
    return base if plan["kind"] == "comment" else dict(base, de=item["from"], a=item["to"])


def run(jira, plan: dict, confirm: Callable, command: str,
        now: Optional[Callable[[], str]] = None) -> Tuple[List[dict], int]:
    """Apply what the log does not already mark done. `confirm` (guard.confirm) raises NotApproved before any write."""
    done = state.applied(plan["id"])
    pending = [i for i in plan["items"] if i["key"] not in done]
    results = {i["key"]: "already applied" for i in plan["items"] if i["key"] in done}
    unlogged = False
    if pending and not state.can_log():
        message = "error: the log cannot be written, so nothing was done (check the state folder)"
        return [{"key": i["key"], "result": results.get(i["key"], message)} for i in plan["items"]], 2
    if pending:
        confirm(len(pending), plan_mod.summary(plan, [i["key"] for i in pending],
                                               browse=getattr(jira, "browse_url", None)), command)
        for item in pending:
            result = _one(jira, plan, item)
            if result == "applied" or result.startswith("error"):
                logged = state.log_write(_entry(plan, item, "ok" if result == "applied" else result), now)
                if not logged:
                    unlogged = True
                    result += " (not recorded in the log: re-running would repeat it)"
            results[item["key"]] = result
    outcomes = [{"key": i["key"], "result": results[i["key"]]} for i in plan["items"]]
    if unlogged:
        return outcomes, 2
    return outcomes, 0 if all(o["result"] in GOOD for o in outcomes) else 1


def render(outcomes: List[dict]) -> str:
    width = max((len(o["key"]) for o in outcomes), default=0)
    return "\n".join(f"{o['key']:<{width}}  {o['result']}" for o in outcomes)
