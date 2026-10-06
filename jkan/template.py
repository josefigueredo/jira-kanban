"""Strict placeholder templates: the files in templates/ fix the shape of every card, Python only fills them.

`{{name}}` is required and must not be empty; `{{?name}}` is optional, and when its value is empty the whole paragraph
that holds it (the text between blank lines) is left out; `{{~name}}` may be empty and stays in place (a front matter
field such as an epic's parent). A value nobody asked for, or a placeholder nobody filled, is
an error: a typo never ships silently. Substitution is one pass, so a value that contains `{{…}}` stays as written.
Names ending in `_html` are fragments already built by the caller and skip the escape.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Callable, Dict, Optional

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
PLACEHOLDER = re.compile(r"\{\{([?~])?([a-z_][a-z0-9_]*)\}\}")


class TemplateError(ValueError):
    pass


def html_escape(text: str) -> str:
    return html.escape(text)


def load(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def placeholders(text: str) -> Dict[str, str]:
    """Each placeholder name and its kind: "" required, "?" optional paragraph, "~" may be empty in place."""
    return {m.group(2): m.group(1) or "" for m in PLACEHOLDER.finditer(text)}


def render(text: str, values: Dict[str, Optional[str]], escape: Optional[Callable[[str], str]] = None) -> str:
    wanted = placeholders(text)
    unknown = sorted(set(values) - set(wanted))
    missing = sorted(name for name, kind in wanted.items() if kind != "?" and name not in values)
    empty = sorted(name for name, kind in wanted.items()
                   if not kind and name in values and not str(values[name] or "").strip())
    problems = ([f"no placeholder for {', '.join(unknown)}"] if unknown else []) + \
               ([f"missing {', '.join(missing)}"] if missing else []) + \
               ([f"empty {', '.join(empty)}"] if empty else [])
    if problems:
        raise TemplateError("; ".join(problems))

    def blank(name: str) -> bool:
        return not str(values.get(name) or "").strip()

    kept = [para for para in re.split(r"\n{2,}", text)
            if not any(m.group(1) == "?" and blank(m.group(2)) for m in PLACEHOLDER.finditer(para))]

    def fill(match: re.Match) -> str:
        name = match.group(2)
        value = str(values.get(name) or "").strip("\n")
        return value if escape is None or name.endswith("_html") else escape(value)

    return PLACEHOLDER.sub(fill, "\n\n".join(kept))
