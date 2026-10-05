"""The epic spec an agent drafts from the conversation: validation against the conventions, and the ordered create plan."""
from __future__ import annotations

from typing import List

ITEM_TYPES = ("story", "task")


def _story_ok(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return lowered.startswith("como ") and " quiero " in lowered and " para " in lowered


def validate(spec: dict, conv: dict) -> List[str]:
    findings: List[str] = []
    if not (spec.get("epic") or {}).get("summary", "").strip():
        findings.append("epic: summary is required")
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
        for j, sub in enumerate(item.get("subtasks") or []):
            if not (sub.get("summary") or "").strip():
                findings.append(f"{ref}.subtasks[{j}]: summary is required")
            if "done" in sub and not isinstance(sub["done"], bool):
                findings.append(f"{ref}.subtasks[{j}]: done must be true or false")
    return findings


def title(area: str, summary: str) -> str:
    summary = summary.strip()
    if not area or summary.startswith("["):
        return summary
    return f"[{area}] {summary}"


def _description(item: dict) -> str:
    parts = []
    if item.get("user_story"):
        parts.append(item["user_story"].strip())
    if item.get("description"):
        parts.append(item["description"].strip())
    acceptance = item.get("acceptance") or []
    if acceptance:
        parts.append("Criterios de aceptación:\n" + "\n".join(f"- {ac.strip()}" for ac in acceptance))
    return "\n\n".join(parts)


def plan(spec: dict, conv: dict) -> List[dict]:
    """Create operations in dependency order: the epic, then each item followed by its subtasks."""
    default = conv.get("default_priority")
    epic = spec["epic"]
    ops = [{"ref": "epic", "kind": "epic", "parent": None, "summary": epic["summary"].strip(),
            "description": (epic.get("description") or "").strip(), "priority": epic.get("priority") or default,
            "labels": list(epic.get("labels") or [])}]
    for i, item in enumerate(spec["items"]):
        ref = f"items[{i}]"
        item_done = bool(item.get("done"))
        ops.append({"ref": ref, "kind": item["type"], "parent": "epic", "summary": title(item.get("area"), item["summary"]),
                    "description": _description(item), "priority": item.get("priority") or default,
                    "labels": list(item.get("labels") or []), "done": item_done})
        for j, sub in enumerate(item.get("subtasks") or []):
            ops.append({"ref": f"{ref}.subtasks[{j}]", "kind": "subtask", "parent": ref,
                        "summary": title(sub.get("area"), sub["summary"]), "description": _description(sub),
                        "priority": sub.get("priority") or item.get("priority") or default,
                        "labels": list(sub.get("labels") or []), "done": bool(sub.get("done", item_done))})
    ops[0]["done"] = all(op["done"] for op in ops[1:])  # the epic is complete only when everything under it is
    return ops
