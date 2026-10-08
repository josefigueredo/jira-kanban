# jira-standup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five read-only `jk` commands (`done`, `next`, `blocked`, `load`, `stats`) and a sibling skill `jira-standup` that answer "what did I do", "what can I do next", "what blocks me", "does a teammate have room" and "my delivery metrics" as tables and trees.

**Architecture:** One new read method, `Jira.search`, returns normalized issue dicts. Pure modules (`queries`, `window`, `standup`, `stats`, `render`) turn those dicts into results and Markdown; `cli.py` only wires arguments to them. The skill is a second folder (`standup/`) in the same repo, installed by `install.sh` next to `jira-kanban`, and calls the same `jk.py`.

**Tech Stack:** Python stdlib only (3.9 compatible: `from __future__ import annotations`, no `match`, no `X | Y` types), `unittest`, Jira Cloud REST v3 `POST /rest/api/3/search/jql`.

**Spec:** `docs/superpowers/specs/2026-10-08-jira-standup-design.md`

## Global Constraints

- Read only: no command in this plan may call `create`, `update`, `assign`, a transition, or write `jira-writes.jsonl`.
- Python stdlib only; the suite passes with `python3 -m unittest discover -s tests` and with `/usr/bin/python3 -m unittest discover -s tests` (3.9).
- Code, skills and CLI messages in English; documentation for people in Rioplatense Spanish; report labels in Spanish, as `jk board` already does.
- TDD: every behavior gets a failing test first. Conventional commits in English, no `Co-Authored-By` and no AI attribution.
- Credentials (`IC_JIRA_*`) are never printed, logged or committed.
- Dates enter the CLI only as `YYYY-MM-DD`; the agent translates "ayer" and "la semana pasada". The team's time zone is `America/Argentina/Buenos_Aires` (`conventions.json` key `timezone`).
- A person is identified only through `people.resolve()`; an ambiguous name is never guessed.
- Every number that can be measured is measured; what cannot is labelled as inference in the output.

## Deviations from the spec (decided while planning, after reading the code)

- `jk load` takes `--weeks N`, not `--days N`: its history is bucketed by week, the same unit `stats` uses.
- Trees are printed inside a fenced code block so the box characters stay aligned; therefore keys in trees are plain text, and only table cells carry the issue URL. Task 8 updates the spec.
- Epics are excluded from `next`, `blocked`, `load` and `stats` rows (they are containers, not work); they are still used to find "sin dueño en sus épicas" and appear in the `done` tree.

## Review Focus

Failure modes the spec implies but a first pass would not test; each has a test in the task named:

1. `--since` after `--until`, a non-ISO date ("ayer"), `--weeks 0` → clear error, exit 1, nothing queried (Task 2, Task 7).
2. A person whose name matches two people → exit 1, candidates listed, no query run (Task 7).
3. An issue with no assignee, no parent, no priority or no dates must not crash any renderer (Tasks 1, 3, 4, 6).
4. A blocking link whose target Jira hides (no `fields`) → still a row, not a `KeyError` (Task 1).
5. A subtask closed in the window whose parent task was not: the tree must still reach its epic (Task 4).

---

### Task 0: Probe the real Jira (measure before building)

Three spec items are inference until measured: `statusCategoryChangedDate` in JQL, the "is blocked by" link type, and whether PLATE uses `duedate`. No repo files change in this task.

**Files:**
- Create: `<scratchpad>/probe_jira.py` (scratchpad, not the repo)

- [ ] **Step 1: Write the probe**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/josefigueredo/CurrentCode/SPECKIT/Harness/jira-kanban")
from jkan import config  # noqa: E402
from jkan.jira import Jira, JiraError  # noqa: E402

creds = config.credentials(Path("."))
if creds is None:
    raise SystemExit("no IC_JIRA_* credentials in this shell")
jira = Jira(*creds)  # never print creds or the base url


def post(jql, fields, n=50):
    return jira._send("POST", "/rest/api/3/search/jql", {"jql": jql, "fields": fields, "maxResults": n}).get("issues", [])


checks = {}
for name, jql in {
    "category_changed_in_jql": 'assignee = currentUser() AND statusCategory in ("Done", "In Progress") AND statusCategoryChangedDate >= "2026-10-01" ORDER BY statusCategoryChangedDate DESC',
    "open_ordered_by_priority": "assignee = currentUser() AND statusCategory != Done ORDER BY priority DESC, duedate ASC",
    "duedate_used_in_plate": "project = PLATE AND duedate is not EMPTY",
}.items():
    try:
        found = post(jql, ["summary", "statuscategorychangedate", "duedate", "priority", "issuelinks", "resolutiondate"])
        checks[name] = {"ok": True, "count": len(found),
                        "has_changed_field": sum(1 for i in found if i["fields"].get("statuscategorychangedate")),
                        "has_duedate": sum(1 for i in found if i["fields"].get("duedate")),
                        "link_inward_names": sorted({(l.get("type") or {}).get("inward") for i in found
                                                     for l in i["fields"].get("issuelinks") or [] if l.get("inwardIssue")})}
    except JiraError as exc:
        checks[name] = {"ok": False, "error": str(exc)[:200]}
checks["link_types"] = [t.get("inward") for t in jira._send("GET", "/rest/api/3/issueLinkType").get("issueLinkTypes", [])]
print(json.dumps(checks, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: Run it**

Run: `python3 <scratchpad>/probe_jira.py`
Expected: JSON with `category_changed_in_jql.ok == true`, `has_changed_field > 0`, and `link_types` containing the inward text the team uses.

- [ ] **Step 3: Decide**

| Result | Action |
|---|---|
| `category_changed_in_jql.ok` is false | STOP. Report the error to the user; do not start Task 1. |
| The blocking link's inward text is not `is blocked by` (e.g. Spanish "está bloqueado por") | In Task 2 Step 3 set `"blocked_link"` in `conventions.json` to that exact text. |
| `duedate_used_in_plate.count == 0` | Keep the code; the two date-based outputs will say "nada con fecha". Tell the user. |

No commit (nothing in the repo changed).

---

### Task 1: `Jira.search` returns normalized issues

**Files:**
- Modify: `jkan/jira.py` (constants after line 12; two helpers and `search` after `children`, ~line 122)
- Modify: `tests/helpers.py` (`FakeJira.__init__`, new `search`, new `issue()`)
- Test: `tests/test_search.py`

**Interfaces:**
- Produces: `Jira.search(jql: str, blocked_link: str = "is blocked by") -> List[dict]`. Each dict has exactly these keys: `key, summary, issuetype, status, category ("todo"|"in_progress"|"done"|""), parent (None | {key, summary, issuetype}), assignee (None | {id, name}), priority, duedate (None | "YYYY-MM-DD"), created, resolved, changed (None | "YYYY-MM-DD"), flagged (bool), blocked_by (list of {key, summary, status, category, assignee})`.
- Produces: `helpers.issue(key, **over) -> dict` (same shape) and `FakeJira.search` whose results come from `fake.search_answer(jql)`; `fake.jqls` records every JQL.

- [ ] **Step 1: Write the failing tests** — create `tests/test_search.py`

```python
from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401
from test_jira import FIELDS, client

BLOCKER = {"key": "PLATE-5", "fields": {"summary": "Esperar a Okta", "status": {"name": "Blocked",
           "statusCategory": {"key": "indeterminate"}}, "assignee": {"displayName": "Ana Gómez"}}}
RAW = {"key": "PLATE-9", "fields": {
    "summary": "[BE] Algo", "issuetype": {"name": "Tarea"},
    "status": {"name": "PROCESANDO", "statusCategory": {"key": "indeterminate"}},
    "parent": {"key": "PLATE-1", "fields": {"summary": "Épica", "issuetype": {"name": "Epic"}}},
    "assignee": {"accountId": "acc-me", "displayName": "Yo"}, "priority": {"name": "High"},
    "duedate": "2026-10-10", "created": "2026-10-01T09:00:00.000-0300", "resolutiondate": None,
    "statuscategorychangedate": "2026-10-07T14:03:00.000-0300", "customfield_10023": [{"value": "Impediment"}],
    "issuelinks": [{"type": {"inward": "is blocked by"}, "inwardIssue": BLOCKER},
                   {"type": {"inward": "relates to"}, "inwardIssue": {"key": "PLATE-6", "fields": {}}},
                   {"type": {"inward": "is blocked by"}, "outwardIssue": {"key": "PLATE-7", "fields": {}}}]}}


class SearchTest(unittest.TestCase):
    def test_search_normalizes_an_issue_and_follows_the_pages(self):
        pages = [{"issues": [RAW], "nextPageToken": "n1"}, {"issues": [dict(RAW, key="PLATE-10")]}]
        jira, rec = client({("POST", "/rest/api/3/search/jql"): lambda body: pages.pop(0),
                            ("GET", "/rest/api/3/field"): FIELDS})
        found = jira.search("assignee = currentUser()")
        self.assertEqual([i["key"] for i in found], ["PLATE-9", "PLATE-10"])
        self.assertEqual(found[0], {
            "key": "PLATE-9", "summary": "[BE] Algo", "issuetype": "Tarea", "status": "PROCESANDO",
            "category": "in_progress", "parent": {"key": "PLATE-1", "summary": "Épica", "issuetype": "Epic"},
            "assignee": {"id": "acc-me", "name": "Yo"}, "priority": "High", "duedate": "2026-10-10",
            "created": "2026-10-01", "resolved": None, "changed": "2026-10-07", "flagged": True,
            "blocked_by": [{"key": "PLATE-5", "summary": "Esperar a Okta", "status": "Blocked",
                            "category": "in_progress", "assignee": "Ana Gómez"}]})
        posts = [c for c in rec.calls if c[0] == "POST"]
        self.assertEqual(posts[0][2]["jql"], "assignee = currentUser()")
        self.assertIn("statuscategorychangedate", posts[0][2]["fields"])
        self.assertIn("customfield_10023", posts[0][2]["fields"])
        self.assertEqual(posts[1][2]["nextPageToken"], "n1")

    def test_search_survives_an_issue_with_nothing_optional(self):
        bare = {"key": "PLATE-2", "fields": {"summary": "x", "status": {"name": "Backlog",
                "statusCategory": {"key": "new"}}, "issuelinks": [{"type": {"inward": "is blocked by"},
                "inwardIssue": {"key": "PLATE-3"}}]}}
        jira, _ = client({("POST", "/rest/api/3/search/jql"): {"issues": [bare]}, ("GET", "/rest/api/3/field"): FIELDS})
        issue = jira.search("x")[0]
        self.assertIsNone(issue["parent"])
        self.assertIsNone(issue["assignee"])
        self.assertEqual(issue["priority"], "")
        self.assertFalse(issue["flagged"])
        self.assertEqual(issue["blocked_by"], [{"key": "PLATE-3", "summary": "", "status": "", "category": "",
                                                "assignee": ""}])

    def test_search_uses_the_link_text_it_is_told_to(self):
        jira, _ = client({("POST", "/rest/api/3/search/jql"): {"issues": [RAW]}, ("GET", "/rest/api/3/field"): FIELDS})
        self.assertEqual(jira.search("x", blocked_link="relates to")[0]["blocked_by"][0]["key"], "PLATE-6")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_search.py"`
Expected: FAIL/ERROR with `AttributeError: 'Jira' object has no attribute 'search'`.

- [ ] **Step 3: Implement** — in `jkan/jira.py` add after `CATEGORY = ...` (line 12):

```python
STANDUP_FIELDS = ["summary", "issuetype", "status", "parent", "assignee", "priority", "duedate", "created",
                  "resolutiondate", "statuscategorychangedate", "issuelinks"]
BLOCKED_LINK = "is blocked by"


def _day(stamp: Optional[str]) -> Optional[str]:
    """Jira's 2026-10-07T14:03:00.000-0300 as its calendar day, 2026-10-07 (the date in the stamp's own offset)."""
    return stamp[:10] if stamp else None


def _state(status: dict) -> str:
    return CATEGORY.get((status.get("statusCategory") or {}).get("key", ""), "")
```

and add these methods to `Jira`, right after `children` (before `update`):

```python
    @staticmethod
    def _blocker(link: dict, wanted: str) -> Optional[dict]:
        """The issue blocking this one, when the link reads `wanted` ("is blocked by") from this side."""
        other = link.get("inwardIssue")
        if not other or ((link.get("type") or {}).get("inward") or "").lower() != wanted.lower():
            return None
        fields = other.get("fields") or {}
        status = fields.get("status") or {}
        return {"key": other["key"], "summary": fields.get("summary") or "", "status": status.get("name", ""),
                "category": _state(status), "assignee": (fields.get("assignee") or {}).get("displayName") or ""}

    def _report_issue(self, raw: dict, flag: Optional[str], wanted: str) -> dict:
        f = raw["fields"]
        parent, owner, status = f.get("parent"), f.get("assignee"), f.get("status") or {}
        parent_fields = (parent or {}).get("fields") or {}
        return {"key": raw["key"], "summary": f.get("summary") or "",
                "issuetype": (f.get("issuetype") or {}).get("name", ""),
                "status": status.get("name", ""), "category": _state(status),
                "parent": {"key": parent["key"], "summary": parent_fields.get("summary") or "",
                           "issuetype": (parent_fields.get("issuetype") or {}).get("name", "")} if parent else None,
                "assignee": {"id": owner["accountId"], "name": owner.get("displayName") or ""} if owner else None,
                "priority": (f.get("priority") or {}).get("name", ""), "duedate": f.get("duedate"),
                "created": _day(f.get("created")), "resolved": _day(f.get("resolutiondate")),
                "changed": _day(f.get("statuscategorychangedate")),
                "flagged": bool(f.get(flag)) if flag else False,
                "blocked_by": [b for b in (self._blocker(link, wanted) for link in f.get("issuelinks") or []) if b]}

    def search(self, jql: str, blocked_link: str = BLOCKED_LINK) -> List[dict]:
        """Every issue the JQL finds, in the shape the reports use. Read only; follows the result pages."""
        flag = self._flag_field()
        fields = STANDUP_FIELDS + ([flag] if flag else [])
        found: List[dict] = []
        token = None
        while True:
            body = {"jql": jql, "fields": fields, "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = self._send("POST", "/rest/api/3/search/jql", body)
            found += [self._report_issue(raw, flag, blocked_link) for raw in page.get("issues", [])]
            token = page.get("nextPageToken")
            if not token:
                return found
```

In `tests/helpers.py`, at the end of `FakeJira.__init__` (after `self.writes: List[tuple] = []`) add:

```python
        self.search_answer = lambda jql: []  # tests replace it: jql -> list of normalized issues
        self.jqls: List[str] = []
```

add this method to `FakeJira` (after `children`):

```python
    def search(self, jql: str, blocked_link: str = "is blocked by") -> List[dict]:
        self.jqls.append(jql)
        return [dict(i) for i in self.search_answer(jql)]
```

and this function after `epic_with_children`:

```python
def issue(key: str, **over) -> dict:
    """A normalized issue as Jira.search returns it, for the report tests."""
    base = {"key": key, "summary": f"Summary of {key}", "issuetype": "Tarea", "status": "Backlog", "category": "todo",
            "parent": None, "assignee": {"id": "acc-me", "name": "Yo"}, "priority": "Medium", "duedate": None,
            "created": "2026-09-01", "resolved": None, "changed": "2026-09-01", "flagged": False, "blocked_by": []}
    base.update(over)
    return base
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_search.py"`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add jkan/jira.py tests/helpers.py tests/test_search.py
git commit -m "feat(jira): search returns normalized issues with dates, assignee, priority and blockers"
```

---

### Task 2: Dates and JQL builders

**Files:**
- Create: `jkan/window.py`, `jkan/queries.py`
- Modify: `conventions.json` (add `blocked_link`, `timezone`, a note)
- Test: `tests/test_queries.py`

**Interfaces:**
- Produces (`window`): `BadWindow(ValueError)`; `parse_day(text) -> date`; `span(since, until, today) -> (date, date)` (`until=None` means today; start after end raises); `horizon(until, today) -> date` (`None` means today; before today raises); `weeks(n) -> int` (1..52 else raises); `today_in(zone) -> date`.
- Produces (`queries`): `changed_in(person, since, until, project=None)`, `open_of(person, project=None)`, `done_since(person, since, project=None)`, `unowned_in(keys)`, `by_keys(keys)`; `person` is `None` (= `currentUser()`) or an accountId. All return a JQL `str`; a bad accountId, project or key raises `ValueError`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_queries.py`

```python
from __future__ import annotations

import unittest
from datetime import date

from helpers import ROOT  # noqa: F401
from jkan import queries, window

TODAY = date(2026, 10, 8)


class WindowTest(unittest.TestCase):
    def test_span_defaults_until_to_today(self):
        self.assertEqual(window.span("2026-10-01", None, TODAY), (date(2026, 10, 1), TODAY))

    def test_span_keeps_both_ends(self):
        self.assertEqual(window.span("2026-10-01", "2026-10-03", TODAY), (date(2026, 10, 1), date(2026, 10, 3)))

    def test_since_after_until_is_refused(self):
        with self.assertRaises(window.BadWindow) as ctx:
            window.span("2026-10-05", "2026-10-03", TODAY)
        self.assertIn("after", str(ctx.exception))

    def test_a_phrase_is_not_a_date(self):
        with self.assertRaises(window.BadWindow) as ctx:
            window.parse_day("ayer")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))

    def test_horizon_cannot_be_in_the_past(self):
        self.assertEqual(window.horizon(None, TODAY), TODAY)
        self.assertEqual(window.horizon("2026-10-12", TODAY), date(2026, 10, 12))
        with self.assertRaises(window.BadWindow):
            window.horizon("2026-10-01", TODAY)

    def test_weeks_must_be_between_1_and_52(self):
        self.assertEqual(window.weeks(4), 4)
        for bad in (0, 53, -1):
            with self.assertRaises(window.BadWindow):
                window.weeks(bad)

    def test_today_in_a_bad_zone_falls_back_to_the_local_date(self):
        self.assertIsInstance(window.today_in("Nope/Nowhere"), date)
        self.assertIsInstance(window.today_in(None), date)


class QueryTest(unittest.TestCase):
    def test_changed_in_includes_the_last_day(self):
        self.assertEqual(
            queries.changed_in(None, date(2026, 10, 1), date(2026, 10, 7)),
            'assignee = currentUser() AND statusCategory in ("Done", "In Progress") '
            'AND statusCategoryChangedDate >= "2026-10-01" AND statusCategoryChangedDate < "2026-10-08" '
            "ORDER BY statusCategoryChangedDate DESC")

    def test_a_person_and_a_project_narrow_the_query(self):
        jql = queries.open_of("712020:abc", "PLATE")
        self.assertEqual(jql, 'assignee = "712020:abc" AND project = PLATE AND statusCategory != Done '
                              "ORDER BY priority DESC, duedate ASC")

    def test_done_since(self):
        self.assertEqual(queries.done_since(None, date(2026, 9, 14)),
                         'assignee = currentUser() AND statusCategory = Done AND statusCategoryChangedDate >= '
                         '"2026-09-14" ORDER BY statusCategoryChangedDate DESC')

    def test_unowned_and_by_keys(self):
        self.assertEqual(queries.unowned_in(["PLATE-1", "PLATE-2"]),
                         "parent in (PLATE-1, PLATE-2) AND assignee is EMPTY AND statusCategory != Done "
                         "ORDER BY priority DESC")
        self.assertEqual(queries.by_keys(["PLATE-3"]), "key in (PLATE-3)")

    def test_nothing_user_supplied_can_break_out_of_the_jql(self):
        with self.assertRaises(ValueError):
            queries.open_of('x" OR 1=1 --')
        with self.assertRaises(ValueError):
            queries.open_of(None, "PLATE OR 1=1")
        with self.assertRaises(ValueError):
            queries.by_keys(["PLATE-1) OR (a = b"])
        with self.assertRaises(ValueError):
            queries.by_keys([])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_queries.py"`
Expected: ERROR `ImportError: cannot import name 'queries' from 'jkan'`.

- [ ] **Step 3: Implement** — create `jkan/window.py`:

```python
"""Dates for the reports: strict ISO days, the windows they make, and today in the team's time zone.

The CLI never reads natural language: the agent turns "ayer" or "la semana pasada" into dates (see standup/SKILL.md).
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional, Tuple


class BadWindow(ValueError):
    """A date or a range the reports cannot use; the message says how to fix it."""


def parse_day(text: Optional[str]) -> _dt.date:
    try:
        return _dt.date.fromisoformat(text)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise BadWindow(f"{text!r} is not a date: use YYYY-MM-DD (the agent turns 'ayer' into a date)") from None


def span(since: str, until: Optional[str], today: _dt.date) -> Tuple[_dt.date, _dt.date]:
    start = parse_day(since)
    end = parse_day(until) if until else today
    if start > end:
        raise BadWindow(f"--since {start} is after --until {end}")
    return start, end


def horizon(until: Optional[str], today: _dt.date) -> _dt.date:
    end = parse_day(until) if until else today
    if end < today:
        raise BadWindow(f"--until {end} is before today ({today}): use jk done for the past")
    return end


def weeks(count: int) -> int:
    if not 1 <= count <= 52:
        raise BadWindow(f"--weeks {count}: use a number from 1 to 52")
    return count


def today_in(zone: Optional[str]) -> _dt.date:
    """Today's date in `zone` (e.g. America/Argentina/Buenos_Aires); the local date when the zone is unknown."""
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo(zone)).date()  # type: ignore[arg-type]
    except (ImportError, KeyError, TypeError, ValueError):
        return _dt.date.today()
```

Create `jkan/queries.py`:

```python
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
```

In `conventions.json`, replace the `"blocked_statuses"` block so it reads (keep the other keys as they are, set `blocked_link` to the text found in Task 0 if it differs):

```json
  "blocked_statuses": [
    "Blocked"
  ],
  "blocked_link": "is blocked by",
  "timezone": "America/Argentina/Buenos_Aires",
```

and append this string to the end of the `"notes"` array (add a comma to the previous last item):

```json
    "Reports (jk done|next|blocked|load|stats) read Jira live. wip_limit (optional, a number) turns jk load into a verdict; without it the command shows only measured numbers."
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_queries.py"` then `python3 -m unittest discover -s tests`
Expected: `OK` for both (the second runs the whole suite; the new `conventions.json` keys must break nothing).

- [ ] **Step 5: Commit**

```bash
git add jkan/window.py jkan/queries.py conventions.json tests/test_queries.py
git commit -m "feat(reports): strict ISO windows and validated JQL builders"
```

---

### Task 3: What to do next, and what blocks

**Files:**
- Create: `jkan/standup.py`
- Test: `tests/test_standup.py`

**Interfaces:**
- Consumes: `queries.open_of`, `queries.unowned_in` (Task 2); `FakeJira.search`, `helpers.issue` (Task 1).
- Produces: `standup.search(jira, jql, conv) -> List[dict]`; `standup.blockers(issue, blocked_statuses) -> List[{"by","title","status","owner"}]`; `standup.blocked_rows(open_issues, conv) -> List[dict]` (each row = blocker fields + `"issue"`); `standup.next_tables(open_issues, unowned, today, until, conv) -> {"ready": [issue], "due": [{"issue","overdue","blocked"}], "unowned": [issue]}`; `standup.epic_keys(open_issues, owned_epics, epic_type) -> List[str]`; `standup.gather_next(jira, person, until, today, conv)`; `standup.gather_blocked(jira, person, conv)`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_standup.py`

```python
from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, FakeJira, issue
from jkan import standup

TODAY, UNTIL = date(2026, 10, 8), date(2026, 10, 10)
EPIC = {"key": "PLATE-100", "summary": "Épica", "issuetype": "Epic"}


class BlockedTest(unittest.TestCase):
    def test_a_link_beats_a_flag_and_a_flag_beats_a_status(self):
        open_issues = [
            issue("PLATE-1", flagged=True),
            issue("PLATE-2", status="Blocked", category="in_progress"),
            issue("PLATE-3", blocked_by=[
                {"key": "PLATE-8", "summary": "Okta", "status": "En curso", "category": "in_progress", "assignee": "Ana"},
                {"key": "PLATE-9", "summary": "Ya está", "status": "Done", "category": "done", "assignee": "Beto"}]),
            issue("PLATE-4", flagged=True, category="done"),
            issue("PLATE-5"),
        ]
        rows = standup.blocked_rows(open_issues, CONVENTIONS)
        self.assertEqual([(r["issue"]["key"], r["by"], r["owner"]) for r in rows], [
            ("PLATE-1", "Flagged, sin link", ""),
            ("PLATE-2", "Estado Blocked, sin link", ""),
            ("PLATE-3", "PLATE-8", "Ana")])

    def test_a_blocker_nobody_owns_says_so(self):
        row = standup.blocked_rows([issue("PLATE-3", blocked_by=[
            {"key": "PLATE-8", "summary": "", "status": "", "category": "", "assignee": ""}])], CONVENTIONS)[0]
        self.assertEqual(row["owner"], "sin dueño")


class NextTest(unittest.TestCase):
    OPEN = [
        issue("PLATE-1", priority="Low", duedate="2026-10-09"),
        issue("PLATE-2", priority="High"),
        issue("PLATE-3", priority="High", duedate="2026-10-05"),
        issue("PLATE-4", priority="Highest", flagged=True),
        issue("PLATE-5", priority="Medium", status="Blocked", category="in_progress", duedate="2026-10-10"),
        issue("PLATE-6", priority=""),
    ]

    def test_ready_is_ordered_by_priority_then_due_date_and_leaves_blocked_out(self):
        tables = standup.next_tables(self.OPEN, [], TODAY, UNTIL, CONVENTIONS)
        self.assertEqual([i["key"] for i in tables["ready"]], ["PLATE-3", "PLATE-2", "PLATE-1", "PLATE-6"])

    def test_due_lists_the_window_marking_overdue_and_blocked(self):
        tables = standup.next_tables(self.OPEN, [], TODAY, UNTIL, CONVENTIONS)
        self.assertEqual([(r["issue"]["key"], r["overdue"], r["blocked"]) for r in tables["due"]], [
            ("PLATE-3", True, False), ("PLATE-1", False, False), ("PLATE-5", False, True)])

    def test_unowned_is_sorted_by_priority(self):
        tables = standup.next_tables([], [issue("PLATE-7", priority="Low", assignee=None),
                                          issue("PLATE-8", priority="High", assignee=None)], TODAY, UNTIL, CONVENTIONS)
        self.assertEqual([i["key"] for i in tables["unowned"]], ["PLATE-8", "PLATE-7"])

    def test_epic_keys_come_from_parents_and_owned_epics(self):
        keys = standup.epic_keys([issue("PLATE-1", parent=EPIC), issue("PLATE-2", parent={**EPIC, "key": "PLATE-9", "issuetype": "Tarea"})],
                                 [issue("PLATE-101", issuetype="Epic")], "Epic")
        self.assertEqual(keys, ["PLATE-100", "PLATE-101"])


class GatherTest(unittest.TestCase):
    def test_gather_next_asks_for_unowned_work_in_the_epics_it_found(self):
        jira = FakeJira()
        mine = [issue("PLATE-1", parent=EPIC), issue("PLATE-101", issuetype="Epic", summary="Mi épica")]
        jira.search_answer = lambda jql: [issue("PLATE-7", assignee=None)] if jql.startswith("parent in") else mine
        tables = standup.gather_next(jira, None, UNTIL, TODAY, CONVENTIONS)
        self.assertEqual([i["key"] for i in tables["ready"]], ["PLATE-1"])  # the epic is a container, not work
        self.assertEqual([i["key"] for i in tables["unowned"]], ["PLATE-7"])
        self.assertTrue(jira.jqls[1].startswith("parent in (PLATE-100, PLATE-101)"))

    def test_gather_next_skips_the_unowned_query_when_there_are_no_epics(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1")]
        standup.gather_next(jira, None, UNTIL, TODAY, CONVENTIONS)
        self.assertEqual(len(jira.jqls), 1)

    def test_gather_blocked_ignores_epics(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", flagged=True), issue("PLATE-2", issuetype="Epic", flagged=True)]
        rows = standup.gather_blocked(jira, "acc-ana", CONVENTIONS)
        self.assertEqual([r["issue"]["key"] for r in rows], ["PLATE-1"])
        self.assertIn('assignee = "acc-ana"', jira.jqls[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_standup.py"`
Expected: ERROR `ImportError: cannot import name 'standup' from 'jkan'`.

- [ ] **Step 3: Implement** — create `jkan/standup.py`:

```python
"""What each report shows, picked from normalized issues (Jira.search). Pure functions, plus one `gather_*` per
report that asks Jira. Epics are containers, not work: they never appear as rows of next, blocked, load or stats."""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from . import queries

FAR = "9999-12-31"  # sorts after any real due date
MAX_EPICS = 50


def search(jira, jql: str, conv: dict) -> List[dict]:
    return jira.search(jql, blocked_link=conv.get("blocked_link") or "is blocked by")


def _rank(conv: dict, priority: str) -> int:
    order = conv.get("priorities") or []
    return order.index(priority) if priority in order else len(order)


def blockers(issue: dict, blocked_statuses: List[str]) -> List[dict]:
    """Why an open issue is blocked: one row per unresolved blocker; with none linked, the flag or the status itself."""
    if issue["category"] == "done":
        return []
    rows = [{"by": b["key"], "title": b["summary"], "status": b["status"], "owner": b["assignee"] or "sin dueño"}
            for b in issue["blocked_by"] if b["category"] != "done"]
    if rows:
        return rows
    if issue["flagged"]:
        return [{"by": "Flagged, sin link", "title": "", "status": "", "owner": ""}]
    if issue["status"].lower() in {name.lower() for name in blocked_statuses}:
        return [{"by": f"Estado {issue['status']}, sin link", "title": "", "status": "", "owner": ""}]
    return []


def blocked_rows(open_issues: List[dict], conv: dict) -> List[dict]:
    statuses = conv.get("blocked_statuses") or []
    return [dict(why, issue=i) for i in open_issues for why in blockers(i, statuses)]


def next_tables(open_issues: List[dict], unowned: List[dict], today: _dt.date, until: _dt.date, conv: dict) -> dict:
    statuses = conv.get("blocked_statuses") or []
    by_priority = lambda i: (_rank(conv, i["priority"]), i["duedate"] or FAR, i["key"])  # noqa: E731
    ready = sorted((i for i in open_issues if not blockers(i, statuses)), key=by_priority)
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
    found = search(jira, queries.open_of(person, conv.get("project")), conv)
    return ([i for i in found if i["issuetype"] != epic_type], [i for i in found if i["issuetype"] == epic_type])


def gather_next(jira, person: Optional[str], until: _dt.date, today: _dt.date, conv: dict) -> dict:
    work, epics = _open(jira, person, conv)
    keys = epic_keys(work, epics, conv["issue_types"]["epic"])
    unowned = search(jira, queries.unowned_in(keys), conv) if keys else []
    return next_tables(work, unowned, today, until, conv)


def gather_blocked(jira, person: Optional[str], conv: dict) -> List[dict]:
    return blocked_rows(_open(jira, person, conv)[0], conv)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_standup.py"`
Expected: `Ran 9 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add jkan/standup.py tests/test_standup.py
git commit -m "feat(reports): pick what to do next and what blocks, by priority and due date"
```

---

### Task 4: The "done" tree

**Files:**
- Modify: `jkan/standup.py` (append)
- Test: `tests/test_done_tree.py`

**Interfaces:**
- Consumes: `queries.changed_in`, `queries.by_keys`, `standup.search`.
- Produces: `standup.done_tree(issues, parents, epic_type) -> List[node]` where `node = {"issue": dict, "context": bool, "children": [node]}`; `standup.gather_done(jira, person, since, until, conv) -> {"done": int, "in_progress": int, "tree": [node]}`. The synthetic "Sin épica" root has `issue["key"] == ""`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_done_tree.py`

```python
from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, FakeJira, issue
from jkan import standup

EPIC = {"key": "PLATE-100", "summary": "Épica", "issuetype": "Epic"}
TASK = {"key": "PLATE-102", "summary": "T", "issuetype": "Tarea"}


def shape(tree):
    return [(n["issue"]["key"], n["context"], shape(n["children"])) for n in tree]


class DoneTreeTest(unittest.TestCase):
    def test_a_subtask_reaches_its_epic_through_a_parent_that_did_not_change(self):
        story = issue("PLATE-101", category="done", changed="2026-10-07", parent=EPIC)
        parent_task = issue("PLATE-102", parent=EPIC)
        sub = issue("PLATE-103", issuetype="Subtarea", category="done", changed="2026-10-06", parent=TASK)
        loose = issue("PLATE-104", category="in_progress", changed="2026-10-07")
        tree = standup.done_tree([story, sub, loose], {"PLATE-102": parent_task}, "Epic")
        self.assertEqual(shape(tree), [
            ("PLATE-100", True, [("PLATE-101", False, []), ("PLATE-102", True, [("PLATE-103", False, [])])]),
            ("", True, [("PLATE-104", False, [])])])
        self.assertEqual(tree[1]["issue"]["summary"], "Sin épica")

    def test_children_are_ordered_by_issue_number_not_by_text(self):
        a = issue("PLATE-1000", parent=EPIC, category="done", changed="2026-10-07")
        b = issue("PLATE-999", parent=EPIC, category="done", changed="2026-10-07")
        self.assertEqual([c["issue"]["key"] for c in standup.done_tree([a, b], {}, "Epic")[0]["children"]],
                         ["PLATE-999", "PLATE-1000"])

    def test_a_closed_epic_is_not_context(self):
        epic = issue("PLATE-100", issuetype="Epic", category="done", changed="2026-10-07")
        story = issue("PLATE-101", parent=EPIC, category="done", changed="2026-10-07")
        self.assertEqual(shape(standup.done_tree([epic, story], {}, "Epic")),
                         [("PLATE-100", False, [("PLATE-101", False, [])])])

    def test_an_unreachable_parent_does_not_loop_or_crash(self):
        orphan = issue("PLATE-5", parent={"key": "PLATE-4", "summary": "", "issuetype": "Tarea"}, category="done")
        self.assertEqual(shape(standup.done_tree([orphan], {}, "Epic")),
                         [("", True, [("PLATE-4", True, [("PLATE-5", False, [])])])])


class GatherDoneTest(unittest.TestCase):
    def test_counts_exclude_epics_and_the_missing_parent_is_fetched_once(self):
        sub = issue("PLATE-103", issuetype="Subtarea", category="done", changed="2026-10-06", parent=TASK)
        story = issue("PLATE-101", category="done", changed="2026-10-07", parent=EPIC)
        wip = issue("PLATE-105", category="in_progress", changed="2026-10-07", parent=EPIC)
        epic = issue("PLATE-100", issuetype="Epic", category="in_progress", changed="2026-10-07")
        parent_task = issue("PLATE-102", parent=EPIC)
        jira = FakeJira()
        jira.search_answer = lambda jql: [parent_task] if jql.startswith("key in") else [sub, story, wip, epic]
        result = standup.gather_done(jira, None, date(2026, 10, 1), date(2026, 10, 7), CONVENTIONS)
        self.assertEqual((result["done"], result["in_progress"]), (2, 1))
        self.assertEqual(jira.jqls[1], "key in (PLATE-102)")
        self.assertEqual(len(jira.jqls), 2)

    def test_empty_window(self):
        jira = FakeJira()
        result = standup.gather_done(jira, None, date(2026, 10, 1), date(2026, 10, 7), CONVENTIONS)
        self.assertEqual(result, {"done": 0, "in_progress": 0, "tree": []})
        self.assertEqual(len(jira.jqls), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_done_tree.py"`
Expected: FAIL `AttributeError: module 'jkan.standup' has no attribute 'done_tree'`.

- [ ] **Step 3: Implement** — append to `jkan/standup.py`:

```python
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
    in_window = set(known) & {i["key"] for i in issues}
    nodes: dict = {}
    linked: set = set()
    order: List[str] = []
    for issue in issues:
        chain = [issue]
        while chain[-1]["parent"] and len(chain) < 4:
            up = chain[-1]["parent"]
            chain.append(known.get(up["key"]) or _stub(up))
        below = None
        for item in chain:  # the issue first, its epic last
            if item["key"] not in nodes:
                nodes[item["key"]] = {"issue": item, "context": item["key"] not in in_window, "children": []}
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
    need = sorted({i["parent"]["key"] for i in issues
                   if i["issuetype"] == types["subtask"] and i["parent"] and i["parent"]["key"] not in have})
    parents = {i["key"]: i for i in search(jira, queries.by_keys(need), conv)} if need else {}
    work = [i for i in issues if i["issuetype"] != types["epic"]]
    return {"done": sum(1 for i in work if i["category"] == "done"),
            "in_progress": sum(1 for i in work if i["category"] == "in_progress"),
            "tree": done_tree(issues, parents, types["epic"])}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_done_tree.py"` then `python3 -m unittest discover -s tests -p "test_standup.py"`
Expected: `OK` for both.

- [ ] **Step 5: Commit**

```bash
git add jkan/standup.py tests/test_done_tree.py
git commit -m "feat(reports): tree of what changed, reaching the epic through parents outside the window"
```

---

### Task 5: Metrics and load

**Files:**
- Create: `jkan/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `queries.done_since`, `standup.search`, `standup.blockers`.
- Produces: `stats.percentile(values, pct)`; `stats.spread(values) -> None | {"n","median","p85"}`; `stats.week_of(day)`; `stats.throughput(done, today, weeks) -> [{"week","closed","partial"}]` (oldest first, zero weeks included); `stats.lead_days(done) -> [int]`; `stats.wip(open_issues, today) -> [{"issue","days","stalled"}]`; `stats.on_time(done) -> None | {"n","on_time","pct"}`; `stats.mix(done, areas) -> {"by_area","by_type"}`; `stats.oldest(open_issues, today, n=3)`; `stats.compute(done, open_issues, today, weeks, conv) -> dict` with keys `weeks, weekly, lead, wip, on_time, mix, oldest`; `stats.load_numbers(done, open_issues, today, weeks, conv) -> dict` with keys `open, in_progress, blocked, overdue, due_soon, weekly, verdict`; `stats.gather_history(jira, person, today, weeks, conv) -> (done, open_issues)`; constants `STALLED_DAYS = 7`, `DUE_SOON_DAYS = 7`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_stats.py`

```python
from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, FakeJira, issue
from jkan import stats

TODAY = date(2026, 10, 8)  # a Thursday: its week starts on Monday 2026-10-05


class MathTest(unittest.TestCase):
    def test_percentile_is_nearest_rank(self):
        ten = list(range(1, 11))
        self.assertEqual((stats.percentile(ten, 50), stats.percentile(ten, 85)), (5, 9))
        self.assertEqual(stats.spread([4]), {"n": 1, "median": 4, "p85": 4})
        self.assertIsNone(stats.spread([]))

    def test_throughput_buckets_by_monday_and_keeps_empty_weeks(self):
        done = [issue("A", changed="2026-10-07"), issue("B", changed="2026-10-05"), issue("C", changed="2026-09-30"),
                issue("D", changed="2026-09-10"), issue("E", changed=None)]
        self.assertEqual(stats.throughput(done, TODAY, 3), [
            {"week": "2026-09-21", "closed": 0, "partial": False},
            {"week": "2026-09-28", "closed": 1, "partial": False},
            {"week": "2026-10-05", "closed": 2, "partial": True}])

    def test_lead_days_uses_resolution_then_the_last_change(self):
        done = [issue("A", created="2026-10-01", resolved="2026-10-04"), issue("B", created="2026-10-01", changed="2026-10-02"),
                issue("C", created=None)]
        self.assertEqual(stats.lead_days(done), [3, 1])

    def test_wip_age_flags_the_stalled(self):
        open_issues = [issue("A", category="in_progress", changed="2026-10-07"),
                       issue("B", category="in_progress", changed="2026-09-28"), issue("C"),
                       issue("D", category="in_progress", changed=None)]
        rows = stats.wip(open_issues, TODAY)
        self.assertEqual([(r["issue"]["key"], r["days"], r["stalled"]) for r in rows], [("B", 10, True), ("A", 1, False)])

    def test_on_time_only_counts_what_had_a_due_date(self):
        done = [issue("A", duedate="2026-10-05", resolved="2026-10-04"), issue("B", duedate="2026-10-05", resolved="2026-10-06"),
                issue("C", resolved="2026-10-06")]
        self.assertEqual(stats.on_time(done), {"n": 2, "on_time": 1, "pct": 50})
        self.assertIsNone(stats.on_time([issue("C")]))

    def test_mix_reads_the_area_prefix_and_the_type(self):
        done = [issue("A", summary="[BE] x"), issue("B", summary="[AI] y", issuetype="Historia"),
                issue("C", summary="[ZZ] z"), issue("D", summary="sin prefijo")]
        self.assertEqual(stats.mix(done, CONVENTIONS["areas"]),
                         {"by_area": {"BE": 1, "AI": 1, "(sin área)": 2}, "by_type": {"Tarea": 3, "Historia": 1}})

    def test_oldest_open(self):
        rows = stats.oldest([issue("A", created="2026-09-01"), issue("B", created="2026-08-01"), issue("C", created=None)], TODAY, 1)
        self.assertEqual([(r["issue"]["key"], r["days"]) for r in rows], [("B", 68)])


class LoadTest(unittest.TestCase):
    OPEN = [issue("A", category="in_progress"), issue("B", category="in_progress", flagged=True),
            issue("C", duedate="2026-10-01"), issue("D", duedate="2026-10-12"), issue("E", duedate="2026-10-20")]

    def test_numbers_are_counts_of_what_is_open(self):
        numbers = stats.load_numbers([issue("X", changed="2026-10-06")], self.OPEN, TODAY, 2, CONVENTIONS)
        self.assertEqual({k: numbers[k] for k in ("open", "in_progress", "blocked", "overdue", "due_soon")},
                         {"open": 5, "in_progress": 2, "blocked": 1, "overdue": 1, "due_soon": 1})
        self.assertEqual([w["closed"] for w in numbers["weekly"]], [0, 1])
        self.assertIsNone(numbers["verdict"])  # no wip_limit: no verdict invented

    def test_a_wip_limit_gives_room(self):
        self.assertEqual(stats.load_numbers([], self.OPEN, TODAY, 1, dict(CONVENTIONS, wip_limit=3))["verdict"],
                         {"wip_limit": 3, "room": 1})
        self.assertEqual(stats.load_numbers([], self.OPEN, TODAY, 1, dict(CONVENTIONS, wip_limit=2))["verdict"]["room"], 0)


class ComputeTest(unittest.TestCase):
    def test_compute_with_nothing_does_not_crash(self):
        result = stats.compute([], [], TODAY, 4, CONVENTIONS)
        self.assertEqual((result["lead"], result["on_time"], result["wip"], result["oldest"]), (None, None, [], []))
        self.assertEqual(len(result["weekly"]), 4)


class GatherHistoryTest(unittest.TestCase):
    def test_gather_history_drops_epics_and_starts_at_the_first_week(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: ([issue("D", changed="2026-10-06"), issue("E", issuetype="Epic")]
                                          if "statusCategory = Done" in jql else [issue("O"), issue("P", issuetype="Epic")])
        done, open_issues = stats.gather_history(jira, None, TODAY, 3, CONVENTIONS)
        self.assertEqual(([i["key"] for i in done], [i["key"] for i in open_issues]), (["D"], ["O"]))
        self.assertIn('statusCategoryChangedDate >= "2026-09-21"', jira.jqls[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_stats.py"`
Expected: ERROR `ImportError: cannot import name 'stats' from 'jkan'`.

- [ ] **Step 3: Implement** — create `jkan/stats.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_stats.py"`
Expected: `OK` (11 tests)

- [ ] **Step 5: Commit**

```bash
git add jkan/stats.py tests/test_stats.py
git commit -m "feat(reports): throughput, lead time, WIP age, on-time rate and load, measured without estimates"
```

---

### Task 6: Markdown rendering

**Files:**
- Create: `jkan/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: result shapes from Tasks 3–5; `stats.DUE_SOON_DAYS`, `stats.STALLED_DAYS`.
- Produces: `render.table(headers, rows, empty="_Nada._") -> str`; `render.head(title, owner, today, window=None, project=None) -> str`; `render.render_tree(tree) -> str`; `render.render_done(head_text, result)`; `render.render_next(head_text, tables, until, link)`; `render.render_blocked(head_text, rows, link)`; `render.render_load(head_text, name, numbers, mine_name=None, mine=None)`; `render.render_stats(head_text, s, link)`. `link` is `Callable[[str], str]` (key -> Markdown link).

- [ ] **Step 1: Write the failing tests** — create `tests/test_render.py`

```python
from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, issue
from jkan import render, stats, standup

TODAY = date(2026, 10, 8)
plain = lambda key: key  # noqa: E731
HEAD = render.head("Hecho", "vos", TODAY, (date(2026, 10, 1), date(2026, 10, 7)), "PLATE")


class TableTest(unittest.TestCase):
    def test_table_escapes_pipes_and_marks_missing_cells(self):
        self.assertEqual(render.table(["Key", "Título"], [["A", "b|c"], ["B", None]]),
                         "| Key | Título |\n| --- | --- |\n| A | b\\|c |\n| B | – |")

    def test_empty_table_says_so(self):
        self.assertEqual(render.table(["Key"], [], empty="_Nada bloqueado._"), "_Nada bloqueado._")

    def test_head_names_who_the_window_and_when(self):
        self.assertEqual(HEAD, "## Hecho\n**Quién:** vos · **Ventana:** 2026-10-01 → 2026-10-07 · **Proyecto:** PLATE · "
                               "**Consultado:** 2026-10-08")


class DoneTest(unittest.TestCase):
    def test_tree_uses_box_characters_and_marks_context(self):
        epic = {"key": "PLATE-100", "summary": "Épica", "issuetype": "Epic"}
        story = issue("PLATE-101", category="done", status="Done", changed="2026-10-07", parent=epic)
        sub = issue("PLATE-103", issuetype="Subtarea", category="done", status="Done", changed="2026-10-06")
        tree = standup.done_tree([story, sub], {}, "Epic")
        text = render.render_tree(tree)
        self.assertEqual(text.splitlines(), [
            "PLATE-100 Épica (contexto)", "└─ PLATE-101 Summary of PLATE-101 · Done · 2026-10-07",
            "Sin épica", "└─ PLATE-103 Summary of PLATE-103 · Done · 2026-10-06"])

    def test_render_done_has_totals_and_a_fenced_tree_or_an_empty_message(self):
        busy = render.render_done(HEAD, {"done": 7, "in_progress": 3, "tree": standup.done_tree([issue("PLATE-5")], {}, "Epic")})
        self.assertIn("**7 cerradas · 3 en curso**", busy)
        self.assertIn("```text", busy)
        self.assertIn("último cambio", busy)
        self.assertIn("_Nada en esta ventana._", render.render_done(HEAD, {"done": 0, "in_progress": 0, "tree": []}))


class NextAndBlockedTest(unittest.TestCase):
    def test_render_next_has_three_tables(self):
        tables = standup.next_tables(
            [issue("PLATE-1", priority="High", duedate="2026-10-05"), issue("PLATE-2", status="Blocked", flagged=True, duedate="2026-10-09")],
            [issue("PLATE-7", assignee=None, parent={"key": "PLATE-100", "summary": "", "issuetype": "Epic"})],
            TODAY, date(2026, 10, 10), CONVENTIONS)
        text = render.render_next(HEAD, tables, date(2026, 10, 10), plain)
        self.assertIn("### Para hacer ya", text)
        self.assertIn("| PLATE-1 | Summary of PLATE-1 | High | 2026-10-05 | Backlog |", text)
        self.assertIn("### Vence hasta 2026-10-10", text)
        self.assertIn("vencido 2026-10-05", text)
        self.assertIn("Blocked (bloqueado)", text)
        self.assertIn("### Sin dueño en sus épicas (para tomar)", text)
        self.assertIn("| PLATE-7 | Summary of PLATE-7 | PLATE-100 | Medium |", text)

    def test_render_blocked_links_the_blocker_or_names_the_flag(self):
        rows = standup.blocked_rows([
            issue("PLATE-1", blocked_by=[{"key": "PLATE-8", "summary": "Okta", "status": "En curso", "category": "in_progress", "assignee": "Ana"}]),
            issue("PLATE-2", flagged=True)], CONVENTIONS)
        text = render.render_blocked(HEAD, rows, lambda k: f"<{k}>")
        self.assertIn("| <PLATE-1> | Summary of PLATE-1 | <PLATE-8> Okta | En curso | Ana |", text)
        self.assertIn("| <PLATE-2> | Summary of PLATE-2 | Flagged, sin link | – | – |", text)
        self.assertIn("_Nada bloqueado._", render.render_blocked(HEAD, [], plain))


class LoadAndStatsTest(unittest.TestCase):
    def numbers(self, **conv):
        return stats.load_numbers([issue("X", changed="2026-10-06")], [issue("A", category="in_progress")], TODAY, 2,
                                  dict(CONVENTIONS, **conv))

    def test_load_without_a_limit_gives_numbers_and_no_verdict(self):
        text = render.render_load(HEAD, "Ana Gómez", self.numbers())
        self.assertIn("| Métrica | Ana Gómez |", text)
        self.assertIn("| En curso (WIP) | 1 |", text)
        self.assertIn("| Cerrados por semana (viejo → nuevo; * = semana en curso) | 0 · 1* |", text)
        self.assertIn("Sin veredicto", text)

    def test_load_compares_side_by_side_and_gives_a_verdict_when_there_is_a_limit(self):
        text = render.render_load(HEAD, "Ana Gómez", self.numbers(wip_limit=3), "vos", self.numbers())
        self.assertIn("| Métrica | Ana Gómez | vos |", text)
        self.assertIn("| En curso (WIP) | 1 | 1 |", text)
        self.assertIn("**Ana Gómez:** WIP 1/3 → tiene espacio para 2 más", text)
        self.assertIn("sin espacio", render.render_load(HEAD, "Ana", self.numbers(wip_limit=1)))

    def test_render_stats_reports_n_and_warns_when_it_is_small(self):
        done = [issue("A", created="2026-10-01", resolved="2026-10-04", duedate="2026-10-05", changed="2026-10-04", summary="[BE] x")]
        s = stats.compute(done, [issue("B", category="in_progress", changed="2026-09-20", created="2026-08-01")], TODAY, 2, CONVENTIONS)
        text = render.render_stats(HEAD, s, plain)
        self.assertIn("n=1 · mediana 3 d · p85 3 d · pocos casos", text)
        self.assertIn("1/1 a tiempo (100%)", text)
        self.assertIn("estancado", text)
        self.assertIn("| BE | 1 |", text)

    def test_render_stats_with_nothing_says_so(self):
        text = render.render_stats(HEAD, stats.compute([], [], TODAY, 2, CONVENTIONS), plain)
        self.assertIn("Sin cierres en el período", text)
        self.assertIn("Ninguno de lo cerrado tenía fecha de vencimiento", text)
        self.assertIn("_Nada en curso._", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_render.py"`
Expected: ERROR `ImportError: cannot import name 'render' from 'jkan'`.

- [ ] **Step 3: Implement** — create `jkan/render.py`:

```python
"""Markdown for the reports: tables (keys are links) and trees (in a code block, so the lines stay aligned).

Labels are Spanish, like `jk board`; error messages elsewhere stay English."""
from __future__ import annotations

import datetime as _dt
import re
from typing import Callable, List, Optional

from . import stats

Link = Callable[[str], str]
KEYLIKE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
NOTE_DONE = ("_Nota: Jira guarda solo el último cambio de estado, así que un issue que pasó por «en curso» y luego a "
             "Done figura con la fecha de Done. «Hecho» significa asignado a la persona (inferencia: si otra persona "
             "cerró un issue suyo, igual aparece)._")


def _cell(value) -> str:
    return "–" if value in (None, "") else str(value).replace("|", "\\|").replace("\n", " ")


def table(headers: List[str], rows: List[list], empty: str = "_Nada._") -> str:
    if not rows:
        return empty
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    return "\n".join(lines + ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows])


def head(title: str, owner: str, today: _dt.date, window: Optional[tuple] = None, project: Optional[str] = None) -> str:
    parts = [f"**Quién:** {owner}"]
    if window:
        parts.append(f"**Ventana:** {window[0]} → {window[1]}")
    if project:
        parts.append(f"**Proyecto:** {project}")
    parts.append(f"**Consultado:** {today}")
    return f"## {title}\n" + " · ".join(parts)


def _label(node: dict) -> str:
    issue = node["issue"]
    if not issue["key"]:
        return issue["summary"]
    bits = [f"{issue['key']} {issue['summary']}"]
    if not node["context"]:
        bits += [b for b in (issue["status"], issue["changed"]) if b]
    return " · ".join(bits) + (" (contexto)" if node["context"] else "")


def _branch(children: List[dict], prefix: str) -> List[str]:
    lines: List[str] = []
    for k, child in enumerate(children):
        last = k == len(children) - 1
        lines.append(f"{prefix}{'└─ ' if last else '├─ '}{_label(child)}")
        lines += _branch(child["children"], prefix + ("   " if last else "│  "))
    return lines


def render_tree(tree: List[dict]) -> str:
    lines: List[str] = []
    for root in tree:
        lines.append(_label(root))
        lines += _branch(root["children"], "")
    return "\n".join(lines)


def render_done(head_text: str, result: dict) -> str:
    totals = f"**{result['done']} cerradas · {result['in_progress']} en curso**"
    body = f"```text\n{render_tree(result['tree'])}\n```" if result["tree"] else "_Nada en esta ventana._"
    return "\n\n".join([head_text, totals, body, NOTE_DONE])


def render_next(head_text: str, tables: dict, until: _dt.date, link: Link) -> str:
    ready = table(["Key", "Título", "Prioridad", "Vence", "Estado"],
                  [[link(i["key"]), i["summary"], i["priority"], i["duedate"], i["status"]] for i in tables["ready"]],
                  "_Nada para hacer ya._")
    due = table(["Key", "Título", "Vence", "Estado"],
                [[link(r["issue"]["key"]), r["issue"]["summary"],
                  ("vencido " if r["overdue"] else "") + r["issue"]["duedate"],
                  r["issue"]["status"] + (" (bloqueado)" if r["blocked"] else "")] for r in tables["due"]],
                "_Nada con fecha en la ventana._")
    unowned = table(["Key", "Título", "Épica", "Prioridad"],
                    [[link(i["key"]), i["summary"], i["parent"]["key"] if i["parent"] else "", i["priority"]]
                     for i in tables["unowned"]], "_Nada sin dueño en sus épicas._")
    return "\n\n".join([head_text, "### Para hacer ya\n" + ready, f"### Vence hasta {until}\n" + due,
                        "### Sin dueño en sus épicas (para tomar)\n" + unowned])


def _by(row: dict, link: Link) -> str:
    return f"{link(row['by'])} {row['title']}".strip() if KEYLIKE.match(row["by"]) else row["by"]


def render_blocked(head_text: str, rows: List[dict], link: Link) -> str:
    body = table(["Key", "Título", "Bloqueado por", "Estado del bloqueador", "Dueño del bloqueador"],
                 [[link(r["issue"]["key"]), r["issue"]["summary"], _by(r, link), r["status"], r["owner"]] for r in rows],
                 "_Nada bloqueado._")
    return head_text + "\n\n" + body


METRICS = (("Abiertos asignados", "open"), ("En curso (WIP)", "in_progress"), ("Bloqueados", "blocked"),
           ("Vencidos", "overdue"), (f"Vencen en {stats.DUE_SOON_DAYS} días", "due_soon"))


def _weekly(weekly: List[dict]) -> str:
    return " · ".join(f"{w['closed']}{'*' if w['partial'] else ''}" for w in weekly)


def render_load(head_text: str, name: str, numbers: dict, mine_name: Optional[str] = None,
                mine: Optional[dict] = None) -> str:
    rows = [[label, numbers[key]] + ([mine[key]] if mine else []) for label, key in METRICS]
    rows.append(["Cerrados por semana (viejo → nuevo; * = semana en curso)", _weekly(numbers["weekly"])]
                + ([_weekly(mine["weekly"])] if mine else []))
    grid = table(["Métrica", name] + ([mine_name] if mine else []), rows)
    verdict = numbers["verdict"]
    if verdict:
        room = (f"tiene espacio para {verdict['room']} más" if verdict["room"] > 0 else "sin espacio")
        line = f"**{name}:** WIP {numbers['in_progress']}/{verdict['wip_limit']} → {room}"
    else:
        line = ("_Sin veredicto: no hay `wip_limit` en .jira-kanban/conventions.json y Jira no tiene estimaciones en "
                "PLATE. Lo de arriba es lo medido; el umbral lo pone el equipo._")
    return "\n\n".join([head_text, grid, line])


def render_stats(head_text: str, s: dict, link: Link) -> str:
    weekly = table(["Semana (lunes)", "Cerrados"],
                   [[w["week"], f"{w['closed']}{' (en curso)' if w['partial'] else ''}"] for w in s["weekly"]])
    lead = s["lead"]
    lead_text = (f"n={lead['n']} · mediana {lead['median']} d · p85 {lead['p85']} d"
                 + (" · pocos casos, no concluyas nada" if lead["n"] < 10 else "")) if lead else "_Sin cierres en el período._"
    wip = table(["Key", "Título", "Días sin cambio", "Estado"],
                [[link(r["issue"]["key"]), r["issue"]["summary"], r["days"], "estancado" if r["stalled"] else ""]
                 for r in s["wip"]], "_Nada en curso._")
    on_time = s["on_time"]
    on_time_text = (f"{on_time['on_time']}/{on_time['n']} a tiempo ({on_time['pct']}%)" if on_time
                    else "_Ninguno de lo cerrado tenía fecha de vencimiento._")
    by_area = table(["Área", "Cerrados"], [[k, v] for k, v in sorted(s["mix"]["by_area"].items())], "_Sin cierres._")
    by_type = table(["Tipo", "Cerrados"], [[k, v] for k, v in sorted(s["mix"]["by_type"].items())], "_Sin cierres._")
    oldest = table(["Key", "Título", "Días abierto"],
                   [[link(r["issue"]["key"]), r["issue"]["summary"], r["days"]] for r in s["oldest"]], "_Nada abierto._")
    return "\n\n".join([head_text, f"### Velocidad: issues cerrados por semana (últimas {s['weeks']})\n" + weekly,
                        "### Lead time (creación → cierre)\n" + lead_text,
                        f"### Edad del WIP (estancado ≥ {stats.STALLED_DAYS} días)\n" + wip,
                        "### Cumplimiento de fechas\n" + on_time_text,
                        "### Mezcla de trabajo\n" + by_area + "\n\n" + by_type, "### Backlog más viejo\n" + oldest])
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_render.py"`
Expected: `OK` (11 tests). If `test_tree_uses_box_characters...` fails on line order, print `render.render_tree(tree)` and fix the test's expectation only if the tree is correct (epic first, "Sin épica" last).

- [ ] **Step 5: Commit**

```bash
git add jkan/render.py tests/test_render.py
git commit -m "feat(reports): render trees and tables for done, next, blocked, load and stats"
```

---

### Task 7: Wire the commands into `jk`

**Files:**
- Modify: `jkan/cli.py` (docstring line 1, imports line 11, `main` signature line 104, parser block before line 116, dispatch after line 135)
- Test: `tests/test_report_cli.py`

**Interfaces:**
- Consumes: everything above; `people.resolve`, `people.NotResolved`.
- Produces: `cli.main(argv, client=..., today=None)`; commands `done --since D [--until D]`, `next [--until D]`, `blocked`, `load [--weeks N]`, `stats [--weeks N]`, all with `--person Q`, `--jira-project KEY`, `--project DIR`, `--json`. Exit 0 ok, 1 for a bad window / unresolved person, 2 for a Jira failure.

- [ ] **Step 1: Write the failing tests** — create `tests/test_report_cli.py`

```python
from __future__ import annotations

import contextlib
import io
import json
import unittest
from datetime import date

from helpers import FakeJira, issue, make_project
from jkan import cli

TODAY = date(2026, 10, 8)


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args + ["--project", str(make_project())], client=lambda project: jira, today=lambda: TODAY)
    return code, out.getvalue(), err.getvalue()


class ReportCliTest(unittest.TestCase):
    def test_done_prints_the_window_the_totals_and_the_tree_and_writes_nothing(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-5", category="done", status="Done", changed="2026-10-07")]
        code, out, _ = run(["done", "--since", "2026-10-01", "--until", "2026-10-07"], jira)
        self.assertEqual(code, 0)
        self.assertIn("## Hecho", out)
        self.assertIn("**Ventana:** 2026-10-01 → 2026-10-07", out)
        self.assertIn("**1 cerradas · 0 en curso**", out)
        self.assertIn("PLATE-5", out)
        self.assertIn('assignee = currentUser()', jira.jqls[0])
        self.assertIn('statusCategoryChangedDate < "2026-10-08"', jira.jqls[0])
        self.assertEqual(jira.writes, [])

    def test_done_without_until_stops_at_today(self):
        jira = FakeJira()
        run(["done", "--since", "2026-10-06"], jira)
        self.assertIn('statusCategoryChangedDate < "2026-10-09"', jira.jqls[0])

    def test_a_bad_window_is_refused_before_asking_jira(self):
        for args in (["done", "--since", "ayer"], ["done", "--since", "2026-10-09"], ["next", "--until", "2026-10-01"],
                     ["stats", "--weeks", "0"], ["load", "--weeks", "99"]):
            jira = FakeJira()
            code, _, err = run(args, jira)
            self.assertEqual(code, 1, args)
            self.assertTrue(err.strip(), args)
            self.assertEqual(jira.jqls, [], args)

    def test_a_unique_person_is_queried_by_account_id(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", assignee={"id": "acc-ana", "name": "Ana Gómez"})]
        code, out, _ = run(["next", "--person", "Ana Gómez"], jira)
        self.assertEqual(code, 0)
        self.assertIn('assignee = "acc-ana"', jira.jqls[0])
        self.assertIn("**Quién:** Ana Gómez", out)

    def test_an_ambiguous_person_is_never_guessed(self):
        jira = FakeJira()
        code, _, err = run(["blocked", "--person", "Martin Fernandez"], jira)
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)
        self.assertEqual(jira.jqls, [])

    def test_next_blocked_and_json(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", flagged=True), issue("PLATE-2", priority="High")]
        code, out, _ = run(["blocked", "--json"], jira)
        self.assertEqual(code, 0)
        self.assertEqual([r["issue"]["key"] for r in json.loads(out)["rows"]], ["PLATE-1"])
        code, out, _ = run(["next"], jira)
        self.assertIn("| [PLATE-2](https://example.atlassian.net/browse/PLATE-2) |", out)

    def test_load_with_a_person_compares_with_me(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", category="in_progress")]
        code, out, _ = run(["load", "--person", "Ana Gómez", "--weeks", "2"], jira)
        self.assertEqual(code, 0)
        self.assertIn("| Métrica | Ana Gómez | vos |", out)
        self.assertEqual(len(jira.jqls), 4)  # closed + open for her, closed + open for me
        self.assertTrue(any("currentUser()" in j for j in jira.jqls) and any("acc-ana" in j for j in jira.jqls))

    def test_stats_runs_on_an_empty_account(self):
        code, out, _ = run(["stats"], FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("Sin cierres en el período", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_report_cli.py"`
Expected: ERROR `TypeError: main() got an unexpected keyword argument 'today'`.

- [ ] **Step 3: Implement** — edit `jkan/cli.py`.

Line 1 docstring → `"""jk: create | pull | push | show | board | who | assign | done | next | blocked | load | stats. Every Jira write is a dry run unless --apply is passed; the reports only read."""`

Line 11 import → `from . import config, journal, kanban, people, preview, render, standup, stats, sync, window`

Add `import datetime as _dt` to the stdlib imports (after `import argparse`). Add before `def main`:

```python
REPORTS = ("done", "next", "blocked", "load", "stats")


def _emit(args, payload, text: str) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str) if args.json else text)


def _report(jira, args, conv: dict, today: _dt.date) -> int:
    """done | next | blocked | load | stats: read only, for the user or, with --person, for a teammate."""
    try:
        person = people.resolve(jira, args.person, conv.get("project")) if args.person else None
        pid, owner = (person["id"], person["name"]) if person else (None, "vos")
        link = lambda key: f"[{key}]({jira.browse_url(key)})"  # noqa: E731
        project = conv.get("project")
        if args.cmd == "done":
            since, until = window.span(args.since, args.until, today)
            result = standup.gather_done(jira, pid, since, until, conv)
            _emit(args, result, render.render_done(render.head("Hecho", owner, today, (since, until), project), result))
        elif args.cmd == "next":
            until = window.horizon(args.until, today)
            tables = standup.gather_next(jira, pid, until, today, conv)
            _emit(args, tables, render.render_next(render.head("Para hacer", owner, today, (today, until), project),
                                                   tables, until, link))
        elif args.cmd == "blocked":
            rows = standup.gather_blocked(jira, pid, conv)
            _emit(args, {"rows": rows}, render.render_blocked(render.head("Bloqueos", owner, today, None, project),
                                                              rows, link))
        else:
            weeks = window.weeks(args.weeks)
            done, open_issues = stats.gather_history(jira, pid, today, weeks, conv)
            if args.cmd == "stats":
                result = stats.compute(done, open_issues, today, weeks, conv)
                _emit(args, result, render.render_stats(render.head("Métricas", owner, today, None, project), result, link))
            else:
                numbers = stats.load_numbers(done, open_issues, today, weeks, conv)
                mine = None
                if person:
                    mine = stats.load_numbers(*stats.gather_history(jira, None, today, weeks, conv), today, weeks, conv)
                _emit(args, {"person": numbers, "me": mine},
                      render.render_load(render.head("Carga", owner, today, None, project), owner, numbers,
                                         "vos" if mine else None, mine))
        return OK
    except (people.NotResolved, window.BadWindow, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return FINDINGS
```

Change the signature `def main(argv: Optional[List[str]] = None, client: Callable = _client) -> int:` to:

```python
def main(argv: Optional[List[str]] = None, client: Callable = _client,
         today: Optional[Callable[[], _dt.date]] = None) -> int:
```

Insert the parsers right before `args = parser.parse_args(argv)`:

```python
    for name, text in (("done", "what you (or --person) moved to In Progress or Done in a period"),
                       ("next", "what you can do now: open work by priority, what is due, what is unowned in your epics"),
                       ("blocked", "what is blocked: by link, by flag or by a blocked status"),
                       ("load", "how loaded a person is, in measured numbers (compared with you when --person is given)"),
                       ("stats", "delivery metrics: throughput, lead time, WIP age, on-time rate, mix (no estimates)")):
        r = sub.add_parser(name, help=text + " (read only)")
        r.add_argument("--person", help="a teammate: name, email or accountId (default: you)")
        r.add_argument("--jira-project", help="only this Jira project, e.g. PLATE")
        r.add_argument("--project", default=".", help="project root that holds ./.jira-kanban (default: cwd)")
        r.add_argument("--json", action="store_true", help="machine-readable output")
        if name == "done":
            r.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
            r.add_argument("--until", help="last day, YYYY-MM-DD (default: today)")
        if name == "next":
            r.add_argument("--until", help="last day of the window, YYYY-MM-DD (default: today)")
        if name in ("load", "stats"):
            r.add_argument("--weeks", type=int, default=4, help="how many weeks of history, 1 to 52 (default: 4)")
```

Add this dispatch right after the `if args.cmd == "assign": return _assign(...)` block (before `if args.cmd == "create":`):

```python
        if args.cmd in REPORTS:
            return _report(jira, args, conv, (today or (lambda: window.today_in(conv.get("timezone"))))())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_report_cli.py"` then `python3 -m unittest discover -s tests`
Expected: `OK` for both. If `test_an_ambiguous_person_is_never_guessed` fails on the message, print `err`: it must come from `people.resolve` ("matches 2 people").

- [ ] **Step 5: Commit**

```bash
git add jkan/cli.py tests/test_report_cli.py
git commit -m "feat(cli): add read-only jk done, next, blocked, load and stats with --person"
```

---

### Task 8: The sibling skill, install, docs

**Files:**
- Create: `standup/SKILL.md`, `tests/test_install.py`
- Modify: `install.sh`, `README.md`, `SKILL.md` (jira-kanban, one line), `docs/superpowers/specs/2026-10-08-jira-standup-design.md`

**Interfaces:**
- Produces: `~/.agents/skills/jira-standup -> <repo>/standup`, plus `~/.claude/skills/jira-standup` and `~/.codex/skills/jira-standup -> ../../.agents/skills/jira-standup`.

- [ ] **Step 1: Write the failing test** — create `tests/test_install.py`

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


def install(home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(["bash", str(ROOT / "install.sh")], env=env, capture_output=True, text=True)


class InstallTest(unittest.TestCase):
    def test_both_skills_are_linked_for_every_host(self):
        home = Path(tempfile.mkdtemp(prefix="jk-home-"))
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-kanban"), str(ROOT))
        self.assertEqual(os.readlink(home / ".agents/skills/jira-standup"), str(ROOT / "standup"))
        for host in (".claude", ".codex"):
            for name in ("jira-kanban", "jira-standup"):
                self.assertEqual(os.readlink(home / host / "skills" / name), f"../../.agents/skills/{name}")
        self.assertEqual(install(home).returncode, 0)  # re-running is safe

    def test_a_real_directory_is_never_replaced(self):
        home = Path(tempfile.mkdtemp(prefix="jk-home-"))
        (home / ".agents/skills/jira-standup").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests -p "test_install.py"`
Expected: FAIL (`FileNotFoundError` on `.agents/skills/jira-standup`, the script does not link it yet).

- [ ] **Step 3: Implement.** Replace `install.sh` entirely with:

```bash
#!/usr/bin/env bash
# Install the jira-kanban and jira-standup skills for Claude Code, Codex and Cursor.
#   ./install.sh
# Shared layout (same as WayOfWork): ~/.agents/skills/<name> points at this repo (jira-kanban) or at its standup/
# folder (jira-standup), and ~/.claude/skills/<name> and ~/.codex/skills/<name> point at ../../.agents/skills/<name>.
# Cursor reads ~/.agents/skills natively. Re-running is safe. A real directory with a skill's name is never
# replaced: the script stops with exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=("jira-kanban:" "jira-standup:standup")  # name:folder inside the repo ("" is the repo itself)
case "${1:-}" in
  -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

link() {  # link <target> <path>: create or refresh a symlink, never replace a real file or directory
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "refusing to replace $2: it is not a symlink; move it away and re-run" >&2
    return 1
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
}

status=0
for entry in "${SKILLS[@]}"; do
  NAME="${entry%%:*}"
  SUB="${entry#*:}"
  TARGET="$REPO${SUB:+/$SUB}"
  link "$TARGET" "$HOME/.agents/skills/$NAME" || exit 1
  for host in .claude .codex; do
    link "../../.agents/skills/$NAME" "$HOME/$host/skills/$NAME" || status=1
  done
  echo "skill: $NAME (Claude Code, Codex, Cursor) -> $TARGET"
done
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; jk needs it" >&2; status=1; }
exit "$status"
```

Create `standup/SKILL.md`:

````markdown
---
name: jira-standup
description: Use when the user asks what they (or a teammate) did in a period ("qué hice ayer", "la semana pasada"), what they can work on in the next days ("hoy", "la semana que viene"), what they are blocked on, how loaded a teammate is before assigning them work, or for their delivery metrics (velocity, lead time). Read only. To create or sync epics use jira-kanban.
---

# jira-standup

Answers four questions from Jira, live, as tables and trees the user reads at a glance. It never writes to Jira.

```bash
python3 ~/.agents/skills/jira-kanban/jk.py <done|next|blocked|load|stats> ... --project .
```

| The user asks | Run |
|---|---|
| what did I do / yesterday / last week | `jk done --since D [--until D]` |
| what can I do today / next week | `jk next [--until D]` |
| what am I blocked on | `jk blocked` |
| does <person> have room to take work | `jk load --person "<name>"` |
| my velocity / metrics | `jk stats [--weeks N]` |

## Steps

1. **Dates.** The CLI only takes `YYYY-MM-DD`. Turn the user's words into dates in `America/Argentina/Buenos_Aires`
   and say which window you used: "ayer" is `--since` = `--until` = yesterday; "la semana pasada" is Monday to Sunday
   of the previous week; "hoy" for `next` is no `--until`; "la semana que viene" is `--until` = the next Sunday.
2. **Run it** with `--jira-project KEY` if the user names a project (otherwise the project in
   `./.jira-kanban/conventions.json`, if any, applies). Show the output as it is: it is already Markdown. Do not
   retell it unless asked.
3. **Another person.** Pass `--person "<name, email or accountId>"`. If the command exits 1 listing candidates,
   show them (name and email) and ask which one; never pick. `jk who "<name>"` finds a person without running a report.
4. **Capacity.** `load` shows measured numbers. It gives a verdict only if `wip_limit` is set in
   `./.jira-kanban/conventions.json`; never invent a threshold. To assign work, hand the user
   `jk assign KEY "<person>"` (dry run) and the same command with `--apply`: the user runs that, not you.
5. **Say what the numbers are not.** `done` uses the last status change and "assigned to"; `stats` has no
   story points (PLATE has none) and no true cycle time; small `n` is flagged in the output. Repeat those limits if
   the user draws a conclusion from them.

## Rules

- Read only: never run `create`, `push`, `assign --apply` or anything with `--apply`.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- Output labels are Spanish; if the user writes in English, the tables stay as they are.
````

Edit `SKILL.md` (jira-kanban): after the line `access goes through \`jk\`; never hand-roll Jira calls or another folder layout.` add a blank line and:

```
To read what was done, what is next, what is blocked, a teammate's load or delivery metrics, use the sibling skill
`jira-standup`; this skill writes.
```

Edit `README.md`: insert before `## Kanban local` (line 111) this section, and add `jk done|next|blocked|load|stats` to the commands table (line 47, after the `jk assign` row):

```markdown
## Reportes (solo lectura)

Responden en tablas y árboles, leyendo Jira en vivo (el kanban local no guarda fechas ni asignados). La skill hermana
`jira-standup` (carpeta `standup/`) los usa; el agente traduce "ayer" o "la semana pasada" a fechas `YYYY-MM-DD`.

| Comando | Responde |
|---|---|
| `jk done --since D [--until D]` | Qué hice: árbol Épica → Historia/Tarea → Subtarea, con totales |
| `jk next [--until D]` | Qué puedo hacer: para hacer ya (por prioridad y vencimiento), lo que vence, lo que está sin dueño en mis épicas |
| `jk blocked` | Dónde estoy bloqueado: por link "is blocked by", por Flagged o por estado bloqueado |
| `jk load --person "X" [--weeks N]` | Carga de otra persona, en números medidos, al lado de la mía |
| `jk stats [--weeks N]` | Velocidad (issues cerrados por semana), lead time, edad del WIP, cumplimiento de fechas, mezcla |

Todos aceptan `--person "NOMBRE"` (si el nombre es ambiguo lista a los candidatos y no elige), `--jira-project KEY` y
`--json`. PLATE no tiene story points, así que la velocidad se mide en issues; `jk load` solo da un veredicto si
`wip_limit` está en `./.jira-kanban/conventions.json`. Límites: Jira guarda solo el último cambio de estado (un issue
que pasó por «en curso» y luego a Done figura con la fecha de Done) y «hecho» significa asignado a la persona.
```

Edit the spec `docs/superpowers/specs/2026-10-08-jira-standup-design.md`: replace `` `jk load --person X [--days N]` `` with `` `jk load --person X [--weeks N]` ``; replace the bullet `- Las keys llevan la URL del issue (`jira.browse_url`) para abrir una con un clic.` with `- Las keys de las tablas llevan la URL del issue (`jira.browse_url`); el árbol va en un bloque de código para que las líneas queden alineadas, así que ahí las keys son texto.`

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s tests -p "test_install.py"` then `python3 -m unittest discover -s tests` then `/usr/bin/python3 -m unittest discover -s tests`
Expected: `OK` for all three, no test skipped.

- [ ] **Step 5: Commit**

```bash
git add standup install.sh tests/test_install.py README.md SKILL.md docs/superpowers/specs
git commit -m "feat(standup): sibling skill jira-standup, installer links both skills, docs"
```

---

### Task 9: Verify for real (read only) and hand over

**Files:** none modified.

- [ ] **Step 1: Run the installer for real**

Run: `./install.sh`
Expected: two `skill:` lines and exit 0; `eza -l ~/.agents/skills | rg jira` shows both symlinks.

- [ ] **Step 2: Smoke-test each command against the real Jira**

Run (from `Harness/jira-kanban`, with `IC_JIRA_*` in the shell; do not print them):

```bash
python3 jk.py done --since 2026-10-05 --until 2026-10-07 --project .
python3 jk.py next --until 2026-10-14 --project .
python3 jk.py blocked --project .
python3 jk.py stats --weeks 4 --project .
python3 jk.py load --person "<a teammate>" --project .
```

Expected: each prints a Markdown block with the header line; no traceback. Read the output against Jira once by eye: does `done` list what the user actually closed on those days? Do the "Vence" and "Cumplimiento" sections say "nada"/"ninguno" if Task 0 found no `duedate` in PLATE?

- [ ] **Step 3: Full suite on both Pythons**

Run: `python3 -m unittest discover -s tests` and `/usr/bin/python3 -m unittest discover -s tests`
Expected: `OK` on both (180 original + about 60 new tests).

- [ ] **Step 4: Report to the user** the output of Step 2, any section that came back empty and why, and that nothing was pushed. Do not push: the user publishes.
