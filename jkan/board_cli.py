"""jk board setup | set | show | check | survey: what each status of a Jira board means to its team.

Reads Jira; the only thing it writes is the local profile (see board_profile.py). Exit codes: 0 done, 1 findings or
a refused input, 2 could not do it (Jira, disk), 3 the profile still has statuses without a role."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, List, Optional

from . import board_profile, render, roles
from .jira import JiraError

OK, FINDINGS, CANNOT, NEEDS_DECISION = 0, 1, 2, 3
VERBS = ("setup", "set", "show", "check", "survey")
CATEGORY = {"todo": "por hacer", "in_progress": "en curso", "done": "hecho"}


def _render(profile: dict) -> str:
    rows = []
    for s in profile["statuses"]:
        confidence = "confirmado" if s.get("by") == "human" else ("alta" if s["role"] else "decidir")
        rows.append([s["name"], s["id"], CATEGORY.get(s["category"], s["category"]),
                     s["role"] or (f"¿{s['suggest']}?" if s.get("suggest") else "¿?"), confidence, s.get("why") or ""])
    pending = board_profile.open_statuses(profile)
    head = (f"## Perfil {profile['project']}\n**Tipo:** {profile['kind']} · **Estados:** {len(profile['statuses'])} · "
            f"**Sin decidir:** {len(pending)} · **Grupos de tipos:** {len(profile['workflows'])}")
    groups = "\n".join(f"- {', '.join(w['types'])}: {len(w['status_ids'])} estados" for w in profile["workflows"])
    table = render.table(["Estado", "Id", "Categoría de Jira", "Rol", "Confianza", "Por qué"], rows)
    tail = (f"**Faltan {len(pending)} decisiones.** Para cada una: `jk board set {profile['project']} <rol> \"<estado>\"` "
            f"(roles: {', '.join(roles.ROLES)}; si dos estados se llaman igual, `id:<id>`).") if pending \
        else "**Perfil completo.**"
    return "\n\n".join([head, groups, table, tail])


def _needs_profile(key: str) -> Optional[dict]:
    profile = board_profile.load(key)
    if profile is None:
        sys.stderr.write(f"no profile for {key}: run jk board setup {key}\n")
    return profile


def _verdict(profile: dict) -> int:
    return NEEDS_DECISION if board_profile.open_statuses(profile) else OK


def _setup(jira, args) -> int:
    existing = board_profile.load(args.key)
    groups = jira.project_statuses(args.key)
    if not groups:
        raise ValueError(f"Jira returned no statuses for {args.key}: wrong key, or the account cannot see it")
    profile = board_profile.build(args.key, groups, args.kind, existing)
    current = {s["id"] for s in profile["statuses"]}
    gone = [s["name"] for s in (existing or {}).get("statuses", []) if s["id"] not in current]
    path = board_profile.save(profile)
    print(_render(profile))
    if gone:
        print(f"\nYa no existen en Jira: {', '.join(gone)}.")
    print(f"\nPerfil guardado en {path}")
    return _verdict(profile)


def _set(args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    try:
        board_profile.assign(profile, args.role, args.status)
    except board_profile.BadSelection as exc:
        sys.stderr.write(f"{exc}\n")
        return FINDINGS
    board_profile.save(profile)
    print(_render(profile))
    return _verdict(profile)


def _show(args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    print(_render(profile))
    return _verdict(profile)


def _check(jira, args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    fresh = {s["id"]: s for g in jira.project_statuses(args.key) for s in g["statuses"]}
    if board_profile.fingerprint(list(fresh.values())) == profile["fingerprint"]:
        print(f"{args.key}: sin cambios en los estados.")
        return OK
    known = {s["id"]: s for s in profile["statuses"]}
    added = sorted(s["name"] for i, s in fresh.items() if i not in known)
    removed = sorted(s["name"] for i, s in known.items() if i not in fresh)
    print(f"{args.key}: el workflow cambió. Nuevos: {', '.join(added) or '–'}. Ya no están: {', '.join(removed) or '–'}.")
    print(f"Corré `jk board setup {args.key}` para actualizar; las decisiones que tomaste se conservan.")
    return FINDINGS


def _survey(jira, args) -> int:
    projects = [p for p in jira.projects() if not args.type or p["type"] == args.type]
    if args.limit:
        projects = projects[:args.limit]
    rows, denied = [], 0
    for project in projects:
        try:
            groups = jira.project_statuses(project["key"])
        except JiraError:
            denied += 1
            continue
        unique = {s["id"]: s for g in groups for s in g["statuses"]}
        proposals = [roles.propose(s) for s in unique.values()]
        rows.append({"project": project["key"], "type": project["type"], "statuses": len(unique),
                     "alta": sum(1 for p in proposals if p["confidence"] == "alta"),
                     "decidir": sum(1 for p in proposals if p["confidence"] == "decidir"),
                     "mismatch": sum(1 for p in proposals if p["mismatch"])})
    statuses = sum(r["statuses"] for r in rows)
    summary = {"projects_read": len(rows), "projects_denied": denied, "statuses": statuses,
               "alta": sum(r["alta"] for r in rows), "decidir": sum(r["decidir"] for r in rows),
               "projects_needing_decisions": sum(1 for r in rows if r["decidir"]),
               "mismatch_statuses": sum(r["mismatch"] for r in rows),
               "mismatch_projects": sum(1 for r in rows if r["mismatch"])}
    if args.json:
        print(json.dumps({"summary": summary, "projects": rows}, ensure_ascii=False, indent=2))
        return OK
    print(render.table(["Proyecto", "Tipo", "Estados", "Alta", "Decidir", "Categoría mal puesta"],
                       [[r["project"], r["type"], r["statuses"], r["alta"], r["decidir"], r["mismatch"]] for r in rows],
                       "_Ningún proyecto._"))
    pct = (lambda n: f"{round(100 * n / statuses)}%") if statuses else (lambda n: "–")
    print(f"\n{summary['projects_read']} proyectos leídos · {denied} sin acceso · {statuses} estados · "
          f"alta {summary['alta']} ({pct(summary['alta'])}) · decidir {summary['decidir']} ({pct(summary['decidir'])}) · "
          f"{summary['projects_needing_decisions']} proyectos con decisiones pendientes · "
          f"{summary['mismatch_statuses']} estados con la categoría mal puesta en {summary['mismatch_projects']} proyectos")
    return OK


def run(argv: List[str], jira: Callable[[], object]) -> int:
    """argv starts at the verb. `jira` builds the client only for the verbs that read Jira."""
    parser = argparse.ArgumentParser(prog="jk board", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)
    setup = sub.add_parser("setup", help="read a project's statuses from Jira, propose a role for each, save the profile")
    setup.add_argument("key", help="Jira project key, e.g. UA")
    setup.add_argument("--kind", choices=board_profile.KINDS, help="how the board works (default: flow, or what the profile says)")
    give = sub.add_parser("set", help="give a role to statuses, by name or id:<id>")
    give.add_argument("key")
    give.add_argument("role", choices=roles.ROLES)
    give.add_argument("status", nargs="+")
    for name, text in (("show", "print the saved profile"), ("check", "compare the profile with Jira's statuses now")):
        sub.add_parser(name, help=text).add_argument("key")
    survey = sub.add_parser("survey", help="propose roles for many projects and count what needs a decision; saves nothing")
    survey.add_argument("--type", help="only projects of this type, e.g. software or service_desk")
    survey.add_argument("--limit", type=int, help="only the first N projects")
    survey.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    try:
        if args.verb == "setup":
            return _setup(jira(), args)
        if args.verb == "set":
            return _set(args)
        if args.verb == "show":
            return _show(args)
        if args.verb == "check":
            return _check(jira(), args)
        return _survey(jira(), args)
    except ValueError as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT
