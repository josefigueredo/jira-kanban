"""A card's description: built from templates/description.md and read back into its fields.

The template is the single source of the shape. Each labelled line (`Por qué: {{why}}`, `Criterios de aceptación:` over
`{{?acceptance}}`) maps a label to a field; the unlabelled `{{?intro}}` is whatever precedes the first label. Parsing
and checking derive the labels from the template, so changing the template changes all three at once.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from . import template

NAME = "description.md"
_UNFILLED = re.compile(r"^\{\{[?~]?[a-z_][a-z0-9_]*\}\}$")


def _layout() -> Tuple[List[Tuple[str, str, str]], str]:
    """(label, field, kind) per labelled section in template order, and the field that takes the unlabelled intro."""
    sections, intro = [], ""
    for para in re.split(r"\n{2,}", template.load(NAME).strip()):
        match = template.PLACEHOLDER.search(para)
        if not match:
            continue
        label = para[:match.start()].strip()
        if label:
            sections.append((label, match.group(2), match.group(1) or ""))
        else:
            intro = match.group(2)
    return sections, intro


def render(fields: Dict[str, str]) -> str:
    return template.render(template.load(NAME), fields).strip()


def parse(text: str) -> Dict[str, str]:
    sections, intro = _layout()
    by_label = {label: field for label, field, _ in sections}
    found: Dict[str, List[str]] = {}
    current = intro
    for line in (text or "").strip().splitlines():
        label = next((lb for lb in by_label if line.startswith(lb)), None)
        if label:
            current = by_label[label]
            found[current] = [line[len(label):].strip()]
        else:
            found.setdefault(current, []).append(line)
    return {field: "\n".join(lines).strip("\n").strip() for field, lines in found.items()
            if "\n".join(lines).strip()}


def blocks(text: str) -> List[Tuple[str, str]]:
    """(label, content) in template order for the sections present; the intro has an empty label."""
    sections, intro = _layout()
    parsed = parse(text)
    out = [("", parsed[intro])] if intro in parsed else []
    return out + [(label.rstrip(":"), parsed[field]) for label, field, _ in sections if field in parsed]


def check(text: str) -> List[str]:
    """What keeps a description from being a card a person can follow: a required section missing, empty or left as
    its placeholder. Braces inside prose are content, not placeholders."""
    sections, _ = _layout()
    parsed, present = parse(text), set()
    for line in (text or "").splitlines():
        present.update(label for label, _, _ in sections if line.startswith(label))
    problems = []
    for label, field, kind in sections:
        name = label.rstrip(":")
        value = parsed.get(field, "")
        if _UNFILLED.match(value):
            problems.append(f"not filled in: {name}")
        elif kind == "" and label not in present:
            problems.append(f"missing: {name}")
        elif kind == "" and not value:
            problems.append(f"empty: {name}")
    return problems
