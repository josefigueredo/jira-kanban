"""jtk: create | pull | push | show | board | who | assign | done | next | blocked | load | stats | board setup|set|show|check|survey | team … | plan … | apply. Every Jira write is a dry run unless --apply is passed; the reports only read."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Callable, List, Optional

from . import (approval, board_cli, board_profile, config, guard, journal, kanban, people, plan_cli, preview, render, roles, standup,
               state, stats, sync, team_cli, views, window)
from .jira import Jira, JiraError

OK, FINDINGS, CANNOT = 0, 1, 2
NEEDS_PERSON = guard.EXIT_NEEDS_PERSON


def excerpt(before: str, after: str, width: int = 60) -> tuple:
    """Both values on one line, cut around their first difference so the change itself is what shows.

    The first characters of two long descriptions are usually the same, so printing them hides the edit. Each side
    keeps a third of the width before the difference and marks a cut with an ellipsis.
    """
    flat = [re.sub(r"\s*\n\s*", " ", str(v or "")).strip() for v in (before, after)]
    if all(len(v) <= width for v in flat):
        return flat[0], flat[1]
    first = next((i for i, (a, b) in enumerate(zip(*flat)) if a != b), min(map(len, flat)))
    start = max(0, first - width // 3)
    return tuple(("…" if start else "") + v[start:start + width] + ("…" if start + width < len(v) else "")
                 for v in flat)


def _client(project: Path, command: Optional[str] = None):
    creds = config.credentials(project)
    if creds is None:
        raise SystemExit("jtk: Jira credentials not found (IC_JIRA_* or JIRA_* in the environment, ./.env.local, "
                         "./.spec-kit/.env)")
    return Jira(*creds, journal=journal.journal(project, command, also=state.log_write) if command else None)


def _show(project: Path, key: str) -> None:
    epic = kanban.epic_dir(project, key)
    if not (epic / "epic.md").is_file():
        print(f"no local kanban for {key}: run jtk pull {key}")
        return
    for entry in sync._local(epic, key):
        depth = {"epic": 0, "story": 1, "task": 1, "subtask": 2}[entry["kind"]]
        label = entry["key"] or entry["path"].parent.name
        print(f"{'  ' * depth}{label} [{entry['kind']}] {entry['status'] or 'new'} · {entry['summary']}")


def _who(jira, name: str, project: Optional[str], as_json: bool) -> int:
    result = people.find(jira, name, project)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        found = result["candidates"]
        print(f"{result['status']}: {len(found)} candidate(s) for {name!r}" if found
              else f"{result['status']}: nobody in Jira matches {name!r}")
        for c in found:
            near = "  (approximate match: check it is who you mean)" if result["status"] != "none" and not c["exact"] else ""
            print(f"  {c['name']} <{c['email'] or 'email hidden'}> {c['id']}{near}")
    return OK if result["status"] == "unique" else FINDINGS


def _short(value, limit: int = 60) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _approve(confirm: Callable, n: int, summary: str, argv: List[str]) -> Optional[int]:
    """None when the write may go ahead (nothing to write, or a person approved); otherwise the exit code to return."""
    if n == 0:
        return None
    try:
        confirm(n, summary, "jtk " + shlex.join(argv))
    except guard.NotApproved as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return NEEDS_PERSON
    return None


def _assign(jira, key: str, who: str, tree: bool, apply: bool, confirm: Callable, argv: List[str]) -> int:
    try:
        person = people.resolve(jira, who, key.split("-")[0])
    except people.NotResolved as exc:
        sys.stderr.write(f"{exc}\n")
        return FINDINGS
    if not person.get("exact", True):
        print(f"approximate match: {who!r} -> {person['name']} <{person['email'] or 'email hidden'}>; "
              f"check it is who you mean")
    if apply:
        planned = sync.assign(jira, key, person, tree=tree, apply=False)
        pending = [i for i in planned["issues"] if i["key"] not in planned["already"]]
        if pending:
            text = f"assign {len(pending)} issue(s) to {person['name']}"
            rows = [(i["key"], i["summary"], f"-> {person['name']}") for i in pending]
            code = _approve(confirm, len(pending), approval.Summary(text, f"Asignar a {person['name']}", rows), argv)
            if code is not None:
                return code
    result = sync.assign(jira, key, person, tree=tree, apply=apply)
    for issue in result["issues"]:
        label = f"{issue['key']} [{issue['issuetype']}] {issue['summary']}"
        if issue["key"] in result["already"]:
            print(f"{label} already assigned to {person['name']}")
        else:
            print(f"{label} -> {person['name']}")
    for error in result["errors"]:
        sys.stderr.write(f"{error}\n")
    changing = len(result["issues"]) - len(result["already"])
    if not apply:
        print(f"dry run: nothing written; --apply assigns {changing} issue(s) to {person['name']}")
    else:
        print(f"assigned {changing - len(result['errors'])} issue(s) to {person['name']}")
    return FINDINGS if result["errors"] else OK


REPORTS = ("done", "next", "blocked", "load", "stats")


def _emit(args, conv: dict, payload, text: str) -> None:
    """Print a report, led by what the reader must know about the profiles it was computed with."""
    notes = roles.notes(conv.get("_seen", []), conv.get("profiles") or {}, conv.get("profile_problems"))
    if args.json:
        print(json.dumps({**payload, "profile_notes": notes}, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n".join(f"> ⚠ {n}" for n in notes) + "\n\n" + text if notes else text)


def _report(jira, args, conv: dict, today: _dt.date) -> int:
    """done | next | blocked | load | stats: read only, for the user or, with --person, for a teammate."""
    conv["profiles"], conv["profile_problems"] = board_profile.scan()
    conv["_seen"] = []
    try:
        if args.cmd == "done":  # the window is checked before Jira is asked anything, even who the person is
            since, until = window.span(args.since, args.until, today)
        elif args.cmd == "next":
            until = window.horizon(args.until, today)
        elif args.cmd in ("load", "stats"):
            weeks = window.weeks(args.weeks)
        scope = conv.get("project")  # one project key, or the boards of a view
        person = ((people.resolve_in(jira, args.person, scope) if isinstance(scope, list) else people.resolve(jira, args.person, scope))
                  if args.person else None)
        pid, owner = (person["id"], person["name"]) if person else (None, "vos")
        link = lambda key: f"[{key}]({jira.browse_url(key)})"  # noqa: E731
        project = ", ".join(scope) if isinstance(scope, list) else scope
        if args.cmd == "done":
            result = standup.gather_done(jira, pid, since, until, conv)
            _emit(args, conv, result, render.render_done(render.head("Hecho", owner, today, (since, until), project), result))
        elif args.cmd == "next":
            tables = standup.gather_next(jira, pid, until, today, conv)
            _emit(args, conv, tables, render.render_next(render.head("Para hacer", owner, today, (today, until), project),
                                                   tables, until, link))
        elif args.cmd == "blocked":
            rows = standup.gather_blocked(jira, pid, conv)
            _emit(args, conv, {"rows": rows}, render.render_blocked(render.head("Bloqueos", owner, today, None, project),
                                                              rows, link))
        else:
            done, open_issues = stats.gather_history(jira, pid, today, weeks, conv)
            if args.cmd == "stats":
                result = stats.compute(done, open_issues, today, weeks, conv)
                _emit(args, conv, result, render.render_stats(render.head("Métricas", owner, today, None, project), result, link))
            else:
                numbers = stats.load_numbers(done, open_issues, today, weeks, conv)
                mine = None
                if person:
                    mine = stats.load_numbers(*stats.gather_history(jira, None, today, weeks, conv), today, weeks, conv)
                _emit(args, conv, {"person": numbers, "me": mine},
                      render.render_load(render.head("Carga", owner, today, None, project), owner, numbers,
                                         "vos" if mine else None, mine))
        return OK
    except (people.NotResolved, window.BadWindow, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return FINDINGS


def main(argv: Optional[List[str]] = None, client: Callable = _client,
         today: Optional[Callable[[], _dt.date]] = None, confirm: Callable = guard.confirm) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) > 1 and argv[0] == "board" and argv[1] in board_cli.VERBS:  # `jtk board EPIC` stays the local kanban
        here = Path(".").resolve()
        return board_cli.run(argv[1:], lambda: client(here) if client is not _client else _client(here, command="board"))
    if argv and argv[0] == "team":  # unlike `board`, no legacy command shares the name: argparse names a bad verb
        here = Path(".").resolve()
        team_conv = config.load_conventions(here)
        make = lambda: client(here) if client is not _client else _client(here, command="team")  # noqa: E731
        return team_cli.run(argv[1:], make, team_conv,
                            today or (lambda: window.today_in(team_conv.get("timezone"))))
    if argv and argv[0] in ("plan", "apply"):  # the guarded writes; the global log is their record, so no per-project journal
        here = Path(".").resolve()
        plan_conv = config.load_conventions(here)
        make = lambda: client(here) if client is not _client else _client(here, command=None)  # noqa: E731
        if argv[0] == "apply":
            return plan_cli.run_apply(argv[1:], make, confirm)
        return plan_cli.run_plan(argv[1:], make, plan_conv,
                                 today or (lambda: window.today_in(plan_conv.get("timezone"))))
    parser = argparse.ArgumentParser(prog="jtk", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("create", "pull", "push", "show", "board"):
        p = sub.add_parser(name)
        p.add_argument("--project", default=".", help="project root that holds ./.jira-kanban (default: cwd)")
        if name == "create":
            p.add_argument("--spec", required=True, help="epic spec JSON (see SKILL.md)")
            p.add_argument("--html", help="also write a standalone, navigable HTML preview to this path")
            p.add_argument("--jira-project", help="Jira project key for the new epic (no default: ask the user)")
        else:
            p.add_argument("epic", help="epic key, e.g. PLATE-504")
        if name in ("create", "push"):
            p.add_argument("--apply", action="store_true", help="write to Jira (default: dry run)")
            group = p.add_mutually_exclusive_group()
            group.add_argument("--assign-open", dest="assign_open", action="store_true", default=None,
                               help="also assign to me the issues that are not complete locally")
            group.add_argument("--no-assign-open", dest="assign_open", action="store_false",
                               help="leave unassigned the issues that are not complete locally")
    who = sub.add_parser("who", help="find a person in Jira by name, email or account id (read only)")
    who.add_argument("name", help="a name (accents and small typos are fine), an email or an accountId")
    who.add_argument("--project", default=".", help="project root that holds ./.jira-kanban (default: cwd)")
    who.add_argument("--jira-project", help="only people assignable in this Jira project, e.g. PLATE")
    who.add_argument("--json", action="store_true", help="machine-readable output")
    give = sub.add_parser("assign", help="assign an issue (and with --tree everything under it) to a person")
    give.add_argument("key", help="issue key, e.g. PLATE-639")
    give.add_argument("who", help="the person: a name, email or accountId (run jtk who first if unsure)")
    give.add_argument("--tree", action="store_true", help="also assign every issue under it")
    give.add_argument("--project", default=".", help="project root that holds ./.jira-kanban (default: cwd)")
    give.add_argument("--apply", action="store_true", help="write to Jira (default: dry run)")
    for name, text in (("done", "what you (or --person) moved to In Progress or Done in a period"),
                       ("next", "what you can do now: open work by priority, what is due, what is unowned in your epics"),
                       ("blocked", "what is blocked: by link, by flag or by a blocked status"),
                       ("load", "how loaded a person is, in measured numbers (compared with you when --person is given)"),
                       ("stats", "delivery metrics: throughput, lead time, WIP age, on-time rate, mix (no estimates)")):
        r = sub.add_parser(name, help=text + " (read only)")
        r.add_argument("--person", help="a teammate: name, email or accountId (default: you)")
        r.add_argument("--jira-project", help="only this Jira project, e.g. PLATE")
        r.add_argument("--project", default=".", help="project root that holds ./.jira-kanban (default: cwd)")
        r.add_argument("--json", action="store_true", help="machine-readable output")
        if name in ("done", "next", "blocked"):
            r.add_argument("--view", help="only the boards of this saved view (see jtk team setup)")
        if name == "done":
            r.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
            r.add_argument("--until", help="last day, YYYY-MM-DD (default: today)")
        if name == "next":
            r.add_argument("--until", help="last day of the window, YYYY-MM-DD (default: today)")
        if name in ("load", "stats"):
            r.add_argument("--weeks", type=int, default=4, help="how many weeks of history, 1 to 52 (default: 4)")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()
    conv = config.load_conventions(project)
    if getattr(args, "jira_project", None):
        conv["project"] = args.jira_project
    if getattr(args, "view", None):
        if getattr(args, "jira_project", None):
            parser.error("--view and --jira-project cannot be used together")
        try:
            conv["project"] = views.load(args.view)["boards"]
        except views.BadView as exc:
            sys.stderr.write(f"jtk: {exc}\n")
            return FINDINGS
    try:
        if args.cmd == "show":
            _show(project, args.epic)
            return OK
        if args.cmd == "board":
            result = sync.board(project, args.epic, conv)
            labels = {"blocked": "Bloqueado", "todo": "Por hacer", "in_progress": "En progreso", "done": "Hecho"}
            print(f"{result['epic']}: {result['total']} issues")
            for group in result["groups"]:
                detail = ", ".join(f"{status} {n}" for status, n in sorted(group["statuses"].items()))
                pct = f" · {result['done_pct']}%" if group["name"] == "done" else ""
                print(f"  {labels[group['name']]} {group['count']}{pct}" + (f"  ({detail})" if detail else ""))
            return OK
        jira = client(project) if client is not _client else _client(project, command=args.cmd)
        if args.cmd == "who":
            return _who(jira, args.name, conv.get("project"), args.json)
        if args.cmd == "assign":
            return _assign(jira, args.key, args.who, args.tree, args.apply, confirm, argv)
        if args.cmd in REPORTS:
            return _report(jira, args, conv, (today or (lambda: window.today_in(conv.get("timezone"))))())
        if args.cmd == "create":
            epic_spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            try:
                if args.apply:  # a silent dry run says how many issues the person is about to approve
                    planned = sync.create(jira, project, epic_spec, conv, apply=False, assign_open=args.assign_open)["ops"]
                    text = f"create {len(planned)} issue(s) in {conv['project']}"
                    rows = [(op.get("ref", ""), op.get("summary", ""), "create") for op in planned]
                    code = _approve(confirm, len(planned), approval.Summary(text, f"Crear en {conv['project']}", rows), argv)
                    if code is not None:
                        return code
                result = sync.create(jira, project, epic_spec, conv, apply=args.apply, assign_open=args.assign_open)
            except (ValueError, sync.NeedsDecision, sync.PartialCreate) as exc:
                sys.stderr.write(f"{exc}\n")
                return FINDINGS
            for op in result["ops"]:
                indent = {"epic": "", "story": "  ", "task": "  ", "subtask": "    "}[op["kind"]]
                key = result.get("keys", {}).get(op["ref"], "")
                who = (op["person"]["name"] + ("" if op["person"].get("exact", True) else " · approximate match")
                       if op["assignee"] == "person" else
                       {"me-done": "vos · completa", "me-started": "vos · en curso", "me": "vos", "none": "sin asignar", "ask": "¿asignar? a decidir"}[op["assignee"]])
                print(f"{indent}{key + ' ' if key else ''}[{conv['issue_types'][op['kind']]}] {op['summary']}  ({who})")
            if args.html:
                Path(args.html).write_text(preview.render(result["ops"], conv), encoding="utf-8")
                print(f"preview: {Path(args.html).resolve()}")
            if not args.apply:
                print(f"dry run: nothing created; --apply creates {len(result['ops'])} issues in {conv['project']}")
            else:
                print(f"created {result['epic']}; local kanban in .jira-kanban/{result['epic']}/")
            errors = result.get("errors") or []
            for error in errors:
                sys.stderr.write(f"{error['key']}: not moved to {error['to']} ({error['reason']})\n")
            if errors:
                sys.stderr.write(f"Every issue was created; do not run create again. Set the status in the issue's .md and "
                                 f"run jtk push {result['epic']} (dry run), then with --apply.\n")
                return FINDINGS
            return OK
        if args.cmd == "pull":
            result = sync.pull(jira, project, args.epic, conv)
            print(f"{result['epic']}: {result['issues']} issues -> {result['dir']}")
            return OK
        try:
            if args.apply:
                planned = sync.push(jira, project, args.epic, apply=False, conv=conv, assign_open=args.assign_open)
                n = len(planned["changes"]) + len(planned["new"])
                rows = [(c["key"], "", f"{c['field']}: {_short(c['from'])} -> {_short(c['to'])}") for c in planned["changes"]]
                rows += [(n_["path"], n_["summary"], "create") for n_ in planned["new"]]
                code = _approve(confirm, n, approval.Summary(f"push {n} write(s) to {args.epic}", f"Subir cambios a {args.epic}", rows), argv)
                if code is not None:
                    return code
            result = sync.push(jira, project, args.epic, apply=args.apply, conv=conv, assign_open=args.assign_open)
        except sync.NeedsDecision as exc:
            sys.stderr.write(f"{exc}\n")
            return FINDINGS
        for c in result["changes"]:
            before, after = excerpt(c["from"], c["to"])
            print(f"{c['key']} {c['field']}: {before} -> {after}")
        for n in result["new"]:
            print(f"new {n['kind']} under {n['parent']}: {n['summary']}")
        for c in result["conflicts"]:
            print(f"conflict {c['key']} {c['field']}: changed locally and in Jira; pull, reapply the local edit, push")
        for i in result["invalid"]:
            print(f"invalid {i['key']} {i['field']}: {i['problem']} (see templates/description.md)")
        for e in result["errors"]:
            print(f"error: {e}")
        if not args.apply:
            print("dry run: nothing written; --apply sends these to Jira")
        else:
            rejected = len(result["errors"])
            print(f"pushed: {len(result['changes']) - rejected} written, {rejected} rejected, "
                  f"{len(result['new'])} created, {len(result['conflicts'])} conflicts"
                  + (f", {len(result['invalid'])} invalid" if result["invalid"] else ""))
        return FINDINGS if result["conflicts"] or result["errors"] or result["invalid"] else OK
    except (JiraError, OSError, KeyError) as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return CANNOT
