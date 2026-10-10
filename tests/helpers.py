from __future__ import annotations

import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def config_dir() -> Path:
    """Point jk at an empty config directory, so no test reads or writes the real ~/.config/jk."""
    path = Path(tempfile.mkdtemp(prefix="jk-config-"))
    os.environ["JK_CONFIG_DIR"] = str(path)
    return path


config_dir()  # every test run starts isolated, even the tests that never ask for a profile


def state_dir() -> Path:
    """Point jk at an empty state directory, so no test reads or writes the real ~/.local/state/jk."""
    path = Path(tempfile.mkdtemp(prefix="jk-state-"))
    os.environ["JK_STATE_DIR"] = str(path)
    return path


state_dir()  # every test run starts isolated

CONVENTIONS = {
    "project": "PLATE",
    "issue_types": {"epic": "Epic", "story": "Story (migrated)", "task": "Tarea", "subtask": "Subtarea"},
    "areas": ["FE", "BE", "BO", "QA", "DEVOPS", "INFRA", "BFF", "AI"],
    "priorities": ["Highest", "High", "Medium", "Low", "Lowest"],
    "default_priority": "Medium",
    "assign_to_me": True,
    "blocked_statuses": ["Blocked"],
}

def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


# What Jira's assignable-user search returns for PLATE, reduced to what jk uses.
PEOPLE = [
    {"id": "acc-matias", "name": "Matías Andrés Fernandez", "email": "matias.fernandez@example.com"},
    {"id": "acc-martin-d", "name": "Martin Daniel Fernandez", "email": "martin.fernandez@example.com"},
    {"id": "acc-martin-l", "name": "Martin Fernandez Lopez", "email": "martin.lopez@example.com"},
    {"id": "acc-maria", "name": "María Celeste Fernández", "email": "maria.fernandez@example.com"},
    {"id": "acc-ana", "name": "Ana Gómez", "email": "ana.gomez@example.com"},
]

STATUS_CATEGORY = {"Backlog": "todo", "Selected for Development": "todo", "PROCESANDO": "in_progress",
                   "Review": "in_progress", "Blocked": "in_progress", "Done": "done"}


def make_project() -> Path:
    return Path(tempfile.mkdtemp(prefix="jk-test-"))


def approve(n, summary, command):
    """A confirm() for tests of the legacy --apply: the person approved. Real runs go through guard.confirm."""
    return None


class FailingJira(Exception):
    pass


class FakeJira:
    """In-memory Jira: issues by key, a sequence for new keys, and a log of every write."""

    def __init__(self, project: str = "PLATE", start: int = 600, fail_on_create: Optional[int] = None,
                 refuse_moves: Optional[Dict[str, str]] = None, users: Optional[List[dict]] = None):
        self.project = project
        self.users = [dict(u) for u in (PEOPLE if users is None else users)]
        self.searches: List[str] = []
        self.search_projects: List[Optional[str]] = []
        self.refuse_moves = refuse_moves or {}  # key -> "raise" (HTTP error) or "none" (no transition to that category)
        self.fail_on_create = fail_on_create  # the Nth create (1-based) raises, like a rejected issue
        self.seq = start
        self.issues: Dict[str, dict] = {}
        self.writes: List[tuple] = []
        self.search_answer = lambda jql: []  # tests replace it: jql -> list of normalized issues
        self.jqls: List[str] = []
        self.status_groups: Dict[str, List[dict]] = {}  # project key -> what Jira.project_statuses returns
        self.project_list: List[dict] = []  # what Jira.projects returns
        self.groups: Dict[str, int] = {"team": 7}  # Jira group -> members
        self.board: Dict[str, dict] = {}  # key -> {"status_id", "status", "assignee"}: what snapshot() sees
        self.workflow: Dict[str, List[dict]] = {}  # status id -> the transitions that leave it
        self.fail_writes: set = set()  # keys whose writes raise, like a Jira that rejects them

    def browse_url(self, key: str) -> str:
        return f"https://example.atlassian.net/browse/{key}"

    def myself(self) -> str:
        return "acc-me"

    def create(self, fields: dict) -> str:
        creates = sum(1 for w in self.writes if w[0] == "create") + 1
        if self.fail_on_create is not None and creates == self.fail_on_create:
            raise FailingJira(f"HTTP 400 on create #{creates}")
        key = f"{self.project}-{self.seq}"
        self.seq += 1
        parent = (fields.get("parent") or {}).get("key")
        self.issues[key] = {"key": key, "summary": fields["summary"], "description": fields.get("description", ""),
                            "issuetype": fields["issuetype"]["name"], "status": "Backlog", "parent": parent,
                            "priority": (fields.get("priority") or {}).get("name"), "labels": fields.get("labels", []),
                            "assignee": (fields.get("assignee") or {}).get("accountId"),
                            "category": "todo", "flagged": False}
        self.writes.append(("create", key, fields))
        return key

    def search_users(self, query: str, project: Optional[str] = None, limit: int = 100) -> List[dict]:
        """Like Jira: a user matches when the query is a prefix of one word of the name, or of the email. No fuzziness."""
        self.searches.append(query)
        self.search_projects.append(project)
        q = _fold(query).strip()
        found = []
        for user in self.users:
            words = _fold(user["name"]).split() + [_fold(user["email"])]
            if q and (any(w.startswith(q) for w in words) or _fold(user["name"]).startswith(q)):
                found.append(dict(user))
        return found[:limit]

    def user(self, account_id: str) -> Optional[dict]:
        return next((dict(u) for u in self.users if u["id"] == account_id), None)

    def assign(self, key: str, account_id: Optional[str]) -> None:
        if key in self.fail_writes:
            raise FailingJira(f"HTTP 400 on assign of {key}")
        self.issues[key]["assignee"] = account_id
        if key in self.board:
            owner = None if account_id is None else {"id": account_id, "name": (self.user(account_id) or {}).get("name", account_id)}
            self.board[key]["assignee"] = owner
        self.writes.append(("assign", key, account_id))

    def get(self, key: str) -> dict:
        return dict(self.issues[key])

    def children(self, key: str) -> List[dict]:
        return [dict(i) for i in self.issues.values() if i["parent"] == key]

    def search(self, jql: str, blocked_link: str = "is blocked by") -> List[dict]:
        self.jqls.append(jql)
        return [dict(i) for i in self.search_answer(jql)]

    def project_statuses(self, key: str) -> List[dict]:
        from jkan.jira import JiraError
        if key not in self.status_groups:
            raise JiraError(f"GET /rest/api/3/project/{key}/statuses: HTTP 404")
        return [dict(g, statuses=[dict(s) for s in g["statuses"]]) for g in self.status_groups[key]]

    def projects(self) -> List[dict]:
        return [dict(p) for p in self.project_list]

    def search_capped(self, jql: str, cap: int, blocked_link: str = "is blocked by"):
        found = self.search(jql, blocked_link)
        return found[:cap], len(found) > cap

    def group_total(self, name: str) -> int:
        from jkan.jira import JiraError
        if name not in self.groups:
            raise JiraError(f"GET /rest/api/3/group/member: HTTP 404 no group {name}")
        return self.groups[name]

    def update(self, key: str, fields: dict) -> None:
        for name in ("summary", "description"):
            if name in fields:
                self.issues[key][name] = fields[name]
        self.writes.append(("update", key, fields))

    def _refused(self, key: str) -> bool:
        how = self.refuse_moves.get(key)
        if how == "raise":
            raise FailingJira(f"HTTP 400 on transition of {key}")
        return how == "none"

    def transition_done(self, key: str) -> Optional[str]:
        if self._refused(key):
            return None
        self.issues[key]["status"] = "Done"
        self.issues[key]["category"] = "done"
        self.writes.append(("transition", key, "Done"))
        return "Done"

    def transition_start(self, key: str, avoid: List[str]) -> Optional[str]:
        if self._refused(key):
            return None
        self.issues[key]["status"] = "PROCESANDO"
        self.issues[key]["category"] = "in_progress"
        self.writes.append(("transition", key, "PROCESANDO"))
        return "PROCESANDO"

    def transition(self, key: str, status: str) -> bool:
        if self._refused(key):
            return False
        open_children = [i for i in self.issues.values() if i["parent"] == key and i["category"] != "done"]
        if STATUS_CATEGORY.get(status) == "done" and open_children:  # like a workflow that guards on sub-tasks
            raise FailingJira(f"HTTP 400: {key} has open sub-tasks")
        self.issues[key]["status"] = status
        self.issues[key]["category"] = STATUS_CATEGORY.get(status, "in_progress")
        self.writes.append(("transition", key, status))
        return True

    # ---- plan / apply -------------------------------------------------------------------------------------------
    def put(self, key: str, status_id: str, status: str, assignee: Optional[dict] = None) -> str:
        """An issue as snapshot() sees it; `assignee` is {"id", "name"} or None."""
        self.board[key] = {"status_id": status_id, "status": status, "assignee": dict(assignee) if assignee else None}
        self.issues.setdefault(key, {"key": key, "assignee": None})
        return key

    def snapshot(self, key: str) -> dict:
        shot = self.board[key]
        return {"status_id": shot["status_id"], "status": shot["status"],
                "assignee": dict(shot["assignee"]) if shot["assignee"] else None}

    def transitions(self, key: str) -> List[dict]:
        return [dict(t, to=dict(t["to"]), required=list(t.get("required", [])))
                for t in self.workflow.get(self.board[key]["status_id"], [])]

    def transition_by_id(self, key: str, transition_id: str) -> None:
        if key in self.fail_writes:
            raise FailingJira(f"HTTP 400 on transition of {key}")
        chosen = next((t for t in self.workflow.get(self.board[key]["status_id"], []) if t["id"] == transition_id), None)
        if chosen is None:
            raise FailingJira(f"HTTP 400: transition {transition_id} is not available for {key}")
        self.board[key].update(status_id=chosen["to"]["id"], status=chosen["to"]["name"])
        self.writes.append(("transition_id", key, transition_id))

    def add_comment(self, key: str, text: str) -> None:
        if key in self.fail_writes:
            raise FailingJira(f"HTTP 400 on comment of {key}")
        self.writes.append(("comment", key, text))


def epic_with_children(jira: FakeJira) -> str:
    """PLATE-600 epic, one story with one subtask, one task without subtasks."""
    epic = jira.create({"summary": "Kanban local", "description": "Objetivo", "issuetype": {"name": "Epic"}})
    story = jira.create({"summary": "[FE] Ver el tablero", "description": "Como analista quiero ver el tablero para decidir",
                         "issuetype": {"name": "Story (migrated)"}, "parent": {"key": epic}})
    jira.create({"summary": "Armar la vista", "description": "", "issuetype": {"name": "Subtarea"},
                 "parent": {"key": story}})
    jira.create({"summary": "[DEVOPS] Pipeline", "description": "CI", "issuetype": {"name": "Tarea"},
                 "parent": {"key": epic}})
    jira.writes.clear()
    return epic


def issue(key: str, **over) -> dict:
    """A normalized issue as Jira.search returns it, for the report tests."""
    base = {"key": key, "summary": f"Summary of {key}", "issuetype": "Tarea", "status": "Backlog", "category": "todo",
            "parent": None, "assignee": {"id": "acc-me", "name": "Yo"}, "priority": "Medium", "duedate": None,
            "created": "2026-09-01", "resolved": None, "changed": "2026-09-01", "updated": "2026-09-01",
            "flagged": False, "blocked_by": []}
    base.update(over)
    return base


def described(spec: dict) -> dict:
    """Give every issue of a spec its why / what / done_when, for tests about something else: jk refuses issues without."""
    entries = [spec["epic"]] + spec["items"] + [sub for item in spec["items"] for sub in item.get("subtasks") or []]
    for entry in entries:
        entry.setdefault("why", f"Hace falta «{entry.get('summary', '')}».")
        entry.setdefault("what", "Lo que dice el título.")
        entry.setdefault("done_when", "Se ve hecho.")
    return spec
