"""The epic spec an agent drafts from the conversation: validation against the conventions, and the ordered create plan."""
from __future__ import annotations

from typing import List

from . import description

ITEM_TYPES = ("story", "task")
SECTIONS = (("why", "the problem or need, as observed"), ("what", "the change, its scope and what stays out"),
            ("done_when", "how a person checks it without asking"))


def _story_ok(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return lowered.startswith("como ") and " quiero " in lowered and " para " in lowered


def _description_findings(ref: str, entry: dict) -> List[str]:
    """The description is built from templates/description.md; the spec gives its fields, never free text."""
    if "description" in entry:
        return [f"{ref}: description is built from why, what and done_when (templates/description.md); "
                f"split it into those fields"]
    return [f"{ref}: {name} is required ({hint})" for name, hint in SECTIONS if not str(entry.get(name) or "").strip()]


def validate(spec: dict, conv: dict) -> List[str]:
    findings: List[str] = []
    if not (spec.get("epic") or {}).get("summary", "").strip():
        findings.append("epic: summary is required")
    findings += _description_findings("epic", spec.get("epic") or {})
    items = spec.get("items") or []
    if not items:
        findings.append("items: at least one story or task")
    areas, priorities = conv["areas"], conv["priorities"]
    for i, item in enumerate(items):
        ref = f"items[{i}]"
        kind = item.get("type")
        if kind not in ITEM_TYPES:
            findings.append(f"{ref}: type must be story or task, not {kind!r}")
        if not (item.get("summary") or "").strip():
            findings.append(f"{ref}: summary is required")
        findings += _description_findings(ref, item)
        if kind == "story" and not _story_ok(item.get("user_story", "")):
            findings.append(f"{ref}: a story needs user_story (Como … quiero … para …); use a task if no one benefits")
        area = item.get("area")
        if area and area not in areas:
            findings.append(f"{ref}: area {area!r} is not one of {', '.join(areas)}")
        priority = item.get("priority")
        if priority and priority not in priorities:
            findings.append(f"{ref}: priority {priority!r} is not one of {', '.join(priorities)}")
        if "done" in item and not isinstance(item["done"], bool):
            findings.append(f"{ref}: done must be true or false")
        findings += _started_findings(ref, item)
        findings += _evidence_findings(ref, item, item.get("done") is True)
        for j, sub in enumerate(item.get("subtasks") or []):
            if not (sub.get("summary") or "").strip():
                findings.append(f"{ref}.subtasks[{j}]: summary is required")
            findings += _description_findings(f"{ref}.subtasks[{j}]", sub)
            if "done" in sub and not isinstance(sub["done"], bool):
                findings.append(f"{ref}.subtasks[{j}]: done must be true or false")
            findings += _started_findings(f"{ref}.subtasks[{j}]", sub)
            inherits = item.get("done") is True and "done" not in sub  # it shows through its parent's evidence
            if not inherits:
                findings += _evidence_findings(f"{ref}.subtasks[{j}]", sub, sub.get("done") is True)
    return findings


def _started_findings(ref: str, entry: dict) -> List[str]:
    if "started" not in entry:
        return []
    if not isinstance(entry["started"], bool):
        return [f"{ref}: started must be true or false"]
    return [f"{ref}: started and done exclude each other"] if entry["started"] and entry.get("done") else []


def _evidence_findings(ref: str, entry: dict, done: bool) -> List[str]:
    found = entry.get("evidence")
    if found is not None and not (isinstance(found, list) and all(isinstance(e, str) and e.strip() for e in found)):
        return [f"{ref}: evidence must be a list of commits, branches or URLs"]
    if done and not found:
        return [f"{ref}: done needs evidence: the commits, branch or URL that show it (\"evidence\": [...])"]
    return []


def title(area: str, summary: str) -> str:
    summary = summary.strip()
    if not area or summary.startswith("["):
        return summary
    return f"[{area}] {summary}"


def sections(item: dict) -> dict:
    """The fields templates/description.md takes, from one spec entry."""
    return {"intro": (item.get("user_story") or "").strip(),
            **{name: str(item.get(name) or "").strip() for name, _ in SECTIONS},
            "acceptance": "\n".join(f"- {ac.strip()}" for ac in item.get("acceptance") or [])}


def _description(item: dict) -> str:
    return description.render(sections(item))


def plan(spec: dict, conv: dict) -> List[dict]:
    """Create operations in dependency order: the epic, then each item followed by its subtasks."""
    default = conv.get("default_priority")
    epic = spec["epic"]
    ops = [{"ref": "epic", "kind": "epic", "parent": None, "summary": epic["summary"].strip(),
            "description": _description(epic), "sections": sections(epic), "priority": epic.get("priority") or default,
            "labels": list(epic.get("labels") or [])}]
    for i, item in enumerate(spec["items"]):
        ref = f"items[{i}]"
        item_done = bool(item.get("done"))
        ops.append({"ref": ref, "kind": item["type"], "parent": "epic", "summary": title(item.get("area"), item["summary"]),
                    "description": _description(item), "sections": sections(item),
                    "priority": item.get("priority") or default,
                    "labels": list(item.get("labels") or []), "done": item_done,
                    "started": bool(item.get("started")), "evidence": list(item.get("evidence") or [])})
        for j, sub in enumerate(item.get("subtasks") or []):
            ops.append({"ref": f"{ref}.subtasks[{j}]", "kind": "subtask", "parent": ref,
                        "summary": title(sub.get("area"), sub["summary"]), "description": _description(sub),
                        "sections": sections(sub),
                        "priority": sub.get("priority") or item.get("priority") or default,
                        "labels": list(sub.get("labels") or []), "done": bool(sub.get("done", item_done)),
                        "started": bool(sub.get("started")),
                        "evidence": list(sub.get("evidence") or (item.get("evidence") if "done" not in sub else None)
                                         or [])})  # a started parent does not start its subtasks
    ops[0]["done"] = all(op["done"] for op in ops[1:])  # the epic is complete only when everything under it is
    return ops
