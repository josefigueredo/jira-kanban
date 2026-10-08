"""Delivery metrics and load, computed from normalized issues. Nothing here needs estimates: PLATE has no story
points, so velocity is issues closed per week. Times are medians and p85 with their n, never averages."""
from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Dict, List, Optional

from . import queries, standup

STALLED_DAYS = 7
DUE_SOON_DAYS = 7
OLDEST = 3
AREA = re.compile(r"^\[([A-Z0-9]+)\]")


def _day(text: str) -> _dt.date:
    return _dt.date.fromisoformat(text)


def percentile(values: List[int], pct: int) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def spread(values: List[int]) -> Optional[dict]:
    return {"n": len(values), "median": percentile(values, 50), "p85": percentile(values, 85)} if values else None


def week_of(day: _dt.date) -> _dt.date:
    return day - _dt.timedelta(days=day.weekday())


def throughput(done: List[dict], today: _dt.date, weeks: int) -> List[dict]:
    first = week_of(today) - _dt.timedelta(weeks=weeks - 1)
    counts = {first + _dt.timedelta(weeks=k): 0 for k in range(weeks)}
    for issue in done:
        if issue["changed"] and week_of(_day(issue["changed"])) in counts:
            counts[week_of(_day(issue["changed"]))] += 1
    return [{"week": w.isoformat(), "closed": n, "partial": w == week_of(today)} for w, n in sorted(counts.items())]


def lead_days(done: List[dict]) -> List[int]:
    days = []
    for issue in done:
        end = issue["resolved"] or issue["changed"]
        if issue["created"] and end:
            days.append(max(0, (_day(end) - _day(issue["created"])).days))
    return days


def wip(open_issues: List[dict], today: _dt.date) -> List[dict]:
    rows = [{"issue": i, "days": (today - _day(i["changed"])).days}
            for i in open_issues if i["category"] == "in_progress" and i["changed"]]
    rows.sort(key=lambda r: (-r["days"], r["issue"]["key"]))
    return [dict(r, stalled=r["days"] >= STALLED_DAYS) for r in rows]


def on_time(done: List[dict]) -> Optional[dict]:
    dated = [i for i in done if i["duedate"] and (i["resolved"] or i["changed"])]
    if not dated:
        return None
    ok = sum(1 for i in dated if (i["resolved"] or i["changed"]) <= i["duedate"])
    return {"n": len(dated), "on_time": ok, "pct": round(100 * ok / len(dated))}


def mix(done: List[dict], areas: List[str]) -> dict:
    by_area: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    for issue in done:
        found = AREA.match(issue["summary"])
        area = found.group(1) if found and found.group(1) in areas else "(sin área)"
        by_area[area] = by_area.get(area, 0) + 1
        by_type[issue["issuetype"]] = by_type.get(issue["issuetype"], 0) + 1
    return {"by_area": by_area, "by_type": by_type}


def oldest(open_issues: List[dict], today: _dt.date, n: int = OLDEST) -> List[dict]:
    rows = [{"issue": i, "days": (today - _day(i["created"])).days} for i in open_issues if i["created"]]
    rows.sort(key=lambda r: (-r["days"], r["issue"]["key"]))
    return rows[:n]


def compute(done: List[dict], open_issues: List[dict], today: _dt.date, weeks: int, conv: dict) -> dict:
    return {"weeks": weeks, "weekly": throughput(done, today, weeks), "lead": spread(lead_days(done)),
            "wip": wip(open_issues, today), "on_time": on_time(done), "mix": mix(done, conv.get("areas") or []),
            "oldest": oldest(open_issues, today)}


def load_numbers(done: List[dict], open_issues: List[dict], today: _dt.date, weeks: int, conv: dict) -> dict:
    statuses = conv.get("blocked_statuses") or []
    soon = (today + _dt.timedelta(days=DUE_SOON_DAYS)).isoformat()
    numbers = {"open": len(open_issues),
               "in_progress": sum(1 for i in open_issues if i["category"] == "in_progress"),
               "blocked": sum(1 for i in open_issues if standup.blockers(i, statuses)),
               "overdue": sum(1 for i in open_issues if i["duedate"] and i["duedate"] < today.isoformat()),
               "due_soon": sum(1 for i in open_issues if i["duedate"] and today.isoformat() <= i["duedate"] <= soon),
               "weekly": throughput(done, today, weeks), "verdict": None}
    limit = conv.get("wip_limit")
    if limit:
        numbers["verdict"] = {"wip_limit": limit, "room": limit - numbers["in_progress"]}
    return numbers


def gather_history(jira, person: Optional[str], today: _dt.date, weeks: int, conv: dict) -> tuple:
    """(closed in the last `weeks` weeks, open now), both without epics."""
    epic_type = conv["issue_types"]["epic"]
    first = week_of(today) - _dt.timedelta(weeks=weeks - 1)
    project = conv.get("project")
    done = standup.search(jira, queries.done_since(person, first, project), conv)
    open_issues = standup.search(jira, queries.open_of(person, project), conv)
    return ([i for i in done if i["issuetype"] != epic_type], [i for i in open_issues if i["issuetype"] != epic_type])
