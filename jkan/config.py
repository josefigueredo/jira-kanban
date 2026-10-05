"""Credentials (same sources and order as WayOfWork) and the Jira conventions this skill applies."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

SKILL_DIR = Path(__file__).resolve().parent.parent
KEYS = {"base_url": ("IC_JIRA_BASE_URL", "JIRA_BASE_URL"),
        "email": ("IC_JIRA_USER_EMAIL", "JIRA_EMAIL"),
        "token": ("IC_JIRA_API_TOKEN", "JIRA_API_TOKEN")}


def _read_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        values[name] = value.strip().strip("'\"")
    return values


def credentials(project: Path, environ: Optional[Mapping[str, str]] = None) -> Optional[Tuple[str, str, str]]:
    """Environment first, then ./.env.local, then ./.spec-kit/.env (as WayOfWork resolves them)."""
    layers = [dict(environ if environ is not None else os.environ), _read_dotenv(project / ".env.local"),
              _read_dotenv(project / ".spec-kit" / ".env")]
    found = []
    for names in KEYS.values():
        value = next((layer[n] for layer in layers for n in names if layer.get(n)), None)
        found.append(value)
    return tuple(found) if all(found) else None  # type: ignore[return-value]


def load_conventions(project: Optional[Path] = None) -> dict:
    """The skill's conventions.json, overridden key by key by the project's ./.jira-kanban/conventions.json."""
    conv = json.loads((SKILL_DIR / "conventions.json").read_text(encoding="utf-8"))
    override = (project / ".jira-kanban" / "conventions.json") if project else None
    if override and override.is_file():
        conv.update(json.loads(override.read_text(encoding="utf-8")))
    return conv
