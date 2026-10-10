from __future__ import annotations

import contextlib
import functools
import io
import json
import re
import unittest

import plan_fixtures as pf
import team_fixtures as fx
from helpers import FakeJira, config_dir, state_dir
from jkan import board_profile, cli, guard, state, views


class NoTerminal:
    def isatty(self):
        return False


def run(args, jira, confirm=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args, client=lambda project: jira, today=lambda: fx.TODAY, confirm=confirm or approve)
    return code, out.getvalue(), err.getvalue()


def approve(n, summary, command):
    return None


def plan_id(out):
    return re.search(r"jk apply ([0-9a-f]{12})", out).group(1)


class Base(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.config = config_dir()
        for prof in fx.profiles().values():
            board_profile.save(prof)
        views.save(fx.view())
        self.jira = FakeJira()
        pf.workflow(self.jira)
        self.issues = {}

    def put(self, key, role, assignee=None, **over):
        self.issues[key] = pf.put(self.jira, key, role, assignee, **over)
        return self.issues[key]

    def serve(self, open_=()):
        known = dict(self.issues)

        def answer(jql):
            if "key in (" in jql:
                wanted = jql.split("key in (", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
                return [known[k] for k in wanted if k in known]
            return list(open_)
        self.jira.search_answer = answer


class PlanTest(Base):
    def test_planning_a_move_saves_a_file_prints_the_summary_and_writes_nothing(self):
        self.put("TEAM-1", "todo")
        self.serve()
        code, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("TEAM-1: Backlog -> En curso", out)
        self.assertIn("Nothing was written to Jira", out)
        saved = state.load_plan(plan_id(out))
        self.assertEqual((saved["kind"], saved["view"], saved["items"][0]["transition"]), ("move", "plataforma", "1>2"))
        self.assertEqual(self.jira.writes, [])

    def test_the_filters_pick_the_open_issues_of_the_view(self):
        a = self.put("TEAM-1", "todo", created="2026-09-01")
        b = self.put("TEAM-2", "todo", fx.ANA)
        self.serve(open_=[a, b])
        code, out, _ = run(["plan", "assign", "plataforma", "--unassigned", "--person", "Ana Gómez"], self.jira)
        self.assertEqual(code, 0)
        saved = state.load_plan(plan_id(out))
        self.assertEqual([i["key"] for i in saved["items"]], ["TEAM-1"])
        self.assertEqual(saved["options"]["person"]["id"], "acc-ana")

    def test_a_comment_plan(self):
        self.put("TEAM-1", "todo")
        self.serve()
        code, out, _ = run(["plan", "comment", "plataforma", "TEAM-1", "--text", "hola equipo"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(state.load_plan(plan_id(out))["options"]["text"], "hola equipo")

    def test_an_ambiguous_person_is_never_guessed_and_nothing_is_saved(self):
        self.put("TEAM-1", "todo")
        self.serve()
        code, _, err = run(["plan", "assign", "plataforma", "TEAM-1", "--person", "Martin"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)
        self.assertFalse((self.base / "plans").exists())

    def test_refusals_exit_1_with_the_reason_and_save_nothing(self):
        self.put("TEAM-1", "todo")
        self.serve()
        cases = [(["plan", "move", "plataforma", "TEAM-1", "--to", "delivered"], "--allow-close"),
                 (["plan", "move", "plataforma", "OTHER-1", "--to", "active"], "not in the boards"),
                 (["plan", "move", "plataforma", "--to", "active"], "say which issues"),
                 (["plan", "comment", "plataforma", "TEAM-1", "--text", " "], "the comment is empty"),
                 (["plan", "move", "plataforma", "TEAM-1", "--to", "active", "--max", "500"], "--max"),
                 (["plan", "move", "nope", "TEAM-1", "--to", "active"], "nope")]
        for args, text in cases:
            code, _, err = run(args, self.jira)
            self.assertEqual(code, 1, args)
            self.assertIn(text, err)
        self.assertFalse((self.base / "plans").exists())

    def test_a_key_that_carries_jql_is_refused_before_jira_is_asked(self):
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1) OR project = X", "--to", "active"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("is not an issue key", err)
        self.assertEqual(self.jira.jqls, [])

    def test_a_board_without_profile_or_with_undecided_statuses_is_refused(self):
        self.put("TEAM-1", "todo")
        self.serve()
        board_profile.save(fx.profile("TEAM", decide_waiting=False))
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("without a role", err)
        (self.config / "profiles" / "DESK.json").unlink()
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no profile for DESK", err)

    def test_a_search_that_hit_its_cap_refuses_to_plan_from_filters(self):
        self.jira.search_answer = lambda jql: [fx.at(f"TEAM-{n}", "todo", assignee=None) for n in range(1, 1002)]
        code, _, err = run(["plan", "assign", "plataforma", "--unassigned", "--person", "Ana Gómez", "--max", "200"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("cap", err)

    def test_a_state_folder_that_cannot_be_written_is_exit_2(self):
        self.put("TEAM-1", "todo")
        self.serve()
        (self.base / "plans").write_text("a file where the folder should be", encoding="utf-8")
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())

    def test_filters_are_the_same_ones_as_list_and_a_bad_role_is_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["plan", "move", "plataforma", "TEAM-1", "--to", "active", "--role", "delivered"], self.jira)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["plan", "move", "plataforma", "TEAM-1", "--to", "nope"], self.jira)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["plan", "explode", "plataforma"], self.jira)


class ApplyTest(Base):
    def planned(self, key="TEAM-1"):
        self.put(key, "todo")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", key, "--to", "active"], self.jira)
        return plan_id(out)

    def test_applying_with_an_approval_writes_and_prints_the_table(self):
        pid = self.planned()
        code, out, _ = run(["apply", pid], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("TEAM-1  applied", out)
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2")])

    def test_without_approval_it_exits_3_and_writes_nothing(self):
        pid = self.planned()

        def refuse(n, summary, command):
            raise guard.NotApproved("not approved; nothing was written.")

        code, _, err = run(["apply", pid], self.jira, confirm=refuse)
        self.assertEqual((code, self.jira.writes), (3, []))
        self.assertIn("nothing was written", err)

    def test_under_the_real_guard_without_a_terminal_it_prints_the_command_and_exits_3(self):
        pid = self.planned()
        real = functools.partial(guard.confirm, streams=(NoTerminal(),) * 3)
        code, _, err = run(["apply", pid], self.jira, confirm=real)
        self.assertEqual((code, self.jira.writes), (3, []))
        self.assertIn(f"  jk apply {pid}", err)

    def test_an_unknown_edited_or_malformed_plan_is_exit_1(self):
        pid = self.planned()
        for bad in ("0" * 12, "../x", "ZZZ"):
            code, _, err = run(["apply", bad], self.jira)
            self.assertEqual(code, 1, bad)
            self.assertTrue(err.strip())
        path = state.plan_path(pid)
        edited = json.loads(path.read_text(encoding="utf-8"))
        edited["items"][0]["key"] = "TEAM-99"
        path.write_text(json.dumps(edited), encoding="utf-8")
        code, _, err = run(["apply", pid], self.jira)
        self.assertEqual((code, self.jira.writes), (1, []))
        self.assertIn("changed after it was planned", err)

    def test_a_plan_of_a_view_that_no_longer_exists_is_refused(self):
        pid = self.planned()
        (self.config / "views" / "plataforma.json").unlink()
        code, _, err = run(["apply", pid], self.jira)
        self.assertEqual((code, self.jira.writes), (1, []))
        self.assertIn("plataforma", err)

    def test_one_changed_issue_makes_the_exit_code_1(self):
        pid = self.planned()
        self.jira.board["TEAM-1"].update(status_id="3", status="Blocked")
        code, out, _ = run(["apply", pid], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("TEAM-1  changed", out)

    def test_apply_takes_exactly_one_id_and_nothing_else(self):
        for args in (["apply"], ["apply", "a" * 12, "--yes"], ["apply", "a" * 12, "b" * 12]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run(args, self.jira)

    def test_a_profile_that_lost_its_roles_after_planning_is_refused_before_asking(self):
        pid = self.planned()
        board_profile.save(fx.profile("TEAM", decide_waiting=False))
        asked = []
        code, _, err = run(["apply", pid], self.jira, confirm=lambda n, s, c: asked.append(n))
        self.assertEqual((code, asked, self.jira.writes), (1, [], []))
        self.assertIn("without a role", err)

    def test_a_plan_whose_board_has_no_profile_any_more_is_refused_not_a_crash(self):
        pid = self.planned()  # TEAM-1, and TEAM stays in the view
        (self.config / "profiles" / "TEAM.json").unlink()
        asked = []
        code, _, err = run(["apply", pid], self.jira, confirm=lambda n, s, c: asked.append(n))
        self.assertEqual((code, asked, self.jira.writes), (1, [], []))
        self.assertIn("no profile for TEAM", err)

    def test_a_plan_whose_board_left_the_view_is_refused_even_if_its_profile_is_still_there(self):
        pid = self.planned()  # TEAM-1
        views.save(fx.view(boards=("DESK",)))
        asked = []
        code, _, err = run(["apply", pid], self.jira, confirm=lambda n, s, c: asked.append(n))
        self.assertEqual((code, asked, self.jira.writes), (1, [], []))
        self.assertIn("TEAM-1 is not in the boards of view 'plataforma'", err)

    def test_a_read_only_command_never_needs_the_guard(self):
        code, _, _ = run(["team", "list"], self.jira)
        self.assertEqual(code, 0)


class RevertCliTest(Base):
    def test_revert_plans_the_inverse_of_an_applied_plan_and_it_needs_its_own_approval(self):
        self.put("TEAM-1", "todo")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        first = plan_id(out)
        run(["apply", first], self.jira)
        self.jira.writes.clear()
        code, out, _ = run(["plan", "revert", first], self.jira)
        self.assertEqual(code, 0)
        second = plan_id(out)
        self.assertNotEqual(first, second)
        self.assertIn("TEAM-1: En curso -> Backlog", out)
        self.assertEqual(self.jira.writes, [])
        asked = []
        run(["apply", second], self.jira, confirm=lambda n, s, c: asked.append((n, c)))
        self.assertEqual(asked, [(1, f"jk apply {second}")])
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "2>1")])

    def test_reverting_a_plan_that_does_not_exist_or_wrote_nothing_is_refused(self):
        code, _, err = run(["plan", "revert", "0" * 12], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no plan", err)
        self.put("TEAM-1", "todo")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        code, _, err = run(["plan", "revert", plan_id(out)], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("wrote nothing", err)


class RevertClosingCliTest(Base):
    def test_a_revert_that_closes_needs_the_flag_on_the_command_line(self):
        self.put("TEAM-1", "delivered")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        first = plan_id(out)
        run(["apply", first], self.jira)
        code, _, err = run(["plan", "revert", first], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("add --allow-close", err)
        code, out, _ = run(["plan", "revert", first, "--allow-close"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("TEAM-1: En curso -> Done", out)
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "5>2")])  # only the first apply wrote; planning the revert did not


if __name__ == "__main__":
    unittest.main()
