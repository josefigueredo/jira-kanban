"""jtk plan move|assign|comment|revert and jtk apply: guarded writes to Jira. A plan only reads Jira and saves a file; apply
runs that file exactly, after a person at a terminal approved it (guard.py).

Exit codes: 0 done, 1 refused or something changed or failed, 2 could not (Jira, disk, log), 3 a person has to do it
(no terminal, or not approved)."""
from __future__ import annotations

import argparse
import sys
from typing import Callable, List

from . import applier, guard, people, plan, roles, state, team, team_cli
from .jira import JiraError

OK, FINDINGS, CANNOT = 0, 1, 2
VERBS = ("move", "assign", "comment", "revert")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jtk plan", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)

    def selecting(p: argparse.ArgumentParser) -> None:
        p.add_argument("view")
        p.add_argument("keys", nargs="*", help="issue keys, e.g. PLATE-12; they must be in the boards of the view")
        p.add_argument("--unassigned", action="store_true", help="select the open issues nobody owns")
        p.add_argument("--older-than", type=int, metavar="DAYS", help="select open issues created DAYS ago or before")
        p.add_argument("--role", choices=team.COUNTED + ("none",), help="select open issues in this role")
        p.add_argument("--max", type=int, help=f"most issues a plan may hold (default {plan.DEFAULT_MAX}, up to {plan.LIMIT_MAX})")

    move = sub.add_parser("move", help="plan moving issues to the status that plays a role (reads Jira, writes a file)")
    selecting(move)
    move.add_argument("--to", required=True, choices=plan.TO_ROLES, help="the role the issues should reach")
    move.add_argument("--to-status", metavar="ID", help="a status id of the profile, when the role has several")
    move.add_argument("--allow-close", action="store_true", help="needed to move to delivered or dropped")
    give = sub.add_parser("assign", help="plan assigning issues to one person (reads Jira, writes a file)")
    selecting(give)
    give.add_argument("--person", required=True, help="a name, email or accountId; never guessed between several")
    note = sub.add_parser("comment", help="plan the same plain-text comment on issues (reads Jira, writes a file)")
    selecting(note)
    note.add_argument("--text", required=True)
    undo = sub.add_parser("revert", help="plan the inverse of an applied plan (it does not guarantee undoing)")
    undo.add_argument("id")
    undo.add_argument("--allow-close", action="store_true", help="needed when the inverse closes issues")
    return parser


def _announce(saved: dict) -> int:
    print(plan.describe(saved))
    print(f"\nPlan {saved['id']} saved in {state.plan_path(saved['id'])}. Nothing was written to Jira.\n"
          f"To apply it, run this in your own terminal (it asks for your approval there):\n  jtk apply {saved['id']}")
    return OK


def _plan(args, jira, conv: dict, today) -> int:
    if args.verb == "revert":
        original = state.load_plan(args.id)
        _, profiles = team_cli.context(original["view"])
        return _announce(state.save_plan(plan.revert(jira(), original, profiles, allow_close=args.allow_close)))
    view, profiles = team_cli.context(args.view)
    limit = plan.check_max(args.max)
    client = jira()
    filtering = args.unassigned or args.older_than is not None or args.role is not None
    open_issues = []
    if filtering:
        open_issues, truncated = team.gather_open(client, view, profiles, conv)
        if truncated:
            raise plan.Refused(f"the search hit the cap of {team.CAP} issues, so the filters would miss some: "
                               f"name the issues by key")
    selection = plan.select(client, view, profiles, conv, open_issues, today, args.keys, args.unassigned,
                            args.older_than, args.role, limit)
    plan.check_profiles(selection, profiles)
    if args.verb == "move":
        body = plan.move(client, view, selection, profiles, args.to, args.to_status, args.allow_close)
    elif args.verb == "assign":
        body = plan.assign(view, selection, people.resolve_in(client, args.person, view["boards"]))
    else:
        body = plan.comment(view, selection, args.text)
    return _announce(state.save_plan(body))


def run_plan(argv: List[str], jira: Callable[[], object], conv: dict, today: Callable) -> int:
    args = _parser().parse_args(argv)
    try:
        return _plan(args, jira, conv, today())
    except ValueError as exc:  # Refused, Refusal, BadPlan, BadView, NotResolved: a decision for the person, not a crash
        sys.stderr.write(f"jtk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return CANNOT


def run_apply(argv: List[str], jira: Callable[[], object], confirm: Callable) -> int:
    parser = argparse.ArgumentParser(prog="jtk apply", description="Run a saved plan after a person approves it.")
    parser.add_argument("id", help="the plan id that jtk plan printed")
    args = parser.parse_args(argv)
    try:
        saved = state.load_plan(args.id)
        view, profiles = team_cli.context(saved["view"])
        outside = [i["key"] for i in saved["items"] if roles.project_of(i["key"]) not in view["boards"]]
        if outside:
            raise plan.Refused(f"{', '.join(outside)} is not in the boards of view {saved['view']!r} "
                               f"({', '.join(view['boards'])}) any more: plan again")
        plan.check_profiles(saved["items"], profiles)
        outcomes, code = applier.run(jira(), saved, confirm, f"jtk apply {saved['id']}")
    except guard.NotApproved as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return guard.EXIT_NEEDS_PERSON
    except ValueError as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jtk: {exc}\n")
        return CANNOT
    print(applier.render(outcomes))
    return code
