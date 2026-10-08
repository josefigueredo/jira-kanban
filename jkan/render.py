"""Markdown for the reports: tables (keys are links) and trees (in a code block, so the lines stay aligned).

Labels are Spanish, like `jk board`; error messages elsewhere stay English."""
from __future__ import annotations

import datetime as _dt
import re
from typing import Callable, List, Optional

from . import stats

Link = Callable[[str], str]
KEYLIKE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
NOTE_DONE = ("_Nota: Jira guarda solo el último cambio de estado, así que un issue que pasó por «en curso» y luego a "
             "Done figura con la fecha de Done. «Hecho» significa asignado a la persona (inferencia: si otra persona "
             "cerró un issue suyo, igual aparece)._")


def _cell(value) -> str:
    return "–" if value in (None, "") else str(value).replace("|", "\\|").replace("\n", " ")


def table(headers: List[str], rows: List[list], empty: str = "_Nada._") -> str:
    if not rows:
        return empty
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    return "\n".join(lines + ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows])


def head(title: str, owner: str, today: _dt.date, window: Optional[tuple] = None, project: Optional[str] = None) -> str:
    parts = [f"**Quién:** {owner}"]
    if window:
        parts.append(f"**Ventana:** {window[0]} → {window[1]}")
    if project:
        parts.append(f"**Proyecto:** {project}")
    parts.append(f"**Consultado:** {today}")
    return f"## {title}\n" + " · ".join(parts)


def _label(node: dict) -> str:
    issue = node["issue"]
    if not issue["key"]:
        return issue["summary"]
    bits = [f"{issue['key']} {issue['summary']}"]
    if not node["context"]:
        bits += [b for b in (issue["status"], issue["changed"]) if b]
    return " · ".join(bits) + (" (contexto)" if node["context"] else "")


def _branch(children: List[dict], prefix: str) -> List[str]:
    lines: List[str] = []
    for k, child in enumerate(children):
        last = k == len(children) - 1
        lines.append(f"{prefix}{'└─ ' if last else '├─ '}{_label(child)}")
        lines += _branch(child["children"], prefix + ("   " if last else "│  "))
    return lines


def render_tree(tree: List[dict]) -> str:
    lines: List[str] = []
    for root in tree:
        lines.append(_label(root))
        lines += _branch(root["children"], "")
    return "\n".join(lines)


def render_done(head_text: str, result: dict) -> str:
    totals = f"**{result['done']} cerradas · {result['in_progress']} en curso**"
    body = f"```text\n{render_tree(result['tree'])}\n```" if result["tree"] else "_Nada en esta ventana._"
    return "\n\n".join([head_text, totals, body, NOTE_DONE])


def render_next(head_text: str, tables: dict, until: _dt.date, link: Link) -> str:
    ready = table(["Key", "Título", "Prioridad", "Vence", "Estado"],
                  [[link(i["key"]), i["summary"], i["priority"], i["duedate"], i["status"]] for i in tables["ready"]],
                  "_Nada para hacer ya._")
    due = table(["Key", "Título", "Prioridad", "Vence", "Estado"],
                [[link(r["issue"]["key"]), r["issue"]["summary"], r["issue"]["priority"],
                  ("vencido " if r["overdue"] else "") + r["issue"]["duedate"],
                  r["issue"]["status"] + (" (bloqueado)" if r["blocked"] else "")] for r in tables["due"]],
                "_Nada con fecha en la ventana._")
    unowned = table(["Key", "Título", "Épica", "Prioridad"],
                    [[link(i["key"]), i["summary"], i["parent"]["key"] if i["parent"] else "", i["priority"]]
                     for i in tables["unowned"]], "_Nada sin dueño en sus épicas._")
    return "\n\n".join([head_text, "### Para hacer ya\n" + ready, f"### Vence hasta {until}\n" + due,
                        "### Sin dueño en sus épicas (para tomar)\n" + unowned])


def _by(row: dict, link: Link) -> str:
    return f"{link(row['by'])} {row['title']}".strip() if KEYLIKE.match(row["by"]) else row["by"]


def render_blocked(head_text: str, rows: List[dict], link: Link) -> str:
    body = table(["Key", "Título", "Prioridad", "Vence", "Estado", "Bloqueado por", "Estado del bloqueador",
                  "Dueño del bloqueador"],
                 [[link(r["issue"]["key"]), r["issue"]["summary"], r["issue"]["priority"], r["issue"]["duedate"],
                   r["issue"]["status"], _by(r, link), r["status"], r["owner"]] for r in rows],
                 "_Nada bloqueado._")
    return head_text + "\n\n" + body


METRICS = (("Abiertos asignados", "open"), ("En curso (WIP)", "in_progress"), ("Bloqueados", "blocked"),
           ("Vencidos", "overdue"), (f"Vencen en {stats.DUE_SOON_DAYS} días", "due_soon"))


def _weekly(weekly: List[dict]) -> str:
    return " · ".join(f"{w['closed']}{'*' if w['partial'] else ''}" for w in weekly)


def render_load(head_text: str, name: str, numbers: dict, mine_name: Optional[str] = None,
                mine: Optional[dict] = None) -> str:
    rows = [[label, numbers[key]] + ([mine[key]] if mine else []) for label, key in METRICS]
    rows.append(["Cerrados por semana (viejo → nuevo; * = semana en curso)", _weekly(numbers["weekly"])]
                + ([_weekly(mine["weekly"])] if mine else []))
    grid = table(["Métrica", name] + ([mine_name] if mine else []), rows)
    verdict = numbers["verdict"]
    if verdict:
        room = (f"tiene espacio para {verdict['room']} más" if verdict["room"] > 0 else "sin espacio")
        line = f"**{name}:** WIP {numbers['in_progress']}/{verdict['wip_limit']} → {room}"
    else:
        line = ("_Sin veredicto: no hay `wip_limit` en .jira-kanban/conventions.json y Jira no tiene estimaciones en "
                "PLATE. Lo de arriba es lo medido; el umbral lo pone el equipo._")
    return "\n\n".join([head_text, grid, line])


def render_stats(head_text: str, s: dict, link: Link) -> str:
    weekly = table(["Semana (lunes)", "Cerrados"],
                   [[w["week"], f"{w['closed']}{' (en curso)' if w['partial'] else ''}"] for w in s["weekly"]])
    lead = s["lead"]
    lead_text = (f"n={lead['n']} · mediana {lead['median']} d · p85 {lead['p85']} d"
                 + (" · pocos casos, no concluyas nada" if lead["n"] < 10 else "")) if lead else "_Sin cierres en el período._"
    wip = table(["Key", "Título", "Días sin cambio", "Estado"],
                [[link(r["issue"]["key"]), r["issue"]["summary"], r["days"], "estancado" if r["stalled"] else ""]
                 for r in s["wip"]], "_Nada en curso._")
    on_time = s["on_time"]
    on_time_text = (f"{on_time['on_time']}/{on_time['n']} a tiempo ({on_time['pct']}%)" if on_time
                    else "_Ninguno de lo cerrado tenía fecha de vencimiento._")
    by_area = table(["Área", "Cerrados"], [[k, v] for k, v in sorted(s["mix"]["by_area"].items())], "_Sin cierres._")
    by_type = table(["Tipo", "Cerrados"], [[k, v] for k, v in sorted(s["mix"]["by_type"].items())], "_Sin cierres._")
    oldest = table(["Key", "Título", "Días abierto"],
                   [[link(r["issue"]["key"]), r["issue"]["summary"], r["days"]] for r in s["oldest"]], "_Nada abierto._")
    return "\n\n".join([head_text, f"### Velocidad: issues cerrados por semana (últimas {s['weeks']})\n" + weekly,
                        "### Lead time (creación → cierre)\n" + lead_text,
                        f"### Edad del WIP (estancado ≥ {stats.STALLED_DAYS} días)\n" + wip,
                        "### Cumplimiento de fechas\n" + on_time_text,
                        "### Mezcla de trabajo\n" + by_area + "\n\n" + by_type, "### Backlog más viejo\n" + oldest])
