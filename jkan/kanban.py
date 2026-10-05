"""The local kanban: one folder per Jira issue under ./.jira-kanban/<EPIC>/, following Jira's levels.

<EPIC>/epic.md · stories/<KEY>/story.md · tasks/<KEY>/task.md · <story or task>/subtasks/<KEY>/subtask.md
Stories and tasks are siblings under the epic, as in Jira; subtasks hang from either.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

ROOT = ".jira-kanban"
FRONT = ("key", "kind", "issuetype", "status", "parent", "url", "synced")
FOLDER = {"story": "stories", "task": "tasks"}


def epic_dir(project: Path, key: str) -> Path:
    return project / ROOT / key


def item_file(epic: Path, kind: str, key: str) -> Path:
    return epic / FOLDER[kind] / key / f"{kind}.md"


def subtask_file(parent_dir: Path, key: str) -> Path:
    return parent_dir / "subtasks" / key / "subtask.md"


def render(issue: dict, synced: str) -> str:
    values = dict(issue, synced=synced)
    lines = ["---"] + [f"{name}: {values.get(name) or ''}" for name in FRONT] + ["---", "", f"# {issue['summary']}", ""]
    description = (issue.get("description") or "").strip()
    if description:
        lines += [description, ""]
    return "\n".join(lines)


def parse(text: str) -> Dict[str, str]:
    """Front matter fields plus summary (the heading) and description (everything after it)."""
    result = {name: "" for name in FRONT}
    lines = text.splitlines()
    body = lines
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            for line in lines[1:end]:
                name, sep, value = line.partition(":")
                if sep and name.strip() in result:
                    result[name.strip()] = value.strip()
            body = lines[end + 1:]
    summary, rest = "", []
    for i, line in enumerate(body):
        if line.startswith("# "):
            summary, rest = line[2:].strip(), body[i + 1:]
            break
    result["summary"] = summary
    result["description"] = "\n".join(rest).strip()
    return result
