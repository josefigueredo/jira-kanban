"""A small Jira Cloud client: v2 for issues (plain-text descriptions), v3 for search and transitions."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Callable, List, Optional

ISSUE_FIELDS = "summary,description,issuetype,status,parent"
CATEGORY = {"new": "todo", "indeterminate": "in_progress", "done": "done"}  # Jira's fixed status categories


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
        return self._send("GET", "/rest/api/3/myself")["accountId"]

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
