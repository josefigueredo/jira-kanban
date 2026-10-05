"""jk: create | pull | push | show | board. Every Jira write is a dry run unless --apply is passed."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional

from . import config, kanban, preview, sync
from .jira import Jira, JiraError

OK, FINDINGS, CANNOT = 0, 1, 2


def _client(project: Path):
    creds = config.credentials(project)
    if creds is None:
        raise SystemExit("jk: Jira credentials not found (IC_JIRA_* or JIRA_* in the environment, ./.env.local, "
                         "./.spec-kit/.env)")
    return Jira(*creds)


def _show(project: Path, key: str) -> None:
    epic = kanban.epic_dir(project, key)
    if not (epic / "epic.md").is_file():
        print(f"no local kanban for {key}: run jk pull {key}")
        return
    for entry in sync._local(epic, key):
        depth = {"epic": 0, "story": 1, "task": 1, "subtask": 2}[entry["kind"]]
        label = entry["key"] or entry["path"].parent.name
        print(f"{'  ' * depth}{label} [{entry['kind']}] {entry['status'] or 'new'} · {entry['summary']}")


def main(argv: Optional[List[str]] = None, client: Callable = _client) -> int:
    parser = argparse.ArgumentParser(prog="jk", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("create", "pull", "push", "show", "board"):
        p = sub.add_parser(name)
        p.add_argument("--project", default=".", help="project root that holds ./.jira-kanban (default: cwd)")
        if name == "create":
            p.add_argument("--spec", required=True, help="epic spec JSON (see SKILL.md)")
            p.add_argument("--html", help="also write a standalone, navigable HTML preview to this path")
        else:
            p.add_argument("epic", help="epic key, e.g. PLATE-504")
        if name in ("create", "push"):
            p.add_argument("--apply", action="store_true", help="write to Jira (default: dry run)")
            group = p.add_mutually_exclusive_group()
            group.add_argument("--assign-open", dest="assign_open", action="store_true", default=None,
                               help="also assign to me the issues that are not complete locally")
            group.add_argument("--no-assign-open", dest="assign_open", action="store_false",
                               help="leave unassigned the issues that are not complete locally")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()
    conv = config.load_conventions(project)
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
        jira = client(project)
        if args.cmd == "create":
            epic_spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            try:
                result = sync.create(jira, project, epic_spec, conv, apply=args.apply, assign_open=args.assign_open)
            except (ValueError, sync.NeedsDecision) as exc:
                sys.stderr.write(f"{exc}\n")
                return FINDINGS
            for op in result["ops"]:
                indent = {"epic": "", "story": "  ", "task": "  ", "subtask": "    "}[op["kind"]]
                key = result.get("keys", {}).get(op["ref"], "")
                who = {"me-done": "vos · completa", "me": "vos", "none": "sin asignar", "ask": "¿asignar? a decidir"}[op["assignee"]]
                print(f"{indent}{key + ' ' if key else ''}[{conv['issue_types'][op['kind']]}] {op['summary']}  ({who})")
            if args.html:
                Path(args.html).write_text(preview.render(result["ops"], conv), encoding="utf-8")
                print(f"preview: {Path(args.html).resolve()}")
            if not args.apply:
                print(f"dry run: nothing created; --apply creates {len(result['ops'])} issues in {conv['project']}")
            else:
                print(f"created {result['epic']}; local kanban in .jira-kanban/{result['epic']}/")
            return OK
        if args.cmd == "pull":
            result = sync.pull(jira, project, args.epic, conv)
            print(f"{result['epic']}: {result['issues']} issues -> {result['dir']}")
            return OK
        try:
            result = sync.push(jira, project, args.epic, apply=args.apply, conv=conv, assign_open=args.assign_open)
        except sync.NeedsDecision as exc:
            sys.stderr.write(f"{exc}\n")
            return FINDINGS
        for c in result["changes"]:
            print(f"{c['key']} {c['field']}: {str(c['from'])[:60]} -> {str(c['to'])[:60]}")
        for n in result["new"]:
            print(f"new {n['kind']} under {n['parent']}: {n['summary']}")
        for c in result["conflicts"]:
            print(f"conflict {c['key']} {c['field']}: changed locally and in Jira; pull, reapply the local edit, push")
        for e in result["errors"]:
            print(f"error: {e}")
        if not args.apply:
            print("dry run: nothing written; --apply sends these to Jira")
        return FINDINGS if result["conflicts"] or result["errors"] else OK
    except (JiraError, OSError, KeyError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT
