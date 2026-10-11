"""A small Jira Cloud client: v2 for issues (plain-text descriptions), v3 for search and transitions."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

ISSUE_FIELDS = "summary,description,issuetype,status,parent"
CATEGORY = {"new": "todo", "indeterminate": "in_progress", "done": "done"}  # Jira's fixed status categories
STANDUP_FIELDS = ["summary", "issuetype", "status", "parent", "assignee", "priority", "duedate", "created",
                  "resolutiondate", "statuscategorychangedate", "issuelinks", "updated", "labels", "components"]
BLOCKED_LINK = "is blocked by"


def _day(stamp: Optional[str]) -> Optional[str]:
    """Jira's 2026-10-07T14:03:00.000-0300 as its calendar day, 2026-10-07 (the date in the stamp's own offset)."""
    return stamp[:10] if stamp else None


def _state(status: dict) -> str:
    return CATEGORY.get((status.get("statusCategory") or {}).get("key", ""), "")


class JiraError(RuntimeError):
    pass


class Jira:
    def __init__(self, base_url: str, email: str, token: str, opener: Optional[Callable] = None, timeout: float = 20.0,
                 journal: Optional[Callable[[dict], None]] = None):
        self.base = base_url.rstrip("/")
        self._auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        self._open = opener or urllib.request.urlopen
        self._timeout = timeout
        # Receives every successful write (jkan/journal.py); reads are never reported.
        self._journal = journal or (lambda entry: None)
        self._flag_id: Optional[str] = None
        self._flag_known = False
        # Who a person is does not change during one run, so the dry run and the write share one answer. Issues are never
        # kept here: apply reads them again on purpose, to notice that someone moved one after the plan.
        self._me: Optional[str] = None
        self._people: Dict[str, dict] = {}
        self._searches: Dict[tuple, List[dict]] = {}

    def _send(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Basic {self._auth}", "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self._open(request, timeout=self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise JiraError(f"{method} {path}: HTTP {exc.code} {exc.read()[:300].decode(errors='replace')}") from exc
        return json.loads(raw) if raw else {}

    def browse_url(self, key: str) -> str:
        return f"{self.base}/browse/{key}"

    def myself(self) -> str:
        if self._me is None:
            self._me = self._send("GET", "/rest/api/3/myself")["accountId"]
        return self._me

    @staticmethod
    def _person(raw: dict) -> dict:
        return {"id": raw["accountId"], "name": raw.get("displayName") or "", "email": raw.get("emailAddress") or ""}

    def search_users(self, query: str, project: Optional[str] = None, limit: int = 100, page: int = 100) -> List[dict]:
        """Active people whose name or email starts with the query, as {id, name, email}.

        With a project, only people who can be assigned issues there. Bots and deactivated accounts are left out.
        Jira matches the start of a word, so it forgives no typo: that is people.py's job.
        """
        asked = (query, project, limit, page)
        if asked in self._searches:
            return [dict(p) for p in self._searches[asked]]
        path = "/rest/api/3/user/assignable/search" if project else "/rest/api/3/user/search"
        found: List[dict] = []
        start = 0
        while len(found) < limit:
            params = {"query": query, "startAt": start, "maxResults": page}
            if project:
                params["project"] = project
            batch = self._send("GET", f"{path}?{urllib.parse.urlencode(params)}")
            found += [self._person(u) for u in batch if u.get("active") and u.get("accountType") == "atlassian"]
            if len(batch) < page:
                break
            start += page
        self._searches[asked] = [dict(p) for p in found[:limit]]
        return found[:limit]

    def user(self, account_id: str) -> Optional[dict]:
        """The person behind an account id, or None when Jira does not know that id."""
        if account_id in self._people:
            return dict(self._people[account_id])
        try:
            person = self._person(self._send("GET", "/rest/api/3/user?" + urllib.parse.urlencode({"accountId": account_id})))
            self._people[account_id] = person
            return dict(person)
        except JiraError as exc:
            if "HTTP 404" in str(exc) or "HTTP 400" in str(exc):
                return None
            raise

    def assign(self, key: str, account_id: str) -> None:
        self._send("PUT", f"/rest/api/3/issue/{key}/assignee", {"accountId": account_id})
        self._journal({"action": "assign", "key": key, "accountId": account_id})

    def create(self, fields: dict) -> str:
        key = self._send("POST", "/rest/api/2/issue", {"fields": fields})["key"]
        self._journal({"action": "create", "key": key, "fields": fields})
        return key

    def _flag_field(self) -> Optional[str]:
        """The id of the "Flagged" (impediment) custom field, looked up once by name; None if the site has none."""
        if not self._flag_known:
            fields = self._send("GET", "/rest/api/3/field")
            self._flag_id = next((f["id"] for f in fields if (f.get("name") or "").lower() == "flagged"), None)
            self._flag_known = True
        return self._flag_id

    def get(self, key: str) -> dict:
        flag = self._flag_field()
        wanted = ISSUE_FIELDS + (f",{flag}" if flag else "")
        issue = self._send("GET", f"/rest/api/2/issue/{key}?fields={wanted}")
        f = issue["fields"]
        status = f.get("status") or {}
        return {"key": issue["key"], "summary": f.get("summary") or "", "description": f.get("description") or "",
                "issuetype": (f.get("issuetype") or {}).get("name", ""), "status": status.get("name", ""),
                "parent": (f.get("parent") or {}).get("key"),
                "category": CATEGORY.get((status.get("statusCategory") or {}).get("key", ""), ""),
                "flagged": bool(f.get(flag)) if flag else False}

    def children(self, key: str) -> List[dict]:
        keys: List[str] = []
        token = None
        while True:
            body = {"jql": f"parent = {key} ORDER BY key", "fields": ["summary"], "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = self._send("POST", "/rest/api/3/search/jql", body)
            keys += [issue["key"] for issue in page.get("issues", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        return [self.get(k) for k in keys]

    def project_statuses(self, key: str) -> List[dict]:
        """The workflows of a project: one entry per distinct set of statuses, with the issue types that share it.

        Each status is {"id", "name", "category"} with category todo, in_progress or done. Read only."""
        raw = self._send("GET", f"/rest/api/3/project/{urllib.parse.quote(key)}/statuses")
        groups: Dict[tuple, dict] = {}
        for kind in raw:
            statuses = [{"id": s["id"], "name": s["name"],
                         "category": CATEGORY.get((s.get("statusCategory") or {}).get("key", ""), "")}
                        for s in kind.get("statuses", [])]
            group = groups.setdefault(tuple(sorted(s["id"] for s in statuses)), {"types": [], "statuses": statuses})
            group["types"].append(kind["name"])
        return list(groups.values())

    def projects(self) -> List[dict]:
        """Every project the account can see, as {key, name, type, style}. Read only; follows the result pages."""
        found: List[dict] = []
        start = 0
        while True:
            page = self._send("GET", f"/rest/api/3/project/search?maxResults=100&startAt={start}")
            found += [{"key": p["key"], "name": p.get("name") or "", "type": p.get("projectTypeKey") or "",
                       "style": p.get("style") or ""} for p in page.get("values", [])]
            if page.get("isLast", True) or not page.get("values"):
                return found
            start += 100

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
                "status": status.get("name", ""), "status_id": status.get("id", ""), "category": _state(status),
                "parent": {"key": parent["key"], "summary": parent_fields.get("summary") or "",
                           "issuetype": (parent_fields.get("issuetype") or {}).get("name", "")} if parent else None,
                "assignee": {"id": owner["accountId"], "name": owner.get("displayName") or ""} if owner else None,
                "priority": (f.get("priority") or {}).get("name", ""), "duedate": f.get("duedate"),
                "created": _day(f.get("created")), "resolved": _day(f.get("resolutiondate")),
                "changed": _day(f.get("statuscategorychangedate")), "updated": _day(f.get("updated")),
                "labels": list(f.get("labels") or []), "components": [c["name"] for c in f.get("components") or [] if c.get("name")],
                "flagged": bool(f.get(flag)) if flag else False,
                "blocked_by": [b for b in (self._blocker(link, wanted) for link in f.get("issuelinks") or []) if b]}

    def search(self, jql: str, blocked_link: str = BLOCKED_LINK) -> List[dict]:
        """Every issue the JQL finds, in the shape the reports use. Read only; follows the result pages."""
        return self._search(jql, blocked_link, None)[0]

    def search_capped(self, jql: str, cap: int, blocked_link: str = BLOCKED_LINK) -> Tuple[List[dict], bool]:
        """At most `cap` issues and whether Jira had more. Read only; stops asking for pages once it has enough."""
        return self._search(jql, blocked_link, cap)

    def _search(self, jql: str, blocked_link: str, cap: Optional[int]) -> Tuple[List[dict], bool]:
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
            if cap is not None and len(found) >= cap:
                return found[:cap], bool(token) or len(found) > cap
            if not token:
                return found, False

    def group_total(self, name: str) -> int:
        """How many people a Jira group has; an unknown group is an HTTP 404 JiraError. Read only."""
        query = urllib.parse.urlencode({"groupname": name, "maxResults": 1})
        return int(self._send("GET", f"/rest/api/3/group/member?{query}").get("total", 0))

    def update(self, key: str, fields: dict) -> None:
        self._send("PUT", f"/rest/api/2/issue/{key}", {"fields": fields})
        self._journal({"action": "update", "key": key, "fields": fields})

    def transition_done(self, key: str) -> Optional[str]:
        """Apply the transition that lands in Jira's done category, preferring a plain "Done" over "Won't Do"."""
        options = self._send("GET", f"/rest/api/3/issue/{key}/transitions").get("transitions", [])
        done = [t for t in options if (((t.get("to") or {}).get("statusCategory") or {}).get("key")) == "done"]
        plain = ("done", "hecho", "listo", "finalizada", "finalizado", "cerrada", "cerrado")
        target = next((t for t in done if (t["to"].get("name") or "").lower() in plain), done[0] if done else None)
        if target is None:
            return None
        self._send("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": target["id"]}})
        self._journal({"action": "transition", "key": key, "to": target["to"].get("name")})
        return target["to"].get("name")

    def transition_start(self, key: str, avoid: List[str]) -> Optional[str]:
        """Apply a transition into Jira's in-progress category, skipping blocked and review statuses when it can."""
        options = self._send("GET", f"/rest/api/3/issue/{key}/transitions").get("transitions", [])
        going = [t for t in options
                 if (((t.get("to") or {}).get("statusCategory") or {}).get("key")) == "indeterminate"]
        skip = {name.lower() for name in avoid} | {"review", "revisión", "en revisión", "code review"}
        target = next((t for t in going if (t["to"].get("name") or "").lower() not in skip), going[0] if going else None)
        if target is None:
            return None
        self._send("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": target["id"]}})
        self._journal({"action": "transition", "key": key, "to": target["to"].get("name")})
        return target["to"].get("name")

    def transition(self, key: str, status: str) -> bool:
        options = self._send("GET", f"/rest/api/3/issue/{key}/transitions").get("transitions", [])
        wanted = status.strip().lower()
        match = next((t for t in options if (t.get("to") or {}).get("name", "").lower() == wanted), None)
        if match is None:
            return False
        self._send("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": match["id"]}})
        self._journal({"action": "transition", "key": key, "to": match["to"].get("name")})
        return True

    def transitions(self, key: str) -> List[dict]:
        """What the issue can do now: id, name, destination and the fields each transition requires. Read only."""
        raw = self._send("GET", f"/rest/api/3/issue/{key}/transitions?expand=transitions.fields").get("transitions", [])
        found = []
        for t in raw:
            to = t.get("to") or {}
            required = sorted(fid for fid, meta in (t.get("fields") or {}).items()
                              if meta.get("required") and not meta.get("hasDefaultValue"))
            found.append({"id": str(t["id"]), "name": t.get("name") or "",
                          "to": {"id": str(to.get("id", "")), "name": to.get("name", "")}, "required": required})
        return found

    def transition_by_id(self, key: str, transition_id: str) -> None:
        self._send("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": transition_id}})
        self._journal({"action": "transition", "key": key, "transition": transition_id})

    def add_comment(self, key: str, text: str) -> None:
        self._send("POST", f"/rest/api/2/issue/{key}/comment", {"body": text})
        self._journal({"action": "comment", "key": key})

    def snapshot(self, key: str) -> dict:
        """The status id and the owner now, which is all apply rereads before a write. Read only."""
        fields = self._send("GET", f"/rest/api/3/issue/{key}?fields=status,assignee")["fields"]
        status, owner = fields.get("status") or {}, fields.get("assignee")
        return {"status_id": str(status.get("id", "")), "status": status.get("name", ""),
                "assignee": {"id": owner["accountId"], "name": owner.get("displayName") or ""} if owner else None}
