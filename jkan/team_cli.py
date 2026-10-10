"""jk team setup | show | list | status | stalled | blocked | flow | digest | desk | rollup: reports about the boards and the
team a manager follows. They only read Jira; the one thing written is the local view (jk team setup).

Exit codes: 0 done, 1 findings or a refused input (a board without profile, a bad view), 2 could not do it (Jira, disk)."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import namedtuple
from typing import Callable, List

from . import board_profile, people, roles, team, team_render, views, window
from .jira import JiraError

OK, FINDINGS, CANNOT = 0, 1, 2
REPORTS = ("status", "stalled", "blocked", "flow", "digest", "desk")
VERBS = ("setup", "show", "list", "rollup") + REPORTS
Result = namedtuple("Result", "title window payload body seen truncated")


class Refusal(ValueError):
    """A report that cannot be computed honestly (a board without profile)."""


def _describe(view: dict) -> str:
    return (f"## View {view['name']}\n**Boards:** {', '.join(view['boards'])} · "
            f"**Equipo:** {team_render.team_label(view['team'])} · **Estancado desde:** {view['stalled_days']} días")


def _profile_rows(view: dict, profiles: dict) -> list:
    rows = []
    for board in view["boards"]:
        if board not in profiles:
            rows.append([board, "sin perfil"])
        else:
            pending = len(board_profile.open_statuses(profiles[board]))
            rows.append([board, "confirmado" if not pending else f"sin confirmar ({pending} sin decidir)"])
    return rows


def _setup(args, jira) -> int:
    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    chosen = None
    note = ""
    if args.group:
        try:
            total = jira().group_total(args.group)
        except JiraError as exc:
            if "HTTP 404" in str(exc):
                raise ValueError(f"Jira has no group {args.group!r}") from exc
            raise
        chosen, note = {"group": args.group}, f"Grupo {args.group}: {total} miembros."
    elif args.people:
        client = jira()
        found = [people.resolve(client, name, boards[0] if boards else None) for name in args.people]
        chosen = {"people": [{"id": p["id"], "name": p["name"]} for p in found]}
        note = "Personas: " + ", ".join(p["name"] for p in found) + "."
    view = views.build(args.name, boards, chosen, args.stalled_days)
    path = views.save(view)
    print(_describe(view))
    if note:
        print("\n" + note)
    profiles, _ = board_profile.scan()
    lacking = team.missing_profiles(view, profiles)
    if lacking:
        print(f"\nFalta el perfil de: {', '.join(lacking)}. Corré `jk board setup KEY` para cada uno antes de pedir reportes.")
    print(f"\nView guardado en {path}")
    return OK


def _show(args) -> int:
    view = views.load(args.name)
    profiles, _ = board_profile.scan()
    print(_describe(view) + "\n\n" + team_render.table(["Board", "Perfil"], _profile_rows(view, profiles), True))
    return OK


def _list() -> int:
    rows = []
    for name in views.names():
        try:
            view = views.load(name)
            rows.append([name, ", ".join(view["boards"]), team_render.team_label(view["team"])])
        except views.BadView as exc:
            rows.append([name, f"ilegible: {exc}", ""])
    print(team_render.table(["View", "Boards", "Equipo"], rows, True, "_Ningún view. Creá uno con `jk team setup`._"))
    return OK


def _context(name: str):
    view = views.load(name)
    profiles, problems = board_profile.scan()
    lacking = team.missing_profiles(view, profiles)
    if lacking:
        broken = [b for b in lacking if b in problems]
        extra = f" ({', '.join(f'{b}: {problems[b][1]}' for b in broken)})" if broken else ""
        raise Refusal(f"no profile for {', '.join(lacking)}{extra}: run jk board setup {lacking[0]}")
    return view, profiles


def _link(jira) -> Callable[[str], str]:
    return lambda key: f"[{key}]({jira.browse_url(key)})"


def _status(args, jira, view, profiles, conv, today) -> Result:
    issues, cut = team.gather_open(jira, view, profiles, conv)
    report = team.status_report(issues, view, profiles)
    return Result("Estado del equipo", None, report, team_render.render_status(report, args.all), issues, cut)


def _stalled(args, jira, view, profiles, conv, today) -> Result:
    days = args.days if args.days is not None else view["stalled_days"]
    if not 1 <= days <= 365:
        raise ValueError("--days must be a whole number from 1 to 365")
    issues, cut = team.gather_open(jira, view, profiles, conv)
    report = team.stalled_report(issues, today, days)
    return Result("Estancados", None, report, team_render.render_stalled(report, args.all, _link(jira)), issues, cut)


def _blocked(args, jira, view, profiles, conv, today) -> Result:
    issues, cut = team.gather_open(jira, view, profiles, conv)
    report = team.blocked_report(issues, conv, today)
    return Result("Bloqueos", None, report, team_render.render_blocked(report, args.all, _link(jira)), issues, cut)


def _flow(args, jira, view, profiles, conv, today) -> Result:
    weeks = window.weeks(args.weeks)
    first = team.first_week(today, weeks)
    issues, cut1 = team.gather_open(jira, view, profiles, conv)
    delivered, cut2 = team.gather_closed(jira, view, profiles, conv, ("delivered",), first)
    dropped, cut3 = team.gather_closed(jira, view, profiles, conv, ("dropped",), first)
    report = team.flow_report(delivered, dropped, issues, today, weeks)
    return Result("Flujo", (first, today), report, team_render.render_flow(report, args.all, _link(jira)),
                  issues + delivered + dropped, cut1 or cut2 or cut3)


def _digest(args, jira, view, profiles, conv, today) -> Result:
    since, until = window.span(args.since, args.until, today)
    issues, cut1 = team.gather_open(jira, view, profiles, conv)
    delivered, cut2 = team.gather_closed(jira, view, profiles, conv, ("delivered",), since)
    dropped, cut3 = team.gather_closed(jira, view, profiles, conv, ("dropped",), since)
    created, cut4 = team.gather_created(jira, view, profiles, conv, since, until)
    report = team.digest_report(delivered, dropped, created, issues, conv, since, until, today, view["stalled_days"])
    return Result("Resumen del período", (since, until), report,
                  team_render.render_digest(report, args.all, _link(jira)),
                  issues + delivered + dropped, cut1 or cut2 or cut3 or cut4)


def _desk(args, jira, view, profiles, conv, today) -> Result:
    weeks = window.weeks(args.weeks)
    if not team.desk_boards(view, profiles):
        raise team.NoDesk(f"view {view['name']!r} has no help desk board: set one with jk board setup KEY --kind helpdesk")
    first = team.first_week(today, weeks)
    issues, cut1 = team.gather_open(jira, view, profiles, conv)
    delivered, cut2 = team.gather_closed(jira, view, profiles, conv, ("delivered",), first)
    report = team.desk_report(issues, delivered, view, profiles, today, weeks)
    return Result("Mesa de ayuda", (first, today), report, team_render.render_desk(report, args.all),
                  issues + delivered, cut1 or cut2)


BUILDERS = {"status": _status, "stalled": _stalled, "blocked": _blocked, "flow": _flow, "digest": _digest, "desk": _desk}


def _emit(args, verb: str, view: dict, profiles: dict, today: _dt.date, result: Result) -> None:
    notes = roles.notes(result.seen, profiles)
    if args.json:
        print(json.dumps({"view": view["name"], "boards": view["boards"], "consulted": today.isoformat(),
                          "profiles": team_render.profile_state(view, profiles), "truncated": result.truncated,
                          "notes": notes, "report": result.payload}, ensure_ascii=False, indent=2, default=str))
        return
    parts = [team_render.head(result.title, view, profiles, today, result.window)]
    alerts = ([f"La búsqueda llegó al tope de {team.CAP} issues: faltan resultados."] if result.truncated else []) + notes
    if alerts:
        parts.append("\n".join(f"> ⚠ {line}" for line in alerts))
    parts += [result.body, team_render.limits(verb)]
    print("\n\n".join(parts))


def _report(args, jira, conv: dict, today: _dt.date) -> int:
    view, profiles = _context(args.view)
    client = jira()
    _emit(args, args.verb, view, profiles, today, BUILDERS[args.verb](args, client, view, profiles, conv, today))
    return OK


def _rollup(args, jira, conv: dict, today: _dt.date) -> int:
    profiles, _ = board_profile.scan()
    client = jira()
    first = team.first_week(today, 4)
    rows, failed = [], False
    for name in args.views:
        try:
            view = views.load(name)
            lacking = team.missing_profiles(view, profiles)
            if lacking:
                raise Refusal(f"sin perfil: {', '.join(lacking)}")
        except (views.BadView, Refusal) as exc:
            rows.append({"view": name, "error": str(exc)})
            failed = True
            continue
        issues, cut1 = team.gather_open(client, view, profiles, conv)
        delivered, cut2 = team.gather_closed(client, view, profiles, conv, ("delivered",), first)
        rows.append(dict(team.rollup_row(view, issues, delivered, conv, today), truncated=cut1 or cut2))
    if args.json:
        print(json.dumps({"consulted": today.isoformat(), "rows": rows}, ensure_ascii=False, indent=2, default=str))
    else:
        cut = [r["view"] for r in rows if r.get("truncated")]
        alert = (f"\n\n> ⚠ La búsqueda llegó al tope de {team.CAP} issues en: {', '.join(cut)}." if cut else "")
        print(f"## Resumen de equipos\n**Views:** {', '.join(args.views)} · **Consultado:** {today}{alert}\n\n"
              + team_render.render_rollup(rows, args.all) + "\n\n" + team_render.limits("rollup"))
    return FINDINGS if failed else OK


def run(argv: List[str], jira: Callable[[], object], conv: dict, today: Callable[[], _dt.date]) -> int:
    """argv starts at the verb. `jira` builds the client only for the verbs that read Jira."""
    parser = argparse.ArgumentParser(prog="jk team", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)
    setup = sub.add_parser("setup", help="save the boards and the team you follow under a name")
    setup.add_argument("name", help="a short name: lower case letters, digits, - and _")
    setup.add_argument("--boards", required=True, help="Jira project keys, separated by commas, e.g. PLATE,UA")
    who = setup.add_mutually_exclusive_group()
    who.add_argument("--group", help="a Jira group whose members are the team")
    who.add_argument("--people", nargs="+", help="the team as names, emails or account ids")
    setup.add_argument("--stalled-days", type=int, default=7, help="days in the same category before work counts as stalled (default 7)")
    sub.add_parser("show", help="print a view and the state of its boards' profiles").add_argument("name")
    sub.add_parser("list", help="list the saved views")
    for verb, text in (("status", "open work by role, per board and per person"),
                       ("stalled", "active work that has not changed category for N days"),
                       ("blocked", "what is blocked and what waits for a third party"),
                       ("flow", "deliveries per week, lead time and the age of work in flight"),
                       ("digest", "delivered, dropped and new in a period, plus today's blocked and stalled"),
                       ("desk", "help desk boards: age of open work, unowned, waiting, resolution time")):
        p = sub.add_parser(verb, help=text + " (read only)")
        p.add_argument("view")
        p.add_argument("--all", action="store_true", help="do not cut tables at 20 rows")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if verb == "stalled":
            p.add_argument("--days", type=int, help="default: the view's stalled days")
        if verb in ("flow", "desk"):
            p.add_argument("--weeks", type=int, default=4, help="how many weeks, 1 to 52 (default 4)")
        if verb == "digest":
            p.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
            p.add_argument("--until", help="last day, YYYY-MM-DD (default: today)")
    roll = sub.add_parser("rollup", help="one row per view: open, blocked, stalled, delivered, lead time (read only)")
    roll.add_argument("views", nargs="+")
    roll.add_argument("--all", action="store_true")
    roll.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verb == "setup":
            return _setup(args, jira)
        if args.verb == "show":
            return _show(args)
        if args.verb == "list":
            return _list()
        if args.verb == "rollup":
            return _rollup(args, jira, conv, today())
        return _report(args, jira, conv, today())
    except ValueError as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT
