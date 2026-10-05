from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONVENTIONS = {
    "project": "PLATE",
    "issue_types": {"epic": "Epic", "story": "Story (migrated)", "task": "Tarea", "subtask": "Subtarea"},
    "areas": ["FE", "BE", "BO", "QA", "DEVOPS", "INFRA", "BFF", "AI"],
    "priorities": ["Highest", "High", "Medium", "Low", "Lowest"],
    "default_priority": "Medium",
    "assign_to_me": True,
    "blocked_statuses": ["Blocked"],
}

STATUS_CATEGORY = {"Backlog": "todo", "Selected for Development": "todo", "PROCESANDO": "in_progress",
                   "Review": "in_progress", "Blocked": "in_progress", "Done": "done"}


def make_project() -> Path:
    return Path(tempfile.mkdtemp(prefix="jk-test-"))


class FailingJira(Exception):
    pass


class FakeJira:
    """In-memory Jira: issues by key, a sequence for new keys, and a log of every write."""

    def __init__(self, project: str = "PLATE", start: int = 600, fail_on_create: Optional[int] = None):
        self.project = project
        self.fail_on_create = fail_on_create  # the Nth create (1-based) raises, like a rejected issue
        self.seq = start
        self.issues: Dict[str, dict] = {}
        self.writes: List[tuple] = []

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

    def get(self, key: str) -> dict:
        return dict(self.issues[key])

    def children(self, key: str) -> List[dict]:
        return [dict(i) for i in self.issues.values() if i["parent"] == key]

    def update(self, key: str, fields: dict) -> None:
        for name in ("summary", "description"):
            if name in fields:
                self.issues[key][name] = fields[name]
        self.writes.append(("update", key, fields))

    def transition_done(self, key: str) -> Optional[str]:
        self.issues[key]["status"] = "Done"
        self.issues[key]["category"] = "done"
        self.writes.append(("transition", key, "Done"))
        return "Done"

    def transition_start(self, key: str, avoid: List[str]) -> Optional[str]:
        self.issues[key]["status"] = "PROCESANDO"
        self.issues[key]["category"] = "in_progress"
        self.writes.append(("transition", key, "PROCESANDO"))
        return "PROCESANDO"

    def transition(self, key: str, status: str) -> bool:
        self.issues[key]["status"] = status
        self.issues[key]["category"] = STATUS_CATEGORY.get(status, "in_progress")
        self.writes.append(("transition", key, status))
        return True


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
