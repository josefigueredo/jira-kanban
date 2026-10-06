"""Both directions between Jira and the local kanban.

create: spec -> Jira (parents first, assigned to the caller) -> pull.
pull:   Jira -> local folders, plus .sync.json, the baseline of what was last read.
push:   local -> Jira, only fields changed locally since the baseline; a field that also changed in Jira is a
        conflict and is never written. Folders named _new-* become new issues under their folder's parent.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from . import config, description, evidence, kanban, spec

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
FIELDS = ("summary", "status", "description")
DONE_STATUSES = ("done", "hecho", "listo", "finalizada", "finalizado", "cerrada", "cerrado")


class NeedsDecision(Exception):
    """Some issues are not complete locally: the user decides whether they are assigned to them."""


class PartialCreate(Exception):
    """Jira rejected an issue halfway through create. What was created stays, the local kanban mirrors it and the
    progress file lets the same command resume without creating anything twice."""


def assignment(ops: List[dict], assign_open: Optional[bool], enabled: bool = True) -> int:
    """Sets op["assignee"]: me-done (complete locally) or me-started (in progress), both assigned without asking;
    otherwise me, none, or ask. Returns asks."""
    asks = 0
    for op in ops:
        if not enabled:
            op["assignee"] = "none"
        elif op.get("done"):
            op["assignee"] = "me-done"
        elif op.get("started"):
            op["assignee"] = "me-started"
        elif assign_open is None:
            op["assignee"] = "ask"
            asks += 1
        else:
            op["assignee"] = "me" if assign_open else "none"
    return asks


def _decision_error(asks: int) -> NeedsDecision:
    return NeedsDecision(f"{asks} issue(s) are not complete locally: ask the user whether to assign them, then pass "
                         f"--assign-open or --no-assign-open (complete ones are assigned to the user without asking)")


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


def _progress_path(project: Path, epic_spec: dict, conv: dict) -> Path:
    digest = hashlib.sha256(json.dumps([conv["project"], epic_spec], sort_keys=True).encode()).hexdigest()[:16]
    return project / ".jira-kanban" / f".create-progress-{digest}.json"


def attach_evidence(ops: List[dict], repo: Path) -> None:
    """Resolve every op's evidence to links and fill the description's Evidencia section; any that does not resolve refuses
    the whole create, before a single write, in the dry run too."""
    findings = []
    for op in ops:
        if not op.get("evidence"):
            continue
        links, problems = evidence.resolve(op["evidence"], repo)
        findings += [f"{op['ref']}: {problem}" for problem in problems]
        op["sections"]["evidence"] = "\n".join(f"- {link}" for link in links)
        op["description"] = description.render(op["sections"])
    if findings:
        raise ValueError("\n".join(findings))


def create(jira, project: Path, epic_spec: dict, conv: dict, apply: bool, assign_open: Optional[bool] = None) -> dict:
    if not conv.get("project"):
        raise ValueError("no Jira project configured: ask the user which one, then pass --jira-project KEY or set "
                         "\"project\" in ./.jira-kanban/conventions.json (the skill never assumes one)")
    findings = spec.validate(epic_spec, conv)
    if findings:
        raise ValueError("\n".join(findings))
    ops = spec.plan(epic_spec, conv)
    attach_evidence(ops, project)
    asks = assignment(ops, assign_open, bool(conv.get("assign_to_me")))
    if not apply:
        return {"ops": ops}
    if asks:
        raise _decision_error(asks)
    me = jira.myself() if any(op["assignee"] != "none" for op in ops) else None
    # Each created key is saved before the next create: a failure halfway never loses them, and the same spec run
    # again skips what already exists instead of duplicating it.
    progress = _progress_path(project, epic_spec, conv)
    keys: Dict[str, str] = json.loads(progress.read_text(encoding="utf-8"))["keys"] if progress.is_file() else {}
    for op in ops:
        if op["ref"] in keys:
            continue
        parent = keys[op["parent"]] if op["parent"] else None
        who = me if op["assignee"] != "none" else None
        try:
            keys[op["ref"]] = jira.create(_fields(conv, who, op["kind"], op["summary"], op["description"], parent,
                                                  op.get("priority"), op.get("labels")))
        except Exception as exc:  # noqa: BLE001 — any rejection must keep what was already created
            if "epic" in keys:
                pull(jira, project, keys["epic"], conv)
            created = ", ".join(keys[o["ref"]] for o in ops if o["ref"] in keys) or "none"
            raise PartialCreate(f"Jira rejected \"{op['summary']}\" ({exc}). Already created: {created}. Fix the "
                                f"cause and run the same command again: it resumes without duplicating.") from exc
        progress.parent.mkdir(parents=True, exist_ok=True)
        progress.write_text(json.dumps({"keys": keys}, indent=2), encoding="utf-8")
    # Every issue exists from here on, so a rejected move never aborts: it is recorded, the rest still move, and the
    # kanban is written. A finished item goes to Done, children before parents and the epic last (spec.plan marks it
    # done only when everything under it is), so a sub-task blocking condition never
    # stops a story; a started item is already being worked on, so it begins in progress, not in the backlog.
    moves = [(op, "Done", jira.transition_done) for op in reversed(ops) if op.get("done")]
    blocked = conv.get("blocked_statuses") or []
    moves += [(op, "in progress", lambda key: jira.transition_start(key, blocked)) for op in ops if op.get("started")]
    errors = []
    for op, target, move in moves:
        key = keys[op["ref"]]
        try:
            reason = None if move(key) else "no transition into that category"
        except Exception as exc:  # noqa: BLE001 — one rejected move must not hide the others
            reason = str(exc) or type(exc).__name__
        if reason:
            errors.append({"key": key, "to": target, "reason": reason})
    pull(jira, project, keys["epic"], conv)
    progress.unlink(missing_ok=True)
    return {"ops": ops, "epic": keys["epic"], "keys": keys, "errors": errors}


def _record(issue: dict, kind: str, url: str, conv: dict) -> dict:
    blocked_names = {name.lower() for name in conv.get("blocked_statuses") or []}
    blocked = bool(issue.get("flagged")) or issue["status"].lower() in blocked_names
    return {"key": issue["key"], "kind": kind, "issuetype": issue["issuetype"], "status": issue["status"],
            "category": issue.get("category") or "", "blocked": "true" if blocked else "false",
            "parent": issue.get("parent") or "", "summary": issue["summary"],
            "description": (issue.get("description") or "").strip(), "url": url}


def pull(jira, project: Path, epic_key: str, conv: Optional[dict] = None) -> dict:
    conv = conv or config.load_conventions(project)
    epic = kanban.epic_dir(project, epic_key)
    written: Dict[Path, dict] = {}
    root = jira.get(epic_key)
    written[epic / "epic.md"] = _record(root, "epic", jira.browse_url(epic_key), conv)
    for item in jira.children(epic_key):
        kind = _kind_of(item["issuetype"], conv)
        path = kanban.item_file(epic, kind, item["key"])
        written[path] = _record(jira.get(item["key"]), kind, jira.browse_url(item["key"]), conv)
        for sub in jira.children(item["key"]):
            written[kanban.subtask_file(path.parent, sub["key"])] = _record(jira.get(sub["key"]), "subtask",
                                                                             jira.browse_url(sub["key"]), conv)
    keep = {path.parent for path in written}
    if epic.is_dir():  # an issue that left the epic leaves the kanban too; _new-* folders are never touched
        for folder in sorted(epic.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if folder.is_dir() and KEY_RE.match(folder.name) and folder not in keep:
                shutil.rmtree(folder, ignore_errors=True)
    baseline = {}
    for path, record in written.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kanban.render(record), encoding="utf-8")
        baseline[record["key"]] = {name: record[name] for name in FIELDS}
    state = {"synced": _now(), "issues": baseline}  # the one place that records when the epic was last read
    (epic / ".sync.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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


def push(jira, project: Path, epic_key: str, apply: bool, conv: Optional[dict] = None,
         assign_open: Optional[bool] = None) -> dict:
    conv = dict(conv or config.load_conventions(project))
    if not conv.get("project"):
        # New issues go to the epic's project; the key says which, so nothing is configured or assumed.
        conv["project"] = epic_key.split("-")[0]
    epic = kanban.epic_dir(project, epic_key)
    state = json.loads((epic / ".sync.json").read_text(encoding="utf-8"))
    baseline = state["issues"] if "issues" in state else state  # a flat baseline predates the sync time
    changes, conflicts, new, invalid = [], [], [], []
    depth: Dict[str, int] = {}
    for entry in _local(epic, epic_key):
        depth[entry["key"]] = {"subtask": 0, "epic": 2}.get(entry["kind"], 1)
        folder = entry["path"].parent.name
        if folder.startswith("_new") or not entry["key"]:
            if entry["parent"] and not KEY_RE.match(entry["parent"]):
                conflicts.append({"key": folder, "field": "parent", "reason": "create its parent first"})
                continue
            problems = description.check(entry["description"])
            if problems:  # a new card is created only once its description follows templates/description.md
                invalid += [{"key": folder, "field": "description", "problem": p} for p in problems]
                continue
            new.append({"path": entry["path"], "kind": entry["kind"], "parent": entry["parent"],
                        "summary": entry["summary"], "description": entry["description"],
                        "done": entry["category"] == "done" or entry["status"].strip().lower() in DONE_STATUSES})
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
            elif field == "description" and description.check(entry[field]):
                # only an edited description is checked: a card mirrored with free text can still move or be renamed
                invalid += [{"key": entry["key"], "field": field, "problem": p} for p in description.check(entry[field])]
            else:
                changes.append({"key": entry["key"], "field": field, "from": base[field], "to": entry[field]})
    asks = assignment(new, assign_open, bool(conv.get("assign_to_me")))
    result = {"changes": changes, "conflicts": conflicts, "new": new, "invalid": invalid, "errors": []}
    if not apply:
        return result
    if asks:
        raise _decision_error(asks)
    # Status moves go deepest first, so a parent closes after its sub-tasks; one rejected write never stops the rest.
    for change in sorted(changes, key=lambda c: depth.get(c["key"], 1) if c["field"] == "status" else -1):
        try:
            if change["field"] != "status":
                jira.update(change["key"], {change["field"]: change["to"]})
            elif not jira.transition(change["key"], change["to"]):
                result["errors"].append(f"{change['key']}: no transition to {change['to']!r}")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"{change['key']}: {change['field']} not written ({exc})")
    if new:
        me = jira.myself() if any(item["assignee"] != "none" for item in new) else None
        for item in new:
            who = me if item["assignee"] != "none" else None
            key = jira.create(_fields(conv, who, item["kind"], item["summary"], item["description"], item["parent"],
                                      conv.get("default_priority")))
            item["key"] = key
            shutil.rmtree(item["path"].parent, ignore_errors=True)
            if item["done"]:  # a card written as finished is created and then moved, like create does
                try:
                    moved = jira.transition_done(key)
                except Exception as exc:  # noqa: BLE001 — the issue exists: report the move, never lose the rest
                    moved, reason = None, str(exc)
                else:
                    reason = "no transition to Done"
                if not moved:
                    result["errors"].append(f"{key}: created, but {reason}")
    pull(jira, project, epic_key, conv)
    return result


GROUPS = ("blocked", "todo", "in_progress", "done")


def board(project: Path, epic_key: str, conv: Optional[dict] = None) -> dict:
    """Group the local kanban by Jira status category, blocked first; reads only local files, never Jira.

    A done issue stays done even if flagged; anything else flagged or in a blocked status is blocked.
    The epic is the frame, not a card. Issues with no category yet (new local folders) count as to do.
    """
    epic = kanban.epic_dir(project, epic_key)
    groups = {name: {"name": name, "count": 0, "statuses": {}} for name in GROUPS}
    total = 0
    for entry in _local(epic, epic_key):
        if entry["kind"] == "epic":
            continue
        total += 1
        category = entry["category"] or "todo"
        name = "blocked" if entry["blocked"] == "true" and category != "done" else category
        group = groups.get(name, groups["todo"])
        group["count"] += 1
        status = entry["status"] or "nuevo"
        group["statuses"][status] = group["statuses"].get(status, 0) + 1
    done = groups["done"]["count"]
    return {"epic": epic_key, "total": total, "done_pct": round(100 * done / total) if total else 0,
            "groups": [groups[name] for name in GROUPS]}
