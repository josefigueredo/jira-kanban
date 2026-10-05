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
}


def make_project() -> Path:
    return Path(tempfile.mkdtemp(prefix="jk-test-"))


class FakeJira:
    """In-memory Jira: issues by key, a sequence for new keys, and a log of every write."""

    def __init__(self, project: str = "PLATE", start: int = 600):
        self.project = project
        self.seq = start
        self.issues: Dict[str, dict] = {}
        self.writes: List[tuple] = []

    def browse_url(self, key: str) -> str:
        return f"https://example.atlassian.net/browse/{key}"

    def myself(self) -> str:
        return "acc-me"

    def create(self, fields: dict) -> str:
        key = f"{self.project}-{self.seq}"
        self.seq += 1
        parent = (fields.get("parent") or {}).get("key")
        self.issues[key] = {"key": key, "summary": fields["summary"], "description": fields.get("description", ""),
                            "issuetype": fields["issuetype"]["name"], "status": "Backlog", "parent": parent,
                            "priority": (fields.get("priority") or {}).get("name"), "labels": fields.get("labels", []),
                            "assignee": (fields.get("assignee") or {}).get("accountId")}
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

    def transition(self, key: str, status: str) -> bool:
        self.issues[key]["status"] = status
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
