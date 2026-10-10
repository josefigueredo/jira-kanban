"""Markdown for the team reports, following the output contract of the spec: a fixed first block, every number with its n,
at most 20 rows per table (--all lifts it), and a fixed «Límites» section. Labels are Spanish, like the other reports."""
from __future__ import annotations

import datetime as _dt
from typing import Callable, Dict, List, Optional

from . import board_profile, render

Link = Callable[[str], str]
CAP_ROWS = 20
SMALL_N = 10

LIMITS = {
    "status": [
        "«Sin rol» son issues en estados que el perfil todavía no decidió o no conoce.",
        "«Sin asignar» cuenta lo abierto sin dueño en esos boards, sea o no del equipo; lo asignado a otras personas no se cuenta.",
        "El veredicto de carga sale del límite de WIP de cada perfil (`jk board limit KEY N`); sin límite, solo números."],
    "stalled": [
        "«Estancado» no es «sin progreso»: la categoría de Jira solo cambia al pasar de una categoría a otra, así que moverse "
        "entre dos estados «en curso» no reinicia los días en la categoría.",
        "Los días desde la última edición se reinician con cualquier cambio, comentarios incluidos."],
    "blocked": [
        "Un issue figura como bloqueado por su rol, por el flag o por un link «is blocked by» sin resolver.",
        "«Esperando» (rol `waiting`) es trabajo frenado por un tercero y va aparte."],
    "flow": [
        "Sin story points: la velocidad se mide en issues entregados (rol `delivered`) por semana.",
        "La fecha de entrega es la de resolución o, si falta, la del último cambio de categoría: un `Done` archivado en otra "
        "categoría puede figurar con una fecha anterior.",
        "No hay tiempo de ciclo real: el lead time va de la creación a la entrega."],
    "digest": [
        "«Nuevo» es lo creado en el período en esos boards, sea o no del equipo.",
        "Bloqueados, esperando y estancados son el estado de hoy, no el del período."],
    "desk": [
        "Sin SLA: ningún service desk medido tenía datos de SLA. La edad corre desde la creación y no cuenta lo que espera a un tercero.",
        "El tiempo de resolución va de la creación a la entrega."],
    "rollup": [
        "Cada fila sale de un view completo; un view con un board sin perfil no se calcula.",
        "Entregados y p85 miden las últimas 4 semanas."],
}


def team_label(team: Optional[dict]) -> str:
    if not team:
        return "todos los asignados"
    if "group" in team:
        return f"grupo {team['group']}"
    return f"{len(team['people'])} personas"


def profile_state(view: dict, profiles: Dict[str, dict]) -> str:
    pending = {b: len(board_profile.open_statuses(profiles[b])) for b in view["boards"] if b in profiles}
    pending = {b: n for b, n in pending.items() if n}
    if not pending:
        return "confirmados"
    return "sin confirmar — " + ", ".join(f"{b} ({n} sin decidir)" for b, n in sorted(pending.items()))


def head(title: str, view: dict, profiles: Dict[str, dict], today: _dt.date, window: Optional[tuple] = None) -> str:
    parts = [f"**View:** {view['name']}", f"**Boards:** {', '.join(view['boards'])}",
             f"**Equipo:** {team_label(view['team'])}"]
    if window:
        parts.append(f"**Ventana:** {window[0]} → {window[1]}")
    parts += [f"**Consultado:** {today}", f"**Perfiles:** {profile_state(view, profiles)}"]
    return f"## {title}\n" + " · ".join(parts)


def limits(verb: str) -> str:
    return "### Límites\n" + "\n".join(f"- {line}" for line in LIMITS[verb])


def table(headers: List[str], rows: List[list], show_all: bool, empty: str = "_Nada._") -> str:
    """The table, cut at 20 rows with a note that says how many were left out (nothing is dropped silently)."""
    shown = rows if show_all or len(rows) <= CAP_ROWS else rows[:CAP_ROWS]
    note = "" if len(shown) == len(rows) else f"\n\n_… y {len(rows) - len(shown)} más (usá --all)._"
    return render.table(headers, shown, empty) + note


def _who(issue: dict) -> str:
    owner = issue.get("assignee")
    return owner["name"] if owner else "sin asignar"


def _days(value) -> str:
    return "–" if value is None else str(value)


def _small(n: int) -> str:
    return " · pocos casos, no concluyas nada" if n < SMALL_N else ""


def _spread(spread: Optional[dict], empty: str) -> str:
    if not spread:
        return empty
    return f"n={spread['n']} · mediana {spread['median']} d · p85 {spread['p85']} d{_small(spread['n'])}"


def render_status(report: dict, show_all: bool) -> str:
    boards = table(["Board", "Abiertos", "Por hacer", "En curso", "Bloqueado", "Esperando", "Sin rol", "Sin asignar"],
                   [[r["board"], r["n"], r["todo"], r["active"], r["blocked"], r["waiting"], r["none"], r["unassigned"]]
                    for r in report["boards"]], show_all)

    def verdict(row: dict) -> str:
        if row["room"] is None:
            return "–"
        return "sin espacio" if row["room"] <= 0 else f"espacio para {row['room']}"

    people = table(["Persona", "Board", "Abiertos", "Por hacer", "En curso", "Bloqueado", "Esperando", "Sin rol", "WIP",
                    "Límite", "Veredicto"],
                   [[r["person"], r["board"], r["n"], r["todo"], r["active"], r["blocked"], r["waiting"], r["none"],
                     r["wip"], r["wip_limit"], verdict(r)] for r in report["people"]], show_all,
                   "_Nadie del equipo tiene trabajo abierto._")
    return "\n\n".join([f"**{report['n']} abiertos** (issues del equipo y sin asignar)", "### Por board\n" + boards,
                        "### Por persona y board\n" + people])


def render_stalled(report: dict, show_all: bool, link: Link) -> str:
    rows = report["rows"]
    body = table(["Key", "Título", "Dueño", "Estado", "Días en la categoría", "Días desde la última edición"],
                 [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), r["issue"]["status"],
                   r["days_in_category"], _days(r["days_since_edit"])] for r in rows], show_all,
                 "_Nada estancado._")
    return "\n\n".join([f"**{len(rows)} de {report['n_active']} en curso** llevan {report['days']} días o más en su categoría",
                        body])


def render_blocked(report: dict, show_all: bool, link: Link) -> str:
    def by(row: dict) -> str:
        return f"{link(row['by'])} {row['title']}".strip() if render.KEYLIKE.match(row["by"]) else row["by"]

    blocked = table(["Key", "Título", "Dueño", "Por qué", "Estado del bloqueador", "Dueño del bloqueador", "Días"],
                    [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), by(r), r["status"], r["owner"],
                      _days(r["days"])] for r in report["blocked"]], show_all, "_Nada bloqueado._")
    waiting = table(["Key", "Título", "Dueño", "Estado", "Días"],
                    [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), r["issue"]["status"],
                      _days(r["days"])] for r in report["waiting"]], show_all, "_Nada esperando a un tercero._")
    return "\n\n".join([f"### Bloqueados ({len(report['blocked'])})\n" + blocked,
                        f"### Esperando a un tercero ({len(report['waiting'])})\n" + waiting])


def render_flow(report: dict, show_all: bool, link: Link) -> str:
    weekly = table(["Semana (lunes)", "Entregados"],
                   [[w["week"], f"{w['closed']}{' (en curso)' if w['partial'] else ''}"] for w in report["weekly"]],
                   show_all)
    wip = table(["Key", "Título", "Dueño", "Días sin cambio de categoría", "Estado"],
                [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), r["days"],
                  "estancado" if r["stalled"] else ""] for r in report["wip"]], show_all, "_Nada en curso._")
    return "\n\n".join([
        f"**{report['delivered_n']} entregados** desde {report['since']}; {report['dropped_n']} descartados "
        "(no cuentan como entregas)",
        f"### Entregados por semana (últimas {report['weeks']})\n" + weekly,
        "### Lead time (creación → entrega)\n" + _spread(report["lead"], "_Sin entregas en el período._"),
        "### Edad del trabajo en curso\n" + wip])


def render_digest(report: dict, show_all: bool, link: Link) -> str:
    def listing(issues: List[dict], day: Callable[[dict], Optional[str]]) -> str:
        return table(["Key", "Título", "Dueño", "Fecha"],
                     [[link(i["key"]), i["summary"], _who(i), day(i) or "–"] for i in issues], show_all)

    totals = (f"**{len(report['delivered'])} entregados · {len(report['dropped'])} descartados · "
              f"{len(report['created'])} nuevos** · hoy: {report['blocked_now']} bloqueados, "
              f"{report['waiting_now']} esperando, {report['stalled_now']} estancados (≥ {report['days']} días)")
    return "\n\n".join([totals,
                        "### Entregados\n" + listing(report["delivered"], lambda i: i.get("resolved") or i.get("changed")),
                        "### Descartados\n" + listing(report["dropped"], lambda i: i.get("changed")),
                        "### Nuevos\n" + listing(report["created"], lambda i: i.get("created"))])


def render_desk(report: dict, show_all: bool) -> str:
    labels = list(report["boards"][0]["age"]) if report["boards"] else []
    body = table(["Board", "Abiertos"] + labels + ["Sin asignar", "Esperando", "Sin rol", "Resueltos"],
                 [[r["board"], r["open"]] + [r["age"][label] for label in labels]
                  + [r["unassigned"], r["waiting"], r["unknown"], r["resolved_n"]] for r in report["boards"]], show_all)
    times = "\n".join(f"- **{r['board']}:** " + _spread(r["resolution"], "sin resueltos en el período")
                      for r in report["boards"])
    return "\n\n".join(["### Abiertos por antigüedad (sin contar lo que espera a un tercero)\n" + body,
                        f"### Tiempo de resolución (últimas {report['weeks']} semanas)\n" + times])


def render_rollup(rows: List[dict], show_all: bool) -> str:
    def lead(row: dict) -> str:
        spread = row.get("lead")
        return "–" if not spread else f"{spread['p85']} d (n={spread['n']})"

    cells = []
    for r in rows:
        if "error" in r:
            cells.append([r["view"], r["error"], "", "", "", ""])
        else:
            cells.append([r["view"], r["open"], r["blocked"], r["stalled"], r["delivered"], lead(r)])
    return table(["View", "Abiertos", "Bloqueados", "Estancados", "Entregados (4 sem)", "Lead time p85"], cells, show_all)
