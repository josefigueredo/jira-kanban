"""What each report shows, picked from normalized issues (Jira.search). Pure functions, plus one `gather_*` per
report that asks Jira. Epics are containers, not work: they never appear as rows of next, blocked, load or stats."""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from . import queries, roles

FAR = "9999-12-31"  # sorts after any real due date
MAX_EPICS = 50


def search(jira, jql: str, conv: dict) -> List[dict]:
    """Jira's answer with each issue's role set from the board profiles in conv["profiles"]."""
    found = jira.search(jql, blocked_link=conv.get("blocked_link") or "is blocked by")
    roles.annotate(found, conv.get("profiles") or {})
    if "_seen" in conv:  # the CLI collects what the report read, to tell the reader which profiles it lacked
        conv["_seen"].extend(found)
    return found


def _rank(conv: dict, priority: str) -> int:
    order = conv.get("priorities") or []
    return order.index(priority) if priority in order else len(order)


def blockers(issue: dict, blocked_statuses: List[str]) -> List[dict]:
    """Why an open issue is blocked: one row per unresolved blocker; with none linked, the flag or the status itself."""
    role = roles.role_of(issue)
    if role in roles.CLOSED:
        return []
    rows = [{"by": b["key"], "title": b["summary"], "status": b["status"], "owner": b["assignee"] or "sin dueño"}
            for b in issue["blocked_by"] if b["category"] != "done"]
    if rows:
        return rows
    if issue["flagged"]:
        return [{"by": "Flagged, sin link", "title": "", "status": "", "owner": ""}]
    if roles.source_of(issue) == "profile":
        by_status = role == "blocked"
    else:
        by_status = issue["status"].lower() in {name.lower() for name in blocked_statuses}
    if by_status:
        return [{"by": f"Estado {issue['status']}, sin link", "title": "", "status": "", "owner": ""}]
    return []


def blocked_rows(open_issues: List[dict], conv: dict) -> List[dict]:
    statuses = conv.get("blocked_statuses") or []
    return [dict(why, issue=i) for i in open_issues for why in blockers(i, statuses)]


def next_tables(open_issues: List[dict], unowned: List[dict], today: _dt.date, until: _dt.date, conv: dict) -> dict:
    statuses = conv.get("blocked_statuses") or []
    by_priority = lambda i: (_rank(conv, i["priority"]), i["duedate"] or FAR, i["key"])  # noqa: E731
    ready = sorted((i for i in open_issues if not blockers(i, statuses) and roles.role_of(i) != "waiting"),
                   key=by_priority)
    due = sorted((i for i in open_issues if i["duedate"] and i["duedate"] <= until.isoformat()),
                 key=lambda i: (i["duedate"], i["key"]))
    return {"ready": ready,
            "due": [{"issue": i, "overdue": i["duedate"] < today.isoformat(), "blocked": bool(blockers(i, statuses))}
                    for i in due],
            "unowned": sorted(unowned, key=by_priority)}


def epic_keys(open_issues: List[dict], owned_epics: List[dict], epic_type: str) -> List[str]:
    keys = {i["parent"]["key"] for i in open_issues if i["parent"] and i["parent"]["issuetype"] == epic_type}
    keys |= {e["key"] for e in owned_epics}
    return sorted(keys)[:MAX_EPICS]


def _open(jira, person: Optional[str], conv: dict) -> tuple:
    """(work, epics) of a person that are not done; epics are kept apart so they never show as rows."""
    epic_type = conv["issue_types"]["epic"]
    found = [i for i in search(jira, queries.open_of(person, conv.get("project")), conv)
             if roles.role_of(i) not in roles.CLOSED]  # a «Done» filed under in progress is not open work
    return ([i for i in found if i["issuetype"] != epic_type], [i for i in found if i["issuetype"] == epic_type])


def gather_next(jira, person: Optional[str], until: _dt.date, today: _dt.date, conv: dict) -> dict:
    work, epics = _open(jira, person, conv)
    keys = epic_keys(work, epics, conv["issue_types"]["epic"])
    unowned = search(jira, queries.unowned_in(keys), conv) if keys else []
    return next_tables(work, unowned, today, until, conv)


def gather_blocked(jira, person: Optional[str], conv: dict) -> List[dict]:
    return blocked_rows(_open(jira, person, conv)[0], conv)


NO_EPIC = {"key": "", "summary": "Sin épica", "issuetype": "", "status": "", "category": "", "changed": None,
           "parent": None}


def _stub(parent: dict) -> dict:
    """What is known of an ancestor Jira did not return: only its key, summary and type."""
    return {"key": parent["key"], "summary": parent["summary"], "issuetype": parent["issuetype"], "status": "",
            "category": "", "changed": None, "parent": None}


def _number(key: str) -> tuple:
    prefix, _, digits = key.rpartition("-")
    return (prefix, int(digits) if digits.isdigit() else 0)


def _sorted(nodes: List[dict]) -> List[dict]:
    for node in nodes:
        node["children"] = _sorted(node["children"])
    return sorted(nodes, key=lambda n: _number(n["issue"]["key"]))


def done_tree(issues: List[dict], parents: dict, epic_type: str) -> List[dict]:
    """Epic -> story/task -> subtask for the issues that changed. `parents` maps the key of a story or task that did
    not change to its issue, so a subtask can still reach its epic. Ancestors outside the window are `context`."""
    known = {i["key"]: i for i in issues}
    known.update({k: v for k, v in parents.items() if k not in known})
    in_window = {i["key"] for i in issues}
    nodes: dict = {}
    linked: set = set()
    order: List[str] = []
    stats_only = ("labels", "components")
    for issue in issues:
        chain = [issue]
        while chain[-1]["parent"] and len(chain) < 4:
            up = chain[-1]["parent"]
            chain.append(known.get(up["key"]) or _stub(up))
        below = None
        for item in chain:  # the issue first, its epic last
            if item["key"] not in nodes:
                shown = {k: v for k, v in item.items() if k not in stats_only}  # labels and components are for `stats --by`
                nodes[item["key"]] = {"issue": shown, "context": item["key"] not in in_window, "children": []}
                order.append(item["key"])
            current = nodes[item["key"]]
            if below is not None and below["issue"]["key"] not in linked:
                current["children"].append(below)
                linked.add(below["issue"]["key"])
            below = current
    roots = [nodes[k] for k in order if k not in linked]
    tree = _sorted([r for r in roots if r["issue"]["issuetype"] == epic_type])
    loose = _sorted([r for r in roots if r["issue"]["issuetype"] != epic_type])
    return tree + ([{"issue": NO_EPIC, "context": True, "children": loose}] if loose else [])


def gather_done(jira, person: Optional[str], since: _dt.date, until: _dt.date, conv: dict) -> dict:
    issues = search(jira, queries.changed_in(person, since, until, conv.get("project")), conv)
    types = conv["issue_types"]
    have = {i["key"] for i in issues}
    need = sorted({i["parent"]["key"] for i in issues  # any child of a non-epic: the subtask type name varies by project
                   if i["parent"] and i["parent"]["issuetype"] != types["epic"] and i["parent"]["key"] not in have})
    parents = {i["key"]: i for i in search(jira, queries.by_keys(need), conv)} if need else {}
    work = [i for i in issues if i["issuetype"] != types["epic"]]
    return {"done": sum(1 for i in work if roles.role_of(i) == "delivered"),
            "dropped": sum(1 for i in work if roles.role_of(i) == "dropped"),
            "in_progress": sum(1 for i in work if roles.role_of(i) in roles.IN_FLIGHT),
            "tree": done_tree(issues, parents, types["epic"])}
