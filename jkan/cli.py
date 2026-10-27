"""jtk: create [--check] | pull | push | show | board | who | assign | attach | done | next | blocked | load | stats | board setup|set|show|check|survey | team … | plan … | apply | update [--check]. Every Jira write is a dry run unless --apply is passed; the reports only read."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Callable, List, Optional

from . import (approval, attach, board_cli, board_profile, check, config, facts, guard, journal, kanban, people, plan_cli, preview, render, roles, standup,
               state, stats, sync, team_cli, update, views, window)
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
        raise SystemExit("jtk: Jira credentials not found (set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN in the "
                         "environment, ./.env.local or ./.spec-kit/.env)")
    return Jira(*creds, journal=journal.journal(project, command, also=state.log_write) if command else None)


def _show(project: Path, key: str) -> None:
    epic = kanban.epic_dir(project, key)
    if not (epic / "epic.md").is_file():
        print(f"no local kanban for {key}: run jtk pull {key}")
        return
    rows = [("Issue", "Tipo", "Estado", "Título")]
    for entry in sync._local(epic, key):
        depth = {"epic": 0, "story": 1, "task": 1, "subtask": 2}[entry["kind"]]
        label = entry["key"] or entry["path"].parent.name
        rows.append(("  " * depth + label, entry["kind"], entry["status"] or "new", entry["summary"]))
    print("\n".join(render.columns(rows)))


def _who(jira, name: str, project: Optional[str], as_json: bool) -> int:
    result = people.find(jira, name, project)
    if as_json:
        print(render.dump(result))
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
            code = _approve(confirm, len(pending), approval.Summary(text, f"Asignar a {person['name']}", rows, badges=[(approval.plural(len(pending), "issue", "issues"), "")], links=[jira.browse_url(i["key"]) for i in pending]), argv)
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


def _attach(jira, project: Path, conv: dict, key: str, files: List[str], sanitize_on: bool, apply: bool,
            confirm: Callable, argv: List[str]) -> int:
    missing = [f for f in files if not Path(f).is_file()]
    if missing:
        sys.stderr.write("jtk: not a file: " + ", ".join(missing) + "\n")
        return CANNOT
    creds = config.credentials(project)
    secrets = [creds[2]] if creds else []
    try:
        uploads = [attach.prepare(Path(f), sanitize_on, secrets) for f in files]
    except ValueError as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return FINDINGS
    limit = jira.attachment_limit()
    too_big = [u for u in uploads if limit and len(u.data) > limit]
    if too_big:
        sys.stderr.write("jtk: over Jira's upload limit of " + attach.human_size(limit) + ": "
                         + ", ".join(f"{u.name} ({attach.human_size(len(u.data))})" for u in too_big) + "\n")
        return FINDINGS
    issue = jira.attachments(key)
    send, already = attach.split_duplicates(uploads, issue["attachments"])
    kinds = {name: kind for kind, name in (conv.get("issue_types") or {}).items()}
    lines = [f"{key} [{issue['issuetype']}] {issue['summary']}"]
    for upload in send:
        lines.append(f"  {upload.name}\n" + "\n".join("    " + line for line in attach.change(upload).splitlines()))
    for upload in already:
        lines.append(f"  {upload.name}: already attached (same name and size); left out")
    print("\n".join(lines))
    if not send:
        print(f"nothing to upload: every file is already attached to {key}")
        return OK
    if not apply:
        print(f"dry run: nothing written; --apply uploads {len(send)} file(s) to {key}")
        return OK
    rows = [(key, u.name, attach.change(u)) for u in send]
    left_out = [(u.name, f"ya adjunto en {key} (mismo nombre y tamaño)") for u in already]
    heading = f"Subir {approval.plural(len(send), 'adjunto', 'adjuntos')} a {key}"
    summary = approval.Summary("\n".join([f"upload {len(send)} attachment(s) to {key}", *lines[1:]]), heading, rows,
                               left_out, kinds=[kinds.get(issue["issuetype"], "")] * len(send),
                               links=[jira.browse_url(key)] * len(send))
    code = _approve(confirm, len(send), summary, argv)
    if code is not None:
        return code
    failed = 0
    for upload in send:
        try:
            jira.attach(key, upload.name, upload.data,
                        record={"sanitized": upload.sanitized, "redactions": dict(upload.redactions)})
        except JiraError as exc:
            failed += 1
            sys.stderr.write(f"jtk: {upload.name}: {exc}\n")
    print(f"uploaded {len(send) - failed} file(s) to {key}")
    return FINDINGS if failed else OK


def _create_rows(planned: List[dict], conv: dict, mine: str):
    """The approval's rows for a create: what moves shows only its destination pill («-> Done»); who gets the issues
    goes once as a badge when it is the same person for all, else on each row."""
    owners = {facts.assignee(op, mine) for op in planned}
    badges = [(approval.plural(len(planned), "issue", "issues"), "")]
    if len(owners) == 1:
        badges.append((f"asignado a {next(iter(owners))}", ""))
    rows = []
    for op in planned:
        moves = op.get("done") or op.get("started")
        if len(owners) == 1:
            change = f"-> {facts.status(op, conv)}" if moves else ""
        else:
            change = (f"Estado: {facts.status(op, conv)}\n" if moves else "") + f"Asignado a: {facts.assignee(op, mine)}"
        rows.append((conv["issue_types"][op["kind"]], op["summary"], change))
    return rows, badges


REPORTS = ("done", "next", "blocked", "load", "stats")


def _emit(args, conv: dict, payload, text: str) -> None:
    """Print a report, led by what the reader must know about the profiles it was computed with."""
    notes = roles.notes(conv.get("_seen", []), conv.get("profiles") or {}, conv.get("profile_problems"))
    if args.json:
        print(render.dump({**payload, "profile_notes": notes}))
    else:
        print("\n".join(f"> ⚠ {n}" for n in notes) + "\n\n" + text if notes else text)


def _report(jira, args, conv: dict, today: _dt.date) -> int:
    """done | next | blocked | load | stats: read only, for the user or, with --person, for a teammate."""
    conv["profiles"], conv["profile_problems"] = board_profile.scan()
    conv["_seen"] = []
    try:
        if args.cmd == "done":  # the window is checked before Jira is asked anything, even who the person is
            since, until = window.resolve(args.since, args.until, args.when, today)
        elif args.cmd == "next":
            until = window.horizon_for(args.until, args.when, today)
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
                result = stats.compute(done, open_issues, today, weeks, conv, by=args.by)
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
    if argv == ["--version"]:
        print(f"jtk {update.version(update.root())}")
        return OK
    if argv and argv[0] == "update":  # about the install, not Jira: no credentials, no project
        return update.run(argv[1:])
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
        p.add_argument("--project", default=".", help="project root that holds ./.jira-team-kit (default: cwd)")
        if name == "create":
            p.add_argument("--spec", help="epic spec JSON (see SKILL.md); not with --check")
            p.add_argument("--check", action="store_true",
                           help="before drafting: is there a wow plan, which Jira project applies, does an epic already exist (offline)")
            p.add_argument("--html", help="also write a standalone, navigable HTML preview to this path")
            p.add_argument("--jira-project", help="Jira project key for the new epic (no default: ask the user)")
            p.add_argument("--epic", help="put the spec's items under this existing epic (e.g. PLATE-504) instead of "
                                          "creating one; the spec then has no \"epic\" and the epic is only read")
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
    who.add_argument("--project", default=".", help="project root that holds ./.jira-team-kit (default: cwd)")
    who.add_argument("--jira-project", help="only people assignable in this Jira project, e.g. PLATE")
    who.add_argument("--json", action="store_true", help="machine-readable output")
    give = sub.add_parser("assign", help="assign an issue (and with --tree everything under it) to a person")
    give.add_argument("key", help="issue key, e.g. PLATE-639")
    give.add_argument("who", help="the person: a name, email or accountId (run jtk who first if unsure)")
    give.add_argument("--tree", action="store_true", help="also assign every issue under it")
    give.add_argument("--project", default=".", help="project root that holds ./.jira-team-kit (default: cwd)")
    give.add_argument("--apply", action="store_true", help="write to Jira (default: dry run)")
    att = sub.add_parser("attach", help="upload files as attachments to an issue (sanitized unless --no-sanitize)")
    att.add_argument("key", help="issue key: an epic, story, task or subtask, e.g. PLATE-706")
    att.add_argument("files", nargs="+", help="files to upload")
    att.add_argument("--no-sanitize", dest="sanitize", action="store_false",
                     help="upload the files as they are; required for anything that is not UTF-8 text")
    att.add_argument("--project", default=".", help="project root that holds ./.jira-team-kit (default: cwd)")
    att.add_argument("--apply", action="store_true", help="write to Jira (default: dry run)")
    for name, text in (("done", "what you (or --person) moved to In Progress or Done in a period"),
                       ("next", "what you can do now: open work by priority, what is due, what is unowned in your epics"),
                       ("blocked", "what is blocked: by link, by flag or by a blocked status"),
                       ("load", "how loaded a person is, in measured numbers (compared with you when --person is given)"),
                       ("stats", "delivery metrics: throughput, lead time, WIP age, on-time rate, mix (no estimates)")):
        r = sub.add_parser(name, help=text + " (read only)")
        r.add_argument("--person", help="a teammate: name, email or accountId (default: you)")
        r.add_argument("--jira-project", help="only this Jira project, e.g. PLATE")
        r.add_argument("--project", default=".", help="project root that holds ./.jira-team-kit (default: cwd)")
        r.add_argument("--json", action="store_true", help="machine-readable output")
        if name in ("done", "next", "blocked"):
            r.add_argument("--view", help="only the boards of this saved view (see jtk team setup)")
        if name == "done":
            r.add_argument("--since", help="first day, YYYY-MM-DD (or use --when)")
            r.add_argument("--until", help="last day, YYYY-MM-DD (default: today)")
            r.add_argument("--when", help="a named window instead of dates: " + ", ".join(window.PAST))
        if name == "next":
            r.add_argument("--until", help="last day of the window, YYYY-MM-DD (default: today)")
            r.add_argument("--when", help="a named horizon instead of --until: " + ", ".join(window.AHEAD))
        if name == "stats":
            r.add_argument("--by", choices=("label", "component"), help="also count closed and open work per label or per component")
        if name in ("load", "stats"):
            r.add_argument("--weeks", type=int, default=4, help="how many weeks of history, 1 to 52 (default: 4)")
    args = parser.parse_args(argv)
    if args.cmd == "create" and bool(args.check) == bool(args.spec):
        parser.error("create needs --spec to create, or --check alone to look before drafting")
    project = Path(args.project).resolve()
    conv = config.load_conventions(project)
    if getattr(args, "jira_project", None):
        conv["project"] = args.jira_project
    elif getattr(args, "epic", None) and isinstance(args.epic, str) and args.cmd == "create":
        conv["project"] = args.epic.rsplit("-", 1)[0]  # the epic's own project; read_epic still checks the key
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
        if args.cmd == "create" and args.check:  # offline: no credentials, no Jira
            print("\n".join(render.columns([("Check", "Result", "Detail"), *check.preflight(project, conv, flag=args.jira_project)])))
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
        if args.cmd == "attach":
            return _attach(jira, project, conv, args.key, args.files, args.sanitize, args.apply, confirm, argv)
        if args.cmd in REPORTS:
            return _report(jira, args, conv, (today or (lambda: window.today_in(conv.get("timezone"))))())
        if args.cmd == "create":
            epic_spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            try:
                if args.apply:  # a silent dry run says how many issues the person is about to approve
                    planned = sync.create(jira, project, epic_spec, conv, apply=False, assign_open=args.assign_open,
                                          epic_key=args.epic)["ops"]
                    planned = [op for op in planned if not op.get("existing")]  # the window lists only what is written
                    moves = sum(1 for op in planned if op.get("done") or op.get("started"))
                    under = f" under {args.epic}" if args.epic else ""
                    text = f"create {len(planned)} issue(s) in {conv['project']}{under}" + (f" and move {moves} of them to Done or in progress" if moves else "")
                    mine = ""
                    if any(op["assignee"].startswith("me") for op in planned):
                        mine = (jira.user(jira.myself()) or {}).get("name") or "vos"
                    rows, badges = _create_rows(planned, conv, mine)
                    code = _approve(confirm, len(planned), approval.Summary(text, f"Crear en {args.epic or conv['project']}", rows, kinds=[op["kind"] for op in planned], transitions=moves, badges=badges), argv)
                    if code is not None:
                        return code
                result = sync.create(jira, project, epic_spec, conv, apply=args.apply, assign_open=args.assign_open,
                                     epic_key=args.epic)
            except (ValueError, sync.NeedsDecision, sync.PartialCreate) as exc:
                sys.stderr.write(f"{exc}\n")
                return FINDINGS
            rows = [("Issue", "Tipo", "Estado", "Asignado", "Título")]
            names = facts.names(result["ops"])
            for op in result["ops"]:
                indent = {"epic": "", "story": "  ", "task": "  ", "subtask": "    "}[op["kind"]]
                key = result.get("keys", {}).get(op["ref"], "")
                rows.append((indent + (key or names[op["ref"]]), conv["issue_types"][op["kind"]], facts.status(op, conv),
                             facts.assignee(op), op["summary"]))
            print("\n".join(render.columns(rows)))
            if args.html:
                Path(args.html).write_text(preview.render(result["ops"], conv), encoding="utf-8")
                print(f"preview: {Path(args.html).resolve()}")
            new = [op for op in result["ops"] if not op.get("existing")]
            if not args.apply:
                under = f" under {args.epic}" if args.epic else ""
                print(f"dry run: nothing created; --apply creates {len(new)} issues in {conv['project']}{under}")
            elif args.epic:
                print(f"added {len(new)} issue(s) to {result['epic']}; local kanban in .jira-team-kit/{result['epic']}/")
            else:
                print(f"created {result['epic']}; local kanban in .jira-team-kit/{result['epic']}/")
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
                rows = [(c["key"], c.get("title", ""), f"{_short(c['from'])} -> {_short(c['to'])}" if c["field"] == "status"
                         else f"{c['field']}: {_short(c['from'])} -> {_short(c['to'])}") for c in planned["changes"]]
                moves = sum(1 for c in planned["changes"] if c["field"] == "status")
                rows += [(conv["issue_types"][n_["kind"]], n_["summary"], f"Crear bajo {n_['parent']}") for n_ in planned["new"]]
                kinds = [""] * len(planned["changes"]) + [n_["kind"] for n_ in planned["new"]]
                code = _approve(confirm, n, approval.Summary(f"push {n} write(s) to {args.epic}", f"Subir cambios a {args.epic}", rows,
                                                             kinds=kinds, transitions=moves,
                                                             badges=[(approval.plural(n, "cambio", "cambios"), "")],
                                                             links=[jira.browse_url(c["key"]) for c in planned["changes"]]
                                                             + [""] * len(planned["new"])), argv)
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
