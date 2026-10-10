"""Team reports: what each report shows, computed from issues that carry a role (roles.annotate). Pure functions, plus
the gather_* that ask Jira. A report never writes anything."""
from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional, Tuple

from . import queries, roles, standup, stats

CAP = 1000  # issues one search may return; past it the report says so
COUNTED = ("todo", "active", "blocked", "waiting")
AGE_BUCKETS = ((0, 2, "0–2 d"), (3, 7, "3–7 d"), (8, 14, "8–14 d"), (15, None, "15+ d"))


class NoDesk(ValueError):
    """The view has no board whose profile says it is a help desk."""


def _day(text: str) -> _dt.date:
    return _dt.date.fromisoformat(text)


def delivery_day(issue: dict) -> Optional[str]:
    """When the issue was delivered: its resolution day or, without one, its last change of category."""
    return issue.get("resolved") or issue.get("changed")


def _days_since(text: Optional[str], today: _dt.date) -> Optional[int]:
    return (today - _day(text)).days if text else None


def missing_profiles(view: dict, profiles: Dict[str, dict]) -> List[str]:
    return [board for board in view["boards"] if board not in profiles]


def first_week(today: _dt.date, weeks: int) -> _dt.date:
    return stats.week_of(today) - _dt.timedelta(weeks=weeks - 1)


# ---- asking Jira -------------------------------------------------------------------------------------------------

def _fetch(jira, jql: str, conv: dict, profiles: Dict[str, dict]) -> Tuple[List[dict], bool]:
    found, truncated = jira.search_capped(jql, CAP, blocked_link=conv.get("blocked_link") or "is blocked by")
    roles.annotate(found, profiles)
    epic = conv["issue_types"]["epic"]
    return [i for i in found if i["issuetype"] != epic], truncated


def gather_open(jira, view: dict, profiles: Dict[str, dict], conv: dict) -> Tuple[List[dict], bool]:
    """Open work of the team, plus what nobody owns, in the view's boards. Statuses without a role come back with role None."""
    return _fetch(jira, queries.team_open(view["boards"], profiles, view["team"]), conv, profiles)


def gather_closed(jira, view: dict, profiles: Dict[str, dict], conv: dict, wanted: tuple,
                  since: _dt.date) -> Tuple[List[dict], bool]:
    jql = queries.team_closed(view["boards"], profiles, view["team"], wanted, since)
    return ([], False) if jql is None else _fetch(jira, jql, conv, profiles)


def gather_created(jira, view: dict, profiles: Dict[str, dict], conv: dict, since: _dt.date,
                   until: _dt.date) -> Tuple[List[dict], bool]:
    return _fetch(jira, queries.team_created(view["boards"], since, until), conv, profiles)


# ---- the reports -------------------------------------------------------------------------------------------------

def _bucket(issue: dict) -> str:
    role = roles.role_of(issue)
    return role if role in COUNTED else "none"


def _tally() -> dict:
    return {role: 0 for role in COUNTED + ("none",)}


def status_report(open_issues: List[dict], view: dict, profiles: Dict[str, dict]) -> dict:
    """How much open work there is in each role, per board and per person; the WIP verdict needs the profile's wip_limit."""
    boards = []
    for board in view["boards"]:
        mine = [i for i in open_issues if roles.project_of(i["key"]) == board]
        row = dict(_tally(), board=board, n=len(mine), unassigned=sum(1 for i in mine if not i["assignee"]))
        for issue in mine:
            row[_bucket(issue)] += 1
        boards.append(row)
    grouped: Dict[tuple, dict] = {}
    for issue in open_issues:
        if not issue["assignee"]:
            continue
        board, name = roles.project_of(issue["key"]), issue["assignee"]["name"]
        row = grouped.setdefault((name, board), dict(_tally(), person=name, board=board, n=0))
        row["n"] += 1
        row[_bucket(issue)] += 1
    people = []
    for (name, board), row in sorted(grouped.items(), key=lambda kv: (kv[0][0].lower(), kv[0][1])):
        wip = row["active"] + row["blocked"] + row["waiting"]
        limit = profiles[board].get("wip_limit")
        row.update(wip=wip, wip_limit=limit, room=None if limit is None else limit - wip)
        people.append(row)
    return {"n": len(open_issues), "boards": boards, "people": people}


def stalled_report(open_issues: List[dict], today: _dt.date, days: int) -> dict:
    """The `active` issues whose category has not changed for `days` days or more, with the days since the last edit beside it."""
    rows = []
    for issue in open_issues:
        if roles.role_of(issue) != "active" or not issue.get("changed"):
            continue
        in_category = _days_since(issue["changed"], today)
        if in_category < days:
            continue
        rows.append({"issue": issue, "days_in_category": in_category,
                     "days_since_edit": _days_since(issue.get("updated"), today)})
    rows.sort(key=lambda r: (-r["days_in_category"], r["issue"]["key"]))
    return {"days": days, "n_active": sum(1 for i in open_issues if roles.role_of(i) == "active"), "rows": rows}


def blocked_report(open_issues: List[dict], conv: dict, today: _dt.date) -> dict:
    """What is blocked (by role, flag or an unresolved «is blocked by» link) and, apart, what waits for a third party."""
    statuses = conv.get("blocked_statuses") or []
    age = lambda i: _days_since(i.get("changed"), today)  # noqa: E731
    order = lambda days, key: (-(days if days is not None else -1), key)  # noqa: E731
    blocked = [dict(why, issue=i, days=age(i)) for i in open_issues for why in standup.blockers(i, statuses)]
    waiting = [{"issue": i, "days": age(i)} for i in open_issues if roles.role_of(i) == "waiting"]
    blocked.sort(key=lambda r: order(r["days"], r["issue"]["key"]))
    waiting.sort(key=lambda r: order(r["days"], r["issue"]["key"]))
    return {"n": len(open_issues), "blocked": blocked, "waiting": waiting}


def flow_report(delivered: List[dict], dropped: List[dict], open_issues: List[dict], today: _dt.date,
                weeks: int, stalled_days: int = stats.STALLED_DAYS) -> dict:
    """Deliveries per week, lead time and the age of the work in flight. Only `delivered` counts as delivery."""
    first = first_week(today, weeks).isoformat()
    mine = [dict(i, changed=delivery_day(i)) for i in delivered if (delivery_day(i) or "") >= first]
    gone = [i for i in dropped if (i.get("changed") or "") >= first]
    return {"weeks": weeks, "since": first, "delivered_n": len(mine), "dropped_n": len(gone),
            "weekly": stats.throughput(mine, today, weeks), "lead": stats.spread(stats.lead_days(mine)),
            "wip": stats.wip(open_issues, today, stalled_days)}


def digest_report(delivered: List[dict], dropped: List[dict], created: List[dict], open_issues: List[dict],
                  conv: dict, since: _dt.date, until: _dt.date, today: _dt.date, days: int) -> dict:
    lo, hi = since.isoformat(), until.isoformat()
    done = sorted((i for i in delivered if lo <= (delivery_day(i) or "") <= hi),
                  key=lambda i: (delivery_day(i), i["key"]))
    gone = sorted((i for i in dropped if lo <= (i.get("changed") or "") <= hi), key=lambda i: (i["changed"], i["key"]))
    new = sorted((i for i in created if lo <= (i.get("created") or "") <= hi), key=lambda i: i["key"])
    blocked = blocked_report(open_issues, conv, today)
    stalled = stalled_report(open_issues, today, days)
    return {"since": lo, "until": hi, "days": days, "delivered": done, "dropped": gone, "created": new,
            "blocked_now": len({r["issue"]["key"] for r in blocked["blocked"]}), "waiting_now": len(blocked["waiting"]),
            "stalled_now": len(stalled["rows"])}


def desk_boards(view: dict, profiles: Dict[str, dict]) -> List[str]:
    return [board for board in view["boards"] if profiles[board].get("kind") == "helpdesk"]


def _age_label(days: int) -> str:
    for low, high, label in AGE_BUCKETS:
        if days >= low and (high is None or days <= high):
            return label
    return AGE_BUCKETS[0][2]  # a creation date in the future counts as the youngest


def desk_report(open_issues: List[dict], delivered: List[dict], view: dict, profiles: Dict[str, dict],
                today: _dt.date, weeks: int) -> dict:
    """For the view's help desk boards: age of what is open (what waits for a third party is counted apart), what has no
    owner, and how long resolving took. There is no SLA here: no service desk measured had SLA data."""
    boards = desk_boards(view, profiles)
    if not boards:
        raise NoDesk(f"view {view['name']!r} has no help desk board: set one with jk board setup KEY --kind helpdesk")
    first = first_week(today, weeks).isoformat()
    rows = []
    for board in boards:
        mine = [i for i in open_issues if roles.project_of(i["key"]) == board]
        age = {label: 0 for _, _, label in AGE_BUCKETS}
        for issue in (i for i in mine if roles.role_of(i) in ("todo", "active", "blocked")):
            days = _days_since(issue.get("created"), today)
            if days is not None:
                age[_age_label(days)] += 1
        solved = [i for i in delivered if roles.project_of(i["key"]) == board and (delivery_day(i) or "") >= first]
        rows.append({"board": board, "open": len(mine), "age": age,
                     "unassigned": sum(1 for i in mine if not i["assignee"]),
                     "waiting": sum(1 for i in mine if roles.role_of(i) == "waiting"),
                     "unknown": sum(1 for i in mine if roles.role_of(i) not in ("todo", "active", "blocked", "waiting")),
                     "resolved_n": len(solved), "resolution": stats.spread(stats.lead_days(solved))})
    return {"weeks": weeks, "since": first, "boards": rows}


def list_issues(open_issues: List[dict], boards: List[str], today: _dt.date, unassigned: bool = False,
                older_than: Optional[int] = None, role: Optional[str] = None,
                age_roles: Optional[tuple] = None) -> List[dict]:
    """The issues behind a count: what status and desk counted on `boards`, oldest first, narrowed by the filters. With
    `age_roles`, older_than only looks at those roles (the desk does not age what waits for a third party)."""
    if role is not None and role not in COUNTED + ("none",):
        raise ValueError(f"role must be one of {', '.join(COUNTED + ('none',))}, not {role!r}")
    if older_than is not None and older_than < 0:
        raise ValueError("older-than must be 0 or more days")
    rows = []
    for issue in open_issues:
        if roles.project_of(issue["key"]) not in boards:
            continue
        bucket, age = _bucket(issue), _days_since(issue.get("created"), today)
        owner = issue["assignee"]["name"] if issue["assignee"] else None
        if (unassigned and owner) or (role is not None and bucket != role):
            continue
        if older_than is not None and (age is None or age < older_than or (age_roles and bucket not in age_roles)):
            continue
        rows.append({"key": issue["key"], "title": issue["summary"], "owner": owner, "status": issue["status"],
                     "role": bucket, "age_days": age})
    return sorted(rows, key=lambda r: (r["age_days"] is None, -(r["age_days"] or 0), r["key"]))


def rollup_row(view: dict, open_issues: List[dict], delivered: List[dict], conv: dict, today: _dt.date,
               weeks: int = 4) -> dict:
    blocked = blocked_report(open_issues, conv, today)
    flow = flow_report(delivered, [], open_issues, today, weeks, view["stalled_days"])
    return {"view": view["name"], "open": len(open_issues),
            "blocked": len({r["issue"]["key"] for r in blocked["blocked"]}),
            "stalled": len(stalled_report(open_issues, today, view["stalled_days"])["rows"]),
            "delivered": flow["delivered_n"], "lead": flow["lead"], "weeks": weeks}
