from __future__ import annotations

import unittest
from unittest import mock

import plan_fixtures as pf
import team_fixtures as fx
from helpers import FakeJira, state_dir
from jkan import applier, guard, plan, state

NOW = lambda: "2026-10-10T12:00:00Z"  # noqa: E731
ANA = {"id": "acc-ana", "name": "Ana Gómez", "email": "a@x", "score": 1.0, "exact": True}


class Approver:
    """A confirm() that approves and remembers what it was asked."""

    def __init__(self):
        self.calls = []

    def __call__(self, n, summary, command):
        self.calls.append((n, summary, command))


def refuse(n, summary, command):
    raise guard.NotApproved("not approved; nothing was written.")


class Base(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.jira = FakeJira()
        pf.workflow(self.jira)
        self.profiles = fx.profiles()
        self.view = fx.view()
        self.issues = {}
        self.approve = Approver()

    def put(self, key, role, assignee=None):
        self.issues[key] = pf.put(self.jira, key, role, assignee)
        return self.issues[key]

    def saved_move(self, keys, role="active", to="active"):
        selection = [self.put(k, role) for k in keys]
        return state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, to, now=NOW))

    def apply(self, saved, confirm=None):
        return applier.run(self.jira, saved, confirm or self.approve, f"jtk apply {saved['id']}", now=NOW)


class MoveTest(Base):
    def test_it_applies_exactly_the_saved_transition_and_logs_what_changed(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        outcomes, code = self.apply(saved)
        self.assertEqual(code, 0)
        self.assertEqual(outcomes, [{"key": "TEAM-1", "result": "applied"}, {"key": "TEAM-2", "result": "applied"}])
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2"), ("transition_id", "TEAM-2", "1>2")])
        entry = state.entries(saved["id"])[0]
        self.assertEqual((entry["command"], entry["key"], entry["action"], entry["result"]), ("apply", "TEAM-1", "move", "ok"))
        self.assertEqual((entry["de"]["id"], entry["a"]["id"]), ("1", "2"))

    def test_the_person_is_asked_once_with_the_real_count_the_summary_and_the_command(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        self.apply(saved)
        n, summary, command = self.approve.calls[0]
        self.assertEqual((len(self.approve.calls), n, command), (1, 2, f"jtk apply {saved['id']}"))
        self.assertIn("TEAM-1: Backlog -> En curso", summary)

    def test_the_approval_window_gets_a_row_per_pending_change(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        self.apply(saved)
        summary = self.approve.calls[0][1]
        move = "Acción: cambiar de estado\nEstado: Backlog -> En curso"
        self.assertEqual(summary.rows, [("TEAM-1", "Summary of TEAM-1", move), ("TEAM-2", "Summary of TEAM-2", move)])
        self.assertEqual(summary.transitions, 2)

    def test_without_approval_nothing_is_written_and_nothing_is_logged(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        with self.assertRaises(guard.NotApproved):
            self.apply(saved, refuse)
        self.assertEqual(self.jira.writes, [])
        self.assertEqual(state.entries(saved["id"]), [])

    def test_an_issue_somebody_moved_after_planning_is_left_alone(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        self.jira.board["TEAM-1"].update(status_id="3", status="Blocked")
        outcomes, code = self.apply(saved)
        self.assertEqual(outcomes, [{"key": "TEAM-1", "result": "changed"}, {"key": "TEAM-2", "result": "applied"}])
        self.assertEqual(code, 1)
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-2", "1>2")])

    def test_an_issue_already_in_the_destination_is_not_touched_and_is_not_a_failure(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.jira.board["TEAM-1"].update(status_id="2", status="En curso")
        outcomes, code = self.apply(saved)
        self.assertEqual((outcomes, code), ([{"key": "TEAM-1", "result": "already there"}], 0))
        self.assertEqual(self.jira.writes, [])

    def test_a_saved_transition_that_no_longer_reaches_the_planned_status_is_not_used(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.jira.workflow["1"] = [dict(t, to={"id": "5", "name": "Done"}) if t["id"] == "1>2" else t
                                   for t in self.jira.workflow["1"]]  # same id, different destination
        outcomes, code = self.apply(saved)
        self.assertEqual((outcomes, code), ([{"key": "TEAM-1", "result": "changed"}], 1))
        self.assertEqual(self.jira.writes, [])

    def test_a_saved_transition_that_disappeared_is_not_used(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.jira.workflow["1"] = [t for t in self.jira.workflow["1"] if t["id"] != "1>2"]
        self.assertEqual(self.apply(saved)[0], [{"key": "TEAM-1", "result": "changed"}])

    def test_one_failure_does_not_stop_the_others_and_the_code_is_not_zero(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2", "TEAM-3"], role="todo")
        self.jira.fail_writes.add("TEAM-2")
        outcomes, code = self.apply(saved)
        self.assertEqual([o["result"].split(":")[0] for o in outcomes], ["applied", "error", "applied"])
        self.assertEqual(code, 1)
        self.assertEqual(sorted(state.applied(saved["id"])), ["TEAM-1", "TEAM-3"])
        failed = [e for e in state.entries(saved["id"]) if e["key"] == "TEAM-2"][0]
        self.assertTrue(failed["result"].startswith("error: "))


class ReapplyTest(Base):
    def test_reapplying_retries_only_what_failed_and_asks_for_that_count(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2", "TEAM-3"], role="todo")
        self.jira.fail_writes.add("TEAM-2")
        self.apply(saved)
        self.jira.fail_writes.clear()
        self.jira.writes.clear()
        again = Approver()
        outcomes, code = self.apply(saved, again)
        self.assertEqual([(o["key"], o["result"]) for o in outcomes],
                         [("TEAM-1", "already applied"), ("TEAM-2", "applied"), ("TEAM-3", "already applied")])
        self.assertEqual((code, again.calls[0][0]), (0, 1))
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-2", "1>2")])

    def test_a_plan_that_is_fully_applied_asks_nothing_and_writes_nothing(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.apply(saved)
        self.jira.writes.clear()
        again = Approver()
        outcomes, code = self.apply(saved, again)
        self.assertEqual((outcomes, code, again.calls, self.jira.writes),
                         ([{"key": "TEAM-1", "result": "already applied"}], 0, [], []))


class AssignTest(Base):
    def saved(self, owner):
        selection = [self.put("TEAM-1", "todo", owner)]
        return state.save_plan(plan.assign(self.view, selection, ANA, now=NOW))

    def test_it_assigns_and_logs_who_had_it(self):
        saved = self.saved(fx.BETO)
        outcomes, code = self.apply(saved)
        self.assertEqual((outcomes, code), ([{"key": "TEAM-1", "result": "applied"}], 0))
        self.assertEqual(self.jira.writes, [("assign", "TEAM-1", "acc-ana")])
        entry = state.entries(saved["id"])[0]
        self.assertEqual((entry["action"], entry["de"]["id"], entry["a"]["id"]), ("assign", "acc-beto", "acc-ana"))

    def test_somebody_else_took_it_meanwhile(self):
        saved = self.saved(fx.BETO)
        self.jira.board["TEAM-1"]["assignee"] = {"id": "acc-other", "name": "Otra"}
        self.assertEqual(self.apply(saved)[0], [{"key": "TEAM-1", "result": "changed"}])
        self.assertEqual(self.jira.writes, [])

    def test_it_is_already_theirs(self):
        saved = self.saved(None)
        self.jira.board["TEAM-1"]["assignee"] = {"id": "acc-ana", "name": "Ana Gómez"}
        self.assertEqual(self.apply(saved), ([{"key": "TEAM-1", "result": "already there"}], 0))

    def test_a_plan_whose_target_is_nobody_unassigns(self):
        self.put("TEAM-1", "todo", fx.ANA)
        body = {"version": 1, "kind": "assign", "view": "plataforma", "created": NOW(), "options": {"person": None},
                "items": [{"key": "TEAM-1", "from": {"id": "acc-ana", "name": "Ana Gómez"}, "to": None}], "skipped": []}
        self.assertEqual(self.apply(state.save_plan(body))[0], [{"key": "TEAM-1", "result": "applied"}])
        self.assertEqual(self.jira.writes, [("assign", "TEAM-1", None)])


class CommentTest(Base):
    def test_a_comment_is_posted_once_even_if_the_plan_is_applied_again(self):
        selection = [self.put("TEAM-1", "todo"), self.put("TEAM-2", "todo")]
        saved = state.save_plan(plan.comment(self.view, selection, "hola", now=NOW))
        self.apply(saved)
        self.apply(saved)
        self.assertEqual(self.jira.writes, [("comment", "TEAM-1", "hola"), ("comment", "TEAM-2", "hola")])
        self.assertNotIn("de", state.entries(saved["id"])[0])


class LogTest(Base):
    def test_a_log_that_cannot_be_written_is_exit_2_not_a_silent_success(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        with mock.patch.object(state, "log_write", return_value=False):
            outcomes, code = self.apply(saved)
        self.assertEqual(code, 2)
        self.assertIn("not recorded", outcomes[0]["result"])
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2")])

    def test_a_log_that_cannot_be_opened_is_found_out_before_the_person_is_asked_and_before_any_write(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        asked = Approver()
        with mock.patch.object(state, "can_log", return_value=False):
            outcomes, code = self.apply(saved, asked)
        self.assertEqual((code, asked.calls, self.jira.writes), (2, [], []))
        self.assertIn("log", outcomes[0]["result"])

    def test_render_aligns_the_keys(self):
        text = applier.render([{"key": "TEAM-1", "result": "applied"}, {"key": "TEAM-10", "result": "changed"}])
        self.assertEqual(text.splitlines(), ["TEAM-1   applied", "TEAM-10  changed"])


if __name__ == "__main__":
    unittest.main()
