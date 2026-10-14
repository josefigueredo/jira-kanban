"""Plans: what `jtk plan move|assign|comment|revert` decides about a selection of issues, written as a file `jtk apply` runs
exactly. Planning only reads Jira. Everything a write needs (the status it leaves and reaches, the transition id, the person)
is resolved here, once; apply never evaluates the query again."""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from . import approval, board_profile, roles, state, team

KEY = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
TO_ROLES = ("todo", "active", "blocked", "waiting", "delivered", "dropped")
CLOSING = ("delivered", "dropped")
DEFAULT_MAX, LIMIT_MAX = 25, 200
MAX_TEXT = 30000


class Refused(ValueError):
    """The plan cannot be made as asked; nothing was saved."""


def check_max(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_MAX
    if not 1 <= value <= LIMIT_MAX:
        raise Refused(f"--max must be between 1 and {LIMIT_MAX}")
    return value


def select(jira, view: dict, profiles: Dict[str, dict], conv: dict, open_issues: List[dict], today, keys: List[str],
           unassigned: bool, older_than: Optional[int], role: Optional[str], limit: int) -> List[dict]:
    """The issues the plan is about: what the filters pick out of the open issues, then the explicit keys, each once."""
    filtering = unassigned or older_than is not None or role is not None
    if not keys and not filtering:
        raise Refused("say which issues: pass keys or at least one of --unassigned, --older-than, --role")
    for key in keys:
        if not KEY.fullmatch(key):
            raise Refused(f"{key!r} is not an issue key")
        if roles.project_of(key) not in view["boards"]:
            raise Refused(f"{key} is not in the boards of view {view['name']!r} ({', '.join(view['boards'])})")
    chosen: Dict[str, dict] = {}
    if filtering:
        by_key = {i["key"]: i for i in open_issues}
        for row in team.list_issues(open_issues, view["boards"], today, unassigned, older_than, role):
            chosen[row["key"]] = by_key[row["key"]]
    missing = [k for k in dict.fromkeys(keys) if k not in chosen]
    if missing:
        found = {i["key"]: i for i in roles.annotate(jira.search(f"key in ({', '.join(missing)})"), profiles)}
        absent = [k for k in missing if k not in found]
        if absent:
            raise Refused(f"Jira does not show {', '.join(absent)}")
        for key in missing:
            chosen[key] = found[key]
    selection = list(chosen.values())
    if not selection:
        raise Refused("no issue matches")
    if len(selection) > limit:
        raise Refused(f"{len(selection)} issues; the limit is {limit} (raise it with --max, up to {LIMIT_MAX})")
    return selection


def check_profiles(selection: List[dict], profiles: Dict[str, dict]) -> None:
    for board in sorted({roles.project_of(i["key"]) for i in selection}):
        pending = board_profile.open_statuses(profiles[board])
        if pending:
            raise Refused(f"the profile of {board} has {len(pending)} status(es) without a role: decide them with "
                          f"jtk board set before planning a write")


def _envelope(kind: str, view: dict, options: dict, items: List[dict], skipped: List[dict],
              now: Optional[Callable[[], str]] = None) -> dict:
    return {"version": 1, "kind": kind, "view": view["name"], "created": (now or state.utc_now)(),
            "options": options, "items": items, "skipped": skipped}


def _why(skipped: List[dict]) -> str:
    return "; ".join(f"{s['key']}: {s['why']}" for s in skipped)


def _route(jira, key: str, target_ids: List[str]):
    """The one transition from where the issue is to one of `target_ids`, or the reason there is none."""
    options = [t for t in jira.transitions(key) if t["to"]["id"] in target_ids]
    if not options:
        return None, {"key": key, "why": "no path"}
    if len(options) > 1:
        return None, {"key": key, "why": "ambiguous",
                      "options": sorted(f"{t['to']['name']} (transition {t['id']})" for t in options)}
    if options[0]["required"]:
        return None, {"key": key, "why": "required fields", "fields": options[0]["required"]}
    return options[0], None


def _choose_status(profiles: Dict[str, dict], selection: List[dict], skipped: List[dict], to_role: str,
                   to_status: Optional[str]) -> str:
    """When the role has several statuses and none was chosen, say which ones, so `--to-status` is not a guess."""
    if to_status is not None or not any(s["why"] == "ambiguous" for s in skipped):
        return ""
    ambiguous = {s["key"] for s in skipped if s["why"] == "ambiguous"}
    boards = sorted({roles.project_of(i["key"]) for i in selection if i["key"] in ambiguous})
    parts = []
    for board in boards:
        choices = [f"{s['name']} ({s['id']})" for s in profiles[board]["statuses"] if s["role"] == to_role]
        parts.append(f"{board}: {', '.join(choices)}")
    return f". The role {to_role} has several statuses; choose one with --to-status ID ({'; '.join(parts)})"


def move(jira, view: dict, selection: List[dict], profiles: Dict[str, dict], to_role: str,
         to_status: Optional[str] = None, allow_close: bool = False,
         now: Optional[Callable[[], str]] = None) -> dict:
    if to_role not in TO_ROLES:
        raise Refused(f"role must be one of {', '.join(TO_ROLES)}, not {to_role!r}")
    if to_role in CLOSING and not allow_close:
        raise Refused(f"moving to {to_role} closes issues: add --allow-close")
    items, skipped = [], []
    for issue in selection:
        profile = profiles[roles.project_of(issue["key"])]
        targets = [s["id"] for s in profile["statuses"] if s["role"] == to_role]
        if to_status is not None:
            if to_status not in targets:
                raise Refused(f"status {to_status} of {profile['project']} does not play the role {to_role}")
            targets = [to_status]
        if not targets:
            skipped.append({"key": issue["key"], "why": f"{profile['project']} has no status with the role {to_role}"})
        elif issue["status_id"] in targets:
            skipped.append({"key": issue["key"], "why": "already there"})
        else:
            chosen, skip = _route(jira, issue["key"], targets)
            if skip:
                skipped.append(skip)
                continue
            items.append({"key": issue["key"], "title": issue.get("summary") or "",
                          "from": {"id": issue["status_id"], "name": issue["status"]},
                          "to": {"id": chosen["to"]["id"], "name": chosen["to"]["name"], "role": to_role},
                          "transition": chosen["id"]})
    if not items:
        raise Refused("nothing to move: " + _why(skipped) + _choose_status(profiles, selection, skipped, to_role, to_status))
    return _envelope("move", view, {"to_role": to_role, "to_status": to_status, "allow_close": allow_close},
                     items, skipped, now)


def assign(view: dict, selection: List[dict], person: dict, now: Optional[Callable[[], str]] = None) -> dict:
    target = {"id": person["id"], "name": person["name"]}
    items, skipped = [], []
    for issue in selection:
        owner = issue.get("assignee")
        if owner and owner["id"] == person["id"]:
            skipped.append({"key": issue["key"], "why": "already there"})
        else:
            items.append({"key": issue["key"], "title": issue.get("summary") or "",
                          "from": {"id": owner["id"], "name": owner["name"]} if owner else None,
                          "to": dict(target)})
    if not items:
        raise Refused("nothing to assign: " + _why(skipped))
    return _envelope("assign", view, {"person": target}, items, skipped, now)


def comment(view: dict, selection: List[dict], text: str, now: Optional[Callable[[], str]] = None) -> dict:
    clean = (text or "").strip()
    if not clean:
        raise Refused("the comment is empty")
    if len(clean) > MAX_TEXT:
        raise Refused(f"the comment is too long ({len(clean)} characters; the limit is {MAX_TEXT})")
    return _envelope("comment", view, {"text": clean}, [{"key": i["key"], "title": i.get("summary") or ""} for i in selection], [], now)


def _status_role(profiles: Dict[str, dict], key: str, status_id: str) -> Optional[str]:
    profile = profiles.get(roles.project_of(key)) or {"statuses": []}
    return next((s["role"] for s in profile["statuses"] if s["id"] == status_id), None)


def revert(jira, original: dict, profiles: Dict[str, dict], now: Optional[Callable[[], str]] = None,
           allow_close: bool = False) -> dict:
    """The inverse of what the log says `original` wrote. It does not guarantee undoing: an issue that changed since, or a
    workflow with no way back, is left out and said; comments are never reverted."""
    view = {"name": original["view"]}
    items, skipped = [], []
    wrote = [e for e in state.entries(original["id"]) if e.get("result") == "ok"]
    titles = {i["key"]: i.get("title", "") for i in original["items"]}  # plans saved before titles existed have none
    if not wrote:
        raise Refused(f"plan {original['id']} wrote nothing, so there is nothing to revert")
    for entry in wrote:
        key = entry["key"]
        if original["kind"] == "comment":
            skipped.append({"key": key, "why": "comments are not reverted"})
            continue
        snap = jira.snapshot(key)
        if original["kind"] == "assign":
            if (snap["assignee"] or {}).get("id") != (entry["a"] or {}).get("id"):
                skipped.append({"key": key, "why": "changed"})
            else:
                items.append({"key": key, "title": titles.get(key, ""), "from": dict(entry["a"]) if entry["a"] else None,
                              "to": dict(entry["de"]) if entry["de"] else None})
            continue
        if snap["status_id"] != entry["a"]["id"]:
            skipped.append({"key": key, "why": "changed"})
            continue
        chosen, skip = _route(jira, key, [entry["de"]["id"]])
        if skip:
            skipped.append(skip)
            continue
        items.append({"key": key, "title": titles.get(key, ""), "from": {"id": snap["status_id"], "name": snap["status"]},
                      "to": {"id": chosen["to"]["id"], "name": chosen["to"]["name"],
                             "role": _status_role(profiles, key, chosen["to"]["id"])},
                      "transition": chosen["id"]})
    if not items:
        raise Refused("nothing to revert: " + _why(skipped))
    if not allow_close and any(i.get("to") and i["to"].get("role") in CLOSING for i in items):
        raise Refused("reverting closes issues: add --allow-close")
    options = {"revert_of": original["id"]}
    return _envelope(original["kind"], view, options, items, skipped, now)


def _who(person: Optional[dict]) -> str:
    return person["name"] if person else "unassigned"


def describe(plan: dict, only: Optional[List[str]] = None) -> str:
    """What the plan will do, in words. Apply shows this before asking for the approval."""
    items = [i for i in plan["items"] if only is None or i["key"] in only]
    head = f"Plan {plan['id']} · {plan['kind']} · view {plan['view']} · {len(items)} issue(s)"
    if plan["kind"] == "move":
        closes = sum(1 for i in items if i["to"].get("role") in CLOSING)
        head += f" · closes {closes}" if closes else ""
        rows = [f"  {i['key']}: {i['from']['name']} -> {i['to']['name']}" for i in items]
    elif plan["kind"] == "assign":
        rows = [f"  {i['key']}: {_who(i['from'])} -> {_who(i['to'])}" for i in items]
    else:
        rows = [f"  {i['key']}" for i in items] + [f"  Comment: {plan['options']['text']}"]
    lines = [head] + rows
    if plan.get("skipped"):
        lines.append("Left out:")
        for skip in plan["skipped"]:
            extra = f" ({', '.join(skip['options'])})" if skip.get("options") else ""
            extra += f" ({', '.join(skip['fields'])})" if skip.get("fields") else ""
            lines.append(f"  {skip['key']}: {skip['why']}{extra}")
    return "\n".join(lines)


def _change(plan: dict, item: dict) -> str:
    """The row's change: «from -> to» renders as the origin and a pill with the destination."""
    if plan["kind"] == "move":
        return f"{item['from']['name']} -> {item['to']['name']}"
    if plan["kind"] == "assign":
        return f"{_who(item['from'])} -> {_who(item['to'])}"
    return f"Comentario: {plan['options']['text']}"


def _heading(plan: dict, items: List[dict]) -> Tuple[str, List[Tuple[str, str]]]:
    """The verb, and the counts as badges («2 issues», «cierra 1» in red)."""
    badges = [(approval.plural(len(items), "issue", "issues"), "")]
    if plan["kind"] == "move":
        closes = sum(1 for i in items if i["to"].get("role") in CLOSING)
        return "Cambiar estado", badges + ([(f"cierra {closes}", "danger")] if closes else [])
    return ("Reasignar" if plan["kind"] == "assign" else "Comentar"), badges


def summary(plan: dict, only: Optional[List[str]] = None) -> approval.Summary:
    """`describe` for the terminal, plus a row per change (key, title, change) and what was left out, for the approval
    window. Built from the saved plan, never from what an agent says."""
    items = [i for i in plan["items"] if only is None or i["key"] in only]
    rows = [(i["key"], i.get("title", ""), _change(plan, i)) for i in items]
    left_out = [(s["key"], s["why"]) for s in plan.get("skipped", [])]
    transitions = len(items) if plan["kind"] == "move" else 0
    heading, badges = _heading(plan, items)
    return approval.Summary(describe(plan, only), heading, rows, left_out, transitions=transitions, badges=badges)
