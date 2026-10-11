"""Markdown for the reports: tables (keys are links) and trees (in a code block, so the lines stay aligned).

Labels are Spanish, like `jtk board`; error messages elsewhere stay English."""
from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Callable, List, Optional

from . import stats

Link = Callable[[str], str]
KEYLIKE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
NOTE_DONE = ("_Nota: Jira guarda solo el último cambio de estado, así que un issue que pasó por «en curso» y luego a "
             "Done figura con la fecha de Done. «Hecho» significa asignado a la persona (inferencia: si otra persona "
             "cerró un issue suyo, igual aparece)._")


def dump(payload) -> str:
    """JSON for a script or an agent: one compact line (indenting costs about a third more and nobody reads it)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _cell(value) -> str:
    return "–" if value in (None, "") else str(value).replace("|", "\\|").replace("\n", " ")


_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _shown(cell: str) -> int:
    """The width a cell takes once rendered: a link counts as its text, not its url."""
    return len(_LINK.sub(r"\1", cell))


def table(headers: List[str], rows: List[list], empty: str = "_Nada._") -> str:
    """A Markdown table whose source is aligned too, so it reads the same rendered or raw. Widths follow what a link shows,
    not its url, so alignment costs a few spaces and not a copy of every url."""
    if not rows:
        return empty
    cells = [[_cell(c) for c in row] for row in rows]
    widths = [max(3, len(h), *(_shown(row[i]) for row in cells)) for i, h in enumerate(headers)]
    pad = lambda v, w: v + " " * (w - _shown(v))  # noqa: E731
    line = lambda values: "| " + " | ".join(pad(v, w) for v, w in zip(values, widths)) + " |"  # noqa: E731
    return "\n".join([line(headers), "| " + " | ".join("-" * w for w in widths) + " |"] + [line(row) for row in cells])


def head(title: str, owner: str, today: _dt.date, window: Optional[tuple] = None, project: Optional[str] = None) -> str:
    parts = [f"**Quién:** {owner}"]
    if window:
        parts.append(f"**Ventana:** {window[0]} → {window[1]}")
    if project:
        parts.append(f"**Proyecto:** {project}")
    parts.append(f"**Consultado:** {today}")
    return f"## {title}\n" + " · ".join(parts)


GAP = "  "


def _widths(rows: List[tuple]) -> List[int]:
    return [max(len(r[i]) for r in rows) for i in range(len(rows[0]) - 1)]


def _line(row: tuple, widths: List[int]) -> str:
    return (GAP.join(c.ljust(w) for c, w in zip(row, widths)) + GAP + row[-1]).rstrip()


def columns(rows: List[tuple]) -> List[str]:
    """Aligned text lines: every column padded to its widest cell but the last, which is free to be long."""
    widths = _widths(rows)
    return [_line(r, widths) for r in rows]


TREE_HEAD = ("Issue", "Estado", "Fecha", "Título")


def _walk(node: dict, lead: str, below: str, rows: List[tuple]) -> None:
    """Adds the node's line, then its children's. A row is (tree + key, status, date, title); a heading with no key is
    (label,). The title goes last so a long one never pushes the other columns out of line."""
    issue = node["issue"]
    if not issue["key"]:
        rows.append((issue["summary"],))
    elif node["context"]:
        rows.append((lead + issue["key"], "", "", issue["summary"] + " (contexto)"))
    else:
        rows.append((lead + issue["key"], issue["status"] or "", issue["changed"] or "", issue["summary"]))
    for k, child in enumerate(node["children"]):
        last = k == len(node["children"]) - 1
        _walk(child, below + ("└─ " if last else "├─ "), below + ("   " if last else "│  "), rows)


def render_tree(tree: List[dict]) -> str:
    rows: List[tuple] = []
    for root in tree:
        _walk(root, "", "", rows)
    widths = _widths([TREE_HEAD] + [r for r in rows if len(r) == 4])
    return "\n".join(r[0] if len(r) == 1 else _line(r, widths) for r in [TREE_HEAD] + rows)


def render_done(head_text: str, result: dict) -> str:
    totals = f"**{result['done']} cerradas · {result['in_progress']} en curso**"
    if result.get("dropped"):
        totals += f" · {result['dropped']} descartadas"
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
    tags = s.get("tags")
    grouped = []
    if tags:
        word, plural = {"label": ("Etiqueta", "etiquetas"), "component": ("Componente", "componentes")}[tags["by"]]
        grouped = [f"### Por {word.lower()}\n" + table([word, "Cerrados", "Abiertos"], [[r["name"], r["closed"], r["open"]] for r in tags["rows"]],
                                                       "_Nada que contar._")
                   + f"\n\nUn issue con varias {plural} cuenta en cada una; la suma puede pasar el total."]
    return "\n\n".join([head_text, f"### Velocidad: issues cerrados por semana (últimas {s['weeks']})\n" + weekly,
                        "### Lead time (creación → cierre)\n" + lead_text,
                        f"### Edad del WIP (estancado ≥ {stats.STALLED_DAYS} días)\n" + wip,
                        "### Cumplimiento de fechas\n" + on_time_text,
                        "### Mezcla de trabajo\n" + by_area + "\n\n" + by_type, *grouped, "### Backlog más viejo\n" + oldest])
