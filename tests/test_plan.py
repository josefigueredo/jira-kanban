from __future__ import annotations

import unittest

import plan_fixtures as pf
import team_fixtures as fx
from helpers import CONVENTIONS, FakeJira, state_dir
from jkan import board_profile, plan, state

TODAY = fx.TODAY
NOW = lambda: "2026-10-10T12:00:00Z"  # noqa: E731


class Base(unittest.TestCase):
    def setUp(self):
        self.state = state_dir()
        self.jira = FakeJira()
        pf.workflow(self.jira)
        self.profiles = fx.profiles()
        self.view = fx.view()
        self.issues = {}

    def put(self, key, role, assignee=None, **over):
        self.issues[key] = pf.put(self.jira, key, role, assignee, **over)
        return self.issues[key]

    def serve_searches(self):
        """Answer `key in (…)` the way Jira would: the issues we know by those keys."""
        def answer(jql):
            wanted = jql.split("key in (", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
            return [self.issues[k] for k in wanted if k in self.issues]
        self.jira.search_answer = answer

    def select(self, keys=(), open_issues=(), unassigned=False, older_than=None, role=None, limit=25):
        return plan.select(self.jira, self.view, self.profiles, CONVENTIONS, list(open_issues), TODAY, list(keys),
                           unassigned, older_than, role, limit)


class SelectTest(Base):
    def test_explicit_keys_are_fetched_from_jira_in_the_given_order(self):
        self.put("TEAM-2", "todo")
        self.put("TEAM-1", "todo")
        self.serve_searches()
        self.assertEqual([i["key"] for i in self.select(["TEAM-1", "TEAM-2"])], ["TEAM-1", "TEAM-2"])
        self.assertEqual(self.jira.jqls, ["key in (TEAM-1, TEAM-2)"])

    def test_filters_select_from_the_open_issues_of_the_view_oldest_first(self):
        a = self.put("TEAM-1", "todo", created="2026-09-01")
        b = self.put("TEAM-2", "todo", created="2026-08-01")
        c = self.put("TEAM-3", "todo", assignee=fx.ANA, created="2026-07-01")
        got = self.select(open_issues=[a, b, c], unassigned=True)
        self.assertEqual([i["key"] for i in got], ["TEAM-2", "TEAM-1"])
        self.assertEqual(self.jira.jqls, [])  # nothing needed fetching

    def test_keys_and_filters_add_up_without_repeating_an_issue(self):
        a = self.put("TEAM-1", "todo")
        self.put("TEAM-5", "active", fx.ANA)
        self.serve_searches()
        got = self.select(["TEAM-1", "TEAM-5"], open_issues=[a], unassigned=True)
        self.assertEqual([i["key"] for i in got], ["TEAM-1", "TEAM-5"])
        self.assertEqual(self.jira.jqls, ["key in (TEAM-5)"])

    def test_saying_nothing_is_refused_there_is_no_all(self):
        with self.assertRaisesRegex(plan.Refused, "say which issues"):
            self.select()

    def test_an_issue_outside_the_boards_of_the_view_is_refused(self):
        with self.assertRaisesRegex(plan.Refused, r"OTHER-1 is not in the boards of view 'plataforma' \(TEAM, DESK\)"):
            self.select(["OTHER-1"])

    def test_a_key_that_carries_jql_is_refused_before_any_query(self):
        for bad in ("TEAM-1) OR project = X", "team-1", "TEAM-1\n", "TEAM-", "TEAM-1,TEAM-2", "TEAM-1 TEAM-2", "-1", ""):
            with self.assertRaisesRegex(plan.Refused, "is not an issue key", msg=repr(bad)):
                self.select([bad])
        self.assertEqual(self.jira.jqls, [])

    def test_a_key_jira_does_not_show_is_refused(self):
        self.serve_searches()
        with self.assertRaisesRegex(plan.Refused, "TEAM-9"):
            self.select(["TEAM-9"])

    def test_more_than_the_limit_is_refused_and_says_how_to_raise_it(self):
        issues = [self.put(f"TEAM-{n}", "todo") for n in range(1, 4)]
        with self.assertRaisesRegex(plan.Refused, r"3 issues; the limit is 2 \(raise it with --max, up to 200\)"):
            self.select(open_issues=issues, unassigned=True, limit=2)
        self.assertEqual(len(self.select(open_issues=issues, unassigned=True, limit=3)), 3)

    def test_the_filters_matching_nothing_is_refused(self):
        with self.assertRaisesRegex(plan.Refused, "no issue matches"):
            self.select(open_issues=[], unassigned=True)

    def test_max_is_between_1_and_200(self):
        self.assertEqual((plan.check_max(None), plan.check_max(1), plan.check_max(200)), (25, 1, 200))
        for bad in (0, 201, -5):
            with self.assertRaisesRegex(plan.Refused, "--max"):
                plan.check_max(bad)


class ProfileTest(Base):
    def test_a_board_with_undecided_statuses_is_refused_when_it_is_touched(self):
        self.profiles["TEAM"] = fx.profile("TEAM", decide_waiting=False)
        touched = [self.put("TEAM-1", "todo")]
        with self.assertRaisesRegex(plan.Refused, "TEAM has 1 status.*without a role.*jk board set"):
            plan.check_profiles(touched, self.profiles)

    def test_a_board_that_is_not_touched_does_not_matter(self):
        self.profiles["TEAM"] = fx.profile("TEAM", decide_waiting=False)
        plan.check_profiles([self.put("DESK-1", "todo")], self.profiles)


class MoveTest(Base):
    def move(self, keys, to_role="active", **kw):
        selection = [self.put(k, "todo") if k not in self.issues else self.issues[k] for k in keys]
        return plan.move(self.jira, self.view, selection, self.profiles, to_role, now=NOW, **kw)

    def test_a_move_records_the_origin_the_destination_and_the_transition_id(self):
        body = self.move(["TEAM-1"])
        self.assertEqual(body["kind"], "move")
        self.assertEqual((body["view"], body["version"], body["created"]), ("plataforma", 1, "2026-10-10T12:00:00Z"))
        self.assertEqual(body["items"], [{"key": "TEAM-1", "from": {"id": "1", "name": "Backlog"},
                                          "to": {"id": "2", "name": "En curso", "role": "active"}, "transition": "1>2"}])
        self.assertEqual(body["skipped"], [])
        self.assertEqual(body["options"], {"to_role": "active", "to_status": None, "allow_close": False})

    def test_planning_never_writes(self):
        self.move(["TEAM-1", "TEAM-2"])
        self.assertEqual(self.jira.writes, [])

    def test_closing_needs_allow_close_and_the_plan_counts_the_closes(self):
        with self.assertRaisesRegex(plan.Refused, "closes issues: add --allow-close"):
            self.move(["TEAM-1"], "delivered")
        with self.assertRaisesRegex(plan.Refused, "closes issues"):
            self.move(["TEAM-1"], "dropped")
        body = self.move(["TEAM-1"], "delivered", allow_close=True)
        self.assertIn("closes 1", plan.describe(dict(body, id="x" * 12)))

    def test_a_role_that_does_not_exist_is_refused(self):
        with self.assertRaisesRegex(plan.Refused, "role must be one of"):
            self.move(["TEAM-1"], "finished")

    def test_an_issue_already_in_the_destination_is_skipped_not_moved(self):
        self.put("TEAM-1", "active")
        self.put("TEAM-2", "todo")
        body = self.move(["TEAM-1", "TEAM-2"])
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "already there"}])

    def test_two_transitions_to_the_role_make_it_ambiguous_and_to_status_resolves_it(self):
        board_profile.assign(self.profiles["TEAM"], "active", ["Blocked"])  # now En curso (2) and Blocked (3) are both «active»
        selection = [self.put("TEAM-1", "todo")]
        with self.assertRaisesRegex(plan.Refused, "nothing to move: TEAM-1: ambiguous"):
            plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW)
        body = plan.move(self.jira, self.view, selection + [self.put("TEAM-2", "todo")], self.profiles, "active",
                         to_status="2", now=NOW)
        self.assertEqual([(i["key"], i["to"]["id"]) for i in body["items"]], [("TEAM-1", "2"), ("TEAM-2", "2")])
        self.assertEqual(body["options"]["to_status"], "2")

    def test_the_ambiguous_issue_lists_its_options_while_others_still_move(self):
        board_profile.assign(self.profiles["TEAM"], "active", ["Blocked"])  # En curso (2) and Blocked (3) are both «active»
        self.jira.workflow["4"] = [t for t in self.jira.workflow["4"] if t["id"] != "4>3"]  # from «waiting» only 2 is reachable
        a, b = self.put("TEAM-1", "todo"), self.put("TEAM-2", "waiting")
        body = plan.move(self.jira, self.view, [a, b], self.profiles, "active", now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "ambiguous",
                                            "options": ["Blocked (transition 1>3)", "En curso (transition 1>2)"]}])

    def test_to_status_must_play_the_role_asked(self):
        with self.assertRaisesRegex(plan.Refused, "status 3 of TEAM does not play the role active"):
            self.move(["TEAM-1"], to_status="3")

    def test_when_nothing_can_move_the_plan_is_refused_with_every_reason(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-3", "blocked")
        self.jira.workflow["1"] = []
        self.jira.workflow["3"] = [dict(t, required=["resolution"]) if t["to"]["id"] == "2" else t for t in self.jira.workflow["3"]]
        with self.assertRaises(plan.Refused) as caught:
            plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-3"]], self.profiles, "active", now=NOW)
        self.assertIn("TEAM-1: no path", str(caught.exception))
        self.assertIn("TEAM-3: required fields", str(caught.exception))

    def test_a_mixed_selection_keeps_what_can_move_and_lists_the_rest(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-3", "blocked")
        self.jira.workflow["3"] = [dict(t, required=["resolution"]) if t["to"]["id"] == "2" else t for t in self.jira.workflow["3"]]
        body = plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-3"]], self.profiles, "active", now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-1"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-3", "why": "required fields", "fields": ["resolution"]}])


class DescribeTest(Base):
    def test_the_summary_names_every_issue_what_changes_and_what_was_left_out(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-2", "active")
        body = plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-2"]], self.profiles, "active", now=NOW)
        text = plan.describe(dict(body, id="abcdef123456"))
        self.assertIn("Plan abcdef123456 · move · view plataforma · 1 issue(s)", text)
        self.assertIn("TEAM-1: Backlog -> En curso", text)
        self.assertIn("Left out:", text)
        self.assertIn("TEAM-2: already there", text)

    def test_only_shows_just_those_issues(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-2", "todo")
        body = plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-2"]], self.profiles, "active", now=NOW)
        text = plan.describe(dict(body, id="abcdef123456"), only=["TEAM-2"])
        self.assertIn("1 issue(s)", text)
        self.assertNotIn("TEAM-1:", text)


ANA = {"id": "acc-ana", "name": "Ana Gómez", "email": "ana@example.com", "score": 1.0, "exact": True}


class AssignTest(Base):
    def test_an_assign_records_who_had_it_and_who_gets_it(self):
        a = self.put("TEAM-1", "todo")
        b = self.put("TEAM-2", "todo", fx.BETO)
        body = plan.assign(self.view, [a, b], ANA, now=NOW)
        self.assertEqual(body["kind"], "assign")
        self.assertEqual(body["options"], {"person": {"id": "acc-ana", "name": "Ana Gómez"}})
        self.assertEqual(body["items"], [
            {"key": "TEAM-1", "from": None, "to": {"id": "acc-ana", "name": "Ana Gómez"}},
            {"key": "TEAM-2", "from": {"id": "acc-beto", "name": "Beto Ruiz"}, "to": {"id": "acc-ana", "name": "Ana Gómez"}}])

    def test_who_already_has_it_is_left_out_and_if_all_do_there_is_no_plan(self):
        a = self.put("TEAM-1", "todo", fx.ANA)
        b = self.put("TEAM-2", "todo")
        body = plan.assign(self.view, [a, b], ANA, now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "already there"}])
        with self.assertRaisesRegex(plan.Refused, "nothing to assign: TEAM-1: already there"):
            plan.assign(self.view, [a], ANA, now=NOW)

    def test_the_summary_reads_from_to(self):
        a = self.put("TEAM-1", "todo")
        text = plan.describe(dict(plan.assign(self.view, [a], ANA, now=NOW), id="abcdef123456"))
        self.assertIn("TEAM-1: unassigned -> Ana Gómez", text)


class CommentTest(Base):
    def test_a_comment_keeps_the_text_once_and_one_item_per_issue(self):
        a, b = self.put("TEAM-1", "todo"), self.put("TEAM-2", "active")
        body = plan.comment(self.view, [a, b], "  Revisamos esto el jueves.  ", now=NOW)
        self.assertEqual(body["kind"], "comment")
        self.assertEqual(body["options"], {"text": "Revisamos esto el jueves."})
        self.assertEqual(body["items"], [{"key": "TEAM-1"}, {"key": "TEAM-2"}])

    def test_an_empty_or_huge_text_is_refused(self):
        a = self.put("TEAM-1", "todo")
        for bad in ("", "   ", "\n\t"):
            with self.assertRaisesRegex(plan.Refused, "the comment is empty"):
                plan.comment(self.view, [a], bad, now=NOW)
        with self.assertRaisesRegex(plan.Refused, "too long"):
            plan.comment(self.view, [a], "x" * (plan.MAX_TEXT + 1), now=NOW)

    def test_the_summary_shows_the_text_that_will_be_posted(self):
        a = self.put("TEAM-1", "todo")
        text = plan.describe(dict(plan.comment(self.view, [a], "hola equipo", now=NOW), id="abcdef123456"))
        self.assertIn("Comment: hola equipo", text)
        self.assertIn("TEAM-1", text)


class RevertTest(Base):
    def applied_move(self, keys=("TEAM-1", "TEAM-2")):
        from jkan import applier
        selection = [self.put(k, "todo") for k in keys]
        saved = state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        self.jira.writes.clear()
        return saved

    def test_reverting_a_move_goes_back_to_the_status_it_left_by_its_own_transition(self):
        saved = self.applied_move()
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual((body["kind"], body["options"]), ("move", {"revert_of": saved["id"]}))
        self.assertEqual(body["items"], [
            {"key": k, "from": {"id": "2", "name": "En curso"}, "to": {"id": "1", "name": "Backlog", "role": "todo"},
             "transition": "2>1"} for k in ("TEAM-1", "TEAM-2")])
        self.assertEqual(self.jira.writes, [])

    def test_an_issue_that_moved_on_since_is_left_out(self):
        saved = self.applied_move()
        self.jira.board["TEAM-1"].update(status_id="5", status="Done")
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "changed"}])

    def test_a_workflow_without_a_way_back_is_marked(self):
        saved = self.applied_move(("TEAM-1",))
        self.jira.workflow["2"] = []
        with self.assertRaisesRegex(plan.Refused, "TEAM-1: no path"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)

    def test_reverting_an_assign_goes_back_to_who_had_it_including_nobody(self):
        from jkan import applier
        selection = [self.put("TEAM-1", "todo"), self.put("TEAM-2", "todo", fx.BETO)]
        saved = state.save_plan(plan.assign(self.view, selection, ANA, now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual(body["kind"], "assign")
        self.assertEqual(body["items"], [
            {"key": "TEAM-1", "from": {"id": "acc-ana", "name": "Ana Gómez"}, "to": None},
            {"key": "TEAM-2", "from": {"id": "acc-ana", "name": "Ana Gómez"}, "to": {"id": "acc-beto", "name": "Beto Ruiz"}}])
        self.assertIn("TEAM-1: Ana Gómez -> unassigned", plan.describe(dict(body, id="abcdef123456")))

    def test_comments_cannot_be_reverted_and_the_plan_says_so(self):
        from jkan import applier
        saved = state.save_plan(plan.comment(self.view, [self.put("TEAM-1", "todo")], "hola", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        with self.assertRaisesRegex(plan.Refused, "TEAM-1: comments are not reverted"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)

    def test_a_plan_that_wrote_nothing_has_nothing_to_revert(self):
        selection = [self.put("TEAM-1", "todo")]
        saved = state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW))
        with self.assertRaisesRegex(plan.Refused, "wrote nothing"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)


if __name__ == "__main__":
    unittest.main()
