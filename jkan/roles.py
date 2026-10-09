"""What a status means to a board: six roles, a proposal for each status, and the rules that turn issues into roles."""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

ROLES = ("todo", "active", "blocked", "waiting", "delivered", "dropped")
CLOSED = ("delivered", "dropped")
IN_FLIGHT = ("active", "blocked", "waiting")
LEGACY = {"todo": "todo", "in_progress": "active", "done": "delivered"}  # Jira category -> role, for a project without profile

DICTIONARY = {
    "delivered": ("done", "finalizado", "finalizada", "completado", "completada", "completo", "completa", "resuelto",
                  "resuelta", "cerrado", "cerrada", "closed", "resolved", "listo", "lista", "released"),
    "dropped": ("cancelado", "cancelada", "cancelled", "canceled", "rechazado", "rechazada", "descartado", "descartada",
                "discarded", "no aplica", "not approved"),
    "blocked": ("blocked", "bloqueado", "bloqueada"),
}
BY_NAME = {name: role for role, names in DICTIONARY.items() for name in names}
SINGLE_WORDS = {name for name in BY_NAME if " " not in name}
EXPECTED_CATEGORY = {"delivered": "done", "dropped": "done", "blocked": "in_progress"}
HINTS = re.compile(r"\b(hold|espera\w*|waiting|paus\w*|bloque\w*|pend\w*|pending|approval|aprobaci\w*)\b")


def normalize(text: str) -> str:
    """Lower case, no accents, no punctuation, single spaces: «Pend. Finalización» -> «pend finalizacion»."""
    folded = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def _proposal(role: Optional[str], confidence: str, why: str, suggest: Optional[str] = None,
              mismatch: bool = False) -> dict:
    return {"role": role, "confidence": confidence, "why": why, "suggest": suggest or role, "mismatch": mismatch}


def propose(status: dict) -> dict:
    """The role a status probably plays. `alta` means the name and Jira's category agree; `decidir` leaves the role
    empty for a person to set, and `suggest` carries the guess. `mismatch` marks a name Jira files in the wrong
    category. status: {"id", "name", "category"} with category todo, in_progress or done."""
    name, category = normalize(status["name"]), status["category"]
    exact = BY_NAME.get(name)
    if exact:
        if category == EXPECTED_CATEGORY[exact]:
            return _proposal(exact, "alta", "nombre conocido y categoría coherente")
        return _proposal(None, "decidir", f"el nombre sugiere {exact} pero Jira lo tiene en la categoría {category}",
                         exact, mismatch=True)
    known = sorted(set(name.split()) & SINGLE_WORDS)
    if known:
        return _proposal(None, "decidir", f"trae «{known[0]}» con más palabras: puede no significar lo mismo",
                         BY_NAME[known[0]])
    if category == "in_progress" and HINTS.search(name):
        return _proposal(None, "decidir", "parece una espera o un bloqueo")
    if category == "done":
        return _proposal(None, "decidir", "categoría done con un nombre que no conozco: ¿entregado o descartado?")
    if category == "todo":
        return _proposal("todo", "alta", "categoría por hacer")
    if category == "in_progress":
        return _proposal("active", "alta", "categoría en curso")
    return _proposal(None, "decidir", f"categoría desconocida {category!r}")


def project_of(key: str) -> str:
    return key.rpartition("-")[0]


def role_of(issue: dict) -> Optional[str]:
    """The role annotate() gave the issue; an issue nobody annotated falls back to Jira's category."""
    return issue["role"] if "role" in issue else LEGACY.get(issue.get("category", ""))


def source_of(issue: dict) -> str:
    return issue.get("role_source", "category")


def annotate(issues: List[dict], profiles: Dict[str, dict]) -> List[dict]:
    """Set issue['role'] (None while the status has no role) and issue['role_source'] ('profile' or 'category')."""
    for issue in issues:
        profile = profiles.get(project_of(issue["key"]))
        if profile is None:
            issue["role"], issue["role_source"] = LEGACY.get(issue.get("category", "")), "category"
            continue
        by_id = {s["id"]: s["role"] for s in profile["statuses"]}
        issue["role"], issue["role_source"] = by_id.get(issue.get("status_id", "")), "profile"
    return issues


def notes(issues: List[dict], profiles: Dict[str, dict], problems: Optional[Dict[str, tuple]] = None) -> List[str]:
    """What a reader must know before trusting a report: projects without profile, profile files nobody could read
    (`problems`: project -> (kind, why)), statuses still undecided, statuses the profile has never seen."""
    problems = problems or {}
    missing: set = set()
    broken: Dict[str, tuple] = {}
    undecided: Dict[str, set] = {}
    unknown: set = set()
    for issue in issues:
        project = project_of(issue["key"])
        profile = profiles.get(project)
        if profile is None:
            if project in problems:
                broken[project] = problems[project]
            else:
                missing.add(project)
            continue
        entry = {s["id"]: s for s in profile["statuses"]}.get(issue.get("status_id", ""))
        if entry is None:
            unknown.add((project, issue.get("status", "")))
        elif entry["role"] is None:
            undecided.setdefault(project, set()).add(entry["name"])
    lines = []
    if missing:
        lines.append("Sin perfil: " + ", ".join(sorted(missing)) + ". Se usa la categoría de Jira; corré `jk board setup KEY`.")
    for project in sorted(broken):
        kind, why = broken[project]
        fix = "actualizá jk" if kind == "newer" else f"corré `jk board setup {project}` para rehacerlo"
        lines.append(f"Perfil de {project} ilegible ({why}): se usa la categoría de Jira; {fix}.")
    for project in sorted(undecided):
        lines.append(f"Perfil sin confirmar en {project}: faltan decidir {', '.join(sorted(undecided[project]))}.")
    for project, status in sorted(unknown):
        lines.append(f"Estado desconocido: {status} ({project}). El workflow cambió; corré `jk board check {project}`.")
    return lines
