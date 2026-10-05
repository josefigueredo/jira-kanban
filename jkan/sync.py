"""Both directions between Jira and the local kanban.

create: spec -> Jira (parents first, assigned to the caller) -> pull.
pull:   Jira -> local folders, plus .sync.json, the baseline of what was last read.
push:   local -> Jira, only fields changed locally since the baseline; a field that also changed in Jira is a
        conflict and is never written. Folders named _new-* become new issues under their folder's parent.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from . import config, kanban, spec

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
FIELDS = ("summary", "status", "description")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kind_of(issuetype: str, conv: dict) -> str:
    by_name = {name.lower(): kind for kind, name in conv["issue_types"].items()}
    return by_name.get((issuetype or "").lower(), "task")  # another level-0 type (a bug) sits with the tasks


def _fields(conv: dict, me: Optional[str], kind: str, summary: str, description: str, parent: Optional[str],
            priority: Optional[str] = None, labels: Optional[List[str]] = None) -> dict:
    fields = {"project": {"key": conv["project"]}, "issuetype": {"name": conv["issue_types"][kind]},
              "summary": summary, "description": description}
    if parent:
        fields["parent"] = {"key": parent}
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = labels
    if me:
        fields["assignee"] = {"accountId": me}
    return fields


def create(jira, project: Path, epic_spec: dict, conv: dict, apply: bool) -> dict:
    findings = spec.validate(epic_spec, conv)
    if findings:
        raise ValueError("\n".join(findings))
    ops = spec.plan(epic_spec, conv)
    if not apply:
        return {"ops": ops}
    me = jira.myself() if conv.get("assign_to_me") else None
    keys: Dict[str, str] = {}
    for op in ops:
        parent = keys[op["parent"]] if op["parent"] else None
        keys[op["ref"]] = jira.create(_fields(conv, me, op["kind"], op["summary"], op["description"], parent,
                                              op.get("priority"), op.get("labels")))
    pull(jira, project, keys["epic"], conv)
    return {"ops": ops, "epic": keys["epic"], "keys": keys}


def _record(issue: dict, kind: str, url: str) -> dict:
    return {"key": issue["key"], "kind": kind, "issuetype": issue["issuetype"], "status": issue["status"],
            "parent": issue.get("parent") or "", "summary": issue["summary"],
            "description": (issue.get("description") or "").strip(), "url": url}


def pull(jira, project: Path, epic_key: str, conv: Optional[dict] = None) -> dict:
    conv = conv or config.load_conventions(project)
    epic = kanban.epic_dir(project, epic_key)
    synced = _now()
    written: Dict[Path, dict] = {}
    root = jira.get(epic_key)
    written[epic / "epic.md"] = _record(root, "epic", jira.browse_url(epic_key))
    for item in jira.children(epic_key):
        kind = _kind_of(item["issuetype"], conv)
        path = kanban.item_file(epic, kind, item["key"])
        written[path] = _record(jira.get(item["key"]), kind, jira.browse_url(item["key"]))
        for sub in jira.children(item["key"]):
            written[kanban.subtask_file(path.parent, sub["key"])] = _record(jira.get(sub["key"]), "subtask",
                                                                             jira.browse_url(sub["key"]))
    keep = {path.parent for path in written}
    if epic.is_dir():  # an issue that left the epic leaves the kanban too; _new-* folders are never touched
        for folder in sorted(epic.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if folder.is_dir() and KEY_RE.match(folder.name) and folder not in keep:
                shutil.rmtree(folder, ignore_errors=True)
    baseline = {}
    for path, record in written.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kanban.render(record, synced), encoding="utf-8")
        baseline[record["key"]] = {name: record[name] for name in FIELDS}
    (epic / ".sync.json").write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"epic": epic_key, "issues": len(written), "dir": str(epic)}


def _local(epic: Path, epic_key: str) -> List[dict]:
    """Every local issue file with the parent and kind its location implies."""
    found = []
    if (epic / "epic.md").is_file():
        found.append({"path": epic / "epic.md", "kind": "epic", "parent": None})
    for kind, folder in kanban.FOLDER.items():
        for item in sorted((epic / folder).glob(f"*/{kind}.md")):
            found.append({"path": item, "kind": kind, "parent": epic_key})
            for sub in sorted((item.parent / "subtasks").glob("*/subtask.md")):
                found.append({"path": sub, "kind": "subtask", "parent": item.parent.name})
    parsed = []
    for entry in found:  # the folder decides kind and parent; the front matter never moves an issue
        parsed.append(dict(kanban.parse(entry["path"].read_text(encoding="utf-8")), **entry))
    return parsed


def push(jira, project: Path, epic_key: str, apply: bool, conv: Optional[dict] = None) -> dict:
    conv = conv or config.load_conventions(project)
    epic = kanban.epic_dir(project, epic_key)
    baseline = json.loads((epic / ".sync.json").read_text(encoding="utf-8"))
    changes, conflicts, new = [], [], []
    for entry in _local(epic, epic_key):
        folder = entry["path"].parent.name
        if folder.startswith("_new") or not entry["key"]:
            if entry["parent"] and not KEY_RE.match(entry["parent"]):
                conflicts.append({"key": folder, "field": "parent", "reason": "create its parent first"})
                continue
            new.append({"path": entry["path"], "kind": entry["kind"], "parent": entry["parent"],
                        "summary": entry["summary"], "description": entry["description"]})
            continue
        base = baseline.get(entry["key"])
        if base is None:
            continue
        remote = None
        for field in FIELDS:
            if entry[field] == base[field]:
                continue
            remote = remote or jira.get(entry["key"])
            if (remote.get(field) or "").strip() != base[field]:
                conflicts.append({"key": entry["key"], "field": field, "local": entry[field], "jira": remote.get(field)})
            else:
                changes.append({"key": entry["key"], "field": field, "from": base[field], "to": entry[field]})
    result = {"changes": changes, "conflicts": conflicts, "new": new, "errors": []}
    if not apply:
        return result
    for change in changes:
        if change["field"] == "status":
            if not jira.transition(change["key"], change["to"]):
                result["errors"].append(f"{change['key']}: no transition to {change['to']!r}")
        else:
            jira.update(change["key"], {change["field"]: change["to"]})
    if new:
        me = jira.myself() if conv.get("assign_to_me") else None
        for item in new:
            key = jira.create(_fields(conv, me, item["kind"], item["summary"], item["description"], item["parent"],
                                      conv.get("default_priority")))
            item["key"] = key
            shutil.rmtree(item["path"].parent, ignore_errors=True)
    pull(jira, project, epic_key, conv)
    return result
