"""jtk plan link: say which issue blocks which, with the same plan, approval and log as every other write."""
from __future__ import annotations

import unittest

from helpers import FakeJira, state_dir
from jkan import applier, plan, state
from jkan import jira as jira_mod
from test_jira import Recorder
from test_plan_cli import Base, plan_id, run

NOW = lambda: "2026-10-28T12:00:00Z"  # noqa: E731
VIEW = {"name": "plataforma", "boards": ["TEAM"]}
OK = lambda n, s, c: None  # noqa: E731


def seed(jira, key, summary=None):
    jira.issues[key] = {"key": key, "summary": summary or f"Summary of {key}", "description": "", "issuetype": "Subtarea",
                        "status": "Backlog", "parent": None, "category": "todo", "flagged": False}


class World(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.jira = FakeJira()
        for n in range(1, 7):
            seed(self.jira, f"TEAM-{n}")


class PlanTest(World):
    def test_each_blocked_issue_lists_what_blocks_it_once(self):
        body = plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3"), ("TEAM-1", "TEAM-4")], now=NOW)
        self.assertEqual(body["kind"], "link")
        self.assertEqual(body["options"], {"type": "Blocks"})
        self.assertEqual([(i["key"], i["from"], [t["key"] for t in i["to"]]) for i in body["items"]],
                         [("TEAM-3", None, ["TEAM-1", "TEAM-2"]), ("TEAM-4", None, ["TEAM-1"])])
        self.assertEqual(body["items"][0]["to"][0]["title"], "Summary of TEAM-1")

    def test_a_link_that_already_exists_is_left_out_and_said(self):
        self.jira.link_blocks("Blocks", "TEAM-1", "TEAM-3")
        body = plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW)
        self.assertEqual([t["key"] for t in body["items"][0]["to"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-3", "why": "already blocked by TEAM-1"}])

    def test_the_opposite_link_is_left_out_instead_of_making_a_loop(self):
        self.jira.link_blocks("Blocks", "TEAM-3", "TEAM-1")
        body = plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW)
        self.assertEqual([t["key"] for t in body["items"][0]["to"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-3", "why": "TEAM-3 already blocks TEAM-1: the opposite link exists"}])

    def test_a_loop_inside_the_plan_is_refused(self):
        with self.assertRaises(plan.Refused) as ctx:
            plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-2"), ("TEAM-2", "TEAM-3"), ("TEAM-3", "TEAM-1")], now=NOW)
        self.assertIn("loop", str(ctx.exception))

    def test_an_issue_cannot_block_itself(self):
        with self.assertRaises(plan.Refused):
            plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-1")], now=NOW)

    def test_both_ends_must_be_in_the_boards_of_the_view(self):
        with self.assertRaises(plan.Refused) as ctx:
            plan.link(self.jira, VIEW, [("OTHER-1", "TEAM-1")], now=NOW)
        self.assertIn("OTHER-1 is not in the boards", str(ctx.exception))

    def test_jira_needs_a_link_type_that_reads_is_blocked_by(self):
        self.jira.link_type_list = [{"name": "Relates", "inward": "relates to", "outward": "relates to"}]
        with self.assertRaises(plan.Refused) as ctx:
            plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-2")], now=NOW)
        self.assertIn("is blocked by", str(ctx.exception))

    def test_nothing_new_is_refused(self):
        self.jira.link_blocks("Blocks", "TEAM-1", "TEAM-2")
        with self.assertRaises(plan.Refused):
            plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-2")], now=NOW)

    def test_the_window_says_what_blocks_each_issue(self):
        body = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW))
        summary = plan.summary(body)
        self.assertEqual(summary.heading, "Vincular dependencias")
        self.assertIn(("2 vínculos", ""), summary.badges)
        self.assertEqual(summary.rows[0], ("TEAM-3", "Summary of TEAM-3", "bloqueada por TEAM-1, TEAM-2"))
        self.assertIn("TEAM-3: blocked by TEAM-1, TEAM-2", plan.describe(body))


class ApplyTest(World):
    def test_it_writes_each_link_logs_it_and_a_second_run_writes_nothing(self):
        saved = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW))
        outcomes, code = applier.run(self.jira, saved, OK, "jtk apply x", now=NOW)
        self.assertEqual((code, outcomes), (0, [{"key": "TEAM-3", "result": "applied"}]))
        self.assertEqual(self.jira.writes, [("link", "TEAM-1", "TEAM-3"), ("link", "TEAM-2", "TEAM-3")])
        self.assertEqual([b["key"] for b in self.jira.blockers("TEAM-3")], ["TEAM-1", "TEAM-2"])
        entry = state.entries(saved["id"])[0]
        self.assertEqual((entry["action"], [t["key"] for t in entry["a"]]), ("link", ["TEAM-1", "TEAM-2"]))
        applier.run(self.jira, saved, OK, "jtk apply x", now=NOW)
        self.assertEqual(len(self.jira.writes), 2)

    def test_a_link_someone_added_since_the_plan_is_not_written_twice(self):
        saved = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW))
        self.jira.link_blocks("Blocks", "TEAM-1", "TEAM-3")
        self.jira.writes.clear()
        applier.run(self.jira, saved, OK, "jtk apply x", now=NOW)
        self.assertEqual(self.jira.writes, [("link", "TEAM-2", "TEAM-3")])

    def test_revert_leaves_a_link_someone_else_added_between_plan_and_apply(self):
        saved = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW))
        self.jira.link_blocks("Blocks", "TEAM-1", "TEAM-3")
        applier.run(self.jira, saved, OK, "jtk apply x", now=NOW)
        self.assertEqual([t["key"] for t in state.entries(saved["id"])[0]["a"]], ["TEAM-2"])
        back = plan.revert(self.jira, saved, {}, now=NOW)
        self.assertEqual([f["key"] for f in back["items"][0]["from"]], ["TEAM-2"])

    def test_the_approval_counts_links_not_issues(self):
        saved = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3"), ("TEAM-1", "TEAM-4")],
                                          now=NOW))
        asked = []
        applier.run(self.jira, saved, lambda n, s, c: asked.append(n), "jtk apply x", now=NOW)
        self.assertEqual(asked, [3])

    def test_a_link_jira_made_the_other_way_round_is_removed_and_reported(self):
        saved = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3")], now=NOW))
        self.jira.inverted = True
        outcomes, code = applier.run(self.jira, saved, OK, "jtk apply x", now=NOW)
        self.assertEqual(code, 1)
        self.assertIn("other way round", outcomes[0]["result"])
        self.assertEqual(self.jira.links, [])

    def test_revert_removes_the_links_it_wrote(self):
        saved = state.save_plan(plan.link(self.jira, VIEW, [("TEAM-1", "TEAM-3"), ("TEAM-2", "TEAM-3")], now=NOW))
        applier.run(self.jira, saved, OK, "jtk apply x", now=NOW)
        back = state.save_plan(plan.revert(self.jira, saved, {}, now=NOW))
        self.assertEqual(back["kind"], "unlink")
        self.assertEqual([(i["key"], [f["key"] for f in i["from"]]) for i in back["items"]], [("TEAM-3", ["TEAM-1", "TEAM-2"])])
        self.assertIn("deja de estar bloqueada por TEAM-1, TEAM-2", plan.summary(back).rows[0][2])
        outcomes, code = applier.run(self.jira, back, OK, "jtk apply y", now=NOW)
        self.assertEqual((code, self.jira.links), (0, []))
        again = plan.revert(self.jira, back, {}, now=NOW)
        self.assertEqual((again["kind"], [t["key"] for t in again["items"][0]["to"]]), ("link", ["TEAM-1", "TEAM-2"]))


class RealJiraTest(unittest.TestCase):
    ISSUE = {"fields": {"issuelinks": [
        {"id": "901", "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
         "inwardIssue": {"key": "PLATE-1"}},
        {"id": "902", "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
         "outwardIssue": {"key": "PLATE-9"}},
        {"id": "903", "type": {"name": "Relates", "inward": "relates to", "outward": "relates to"},
         "inwardIssue": {"key": "PLATE-5"}}]}}

    def test_blockers_are_the_inward_ends_that_read_is_blocked_by(self):
        rec = Recorder({("GET", "/rest/api/2/issue/PLATE-2"): self.ISSUE})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec)
        self.assertEqual(jira.blockers("PLATE-2"), [{"key": "PLATE-1", "link": "901"}])
        self.assertIn("fields=issuelinks", rec.calls[0][1])

    def test_a_link_puts_the_blocker_inward_like_jira_reads_it_back_and_is_journaled(self):
        # Measured on Jira Cloud on 2026-10-28: with the blocker as outwardIssue the link came out the other way round.
        log = []
        rec = Recorder({("POST", "/rest/api/2/issueLink"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        jira.link_blocks("Blocks", "PLATE-1", "PLATE-2")
        self.assertEqual(rec.calls[0], ("POST", "/rest/api/2/issueLink", {
            "type": {"name": "Blocks"}, "inwardIssue": {"key": "PLATE-1"}, "outwardIssue": {"key": "PLATE-2"}}))
        self.assertEqual(log, [{"action": "link", "key": "PLATE-2", "blocker": "PLATE-1"}])

    def test_unlink_deletes_the_link_by_id(self):
        log = []
        rec = Recorder({("DELETE", "/rest/api/2/issueLink/901"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        jira.unlink("901")
        self.assertEqual(rec.calls[0][:2], ("DELETE", "/rest/api/2/issueLink/901"))
        self.assertEqual(log, [{"action": "unlink", "link": "901"}])

    def test_link_types_are_name_inward_and_outward(self):
        rec = Recorder({("GET", "/rest/api/2/issueLinkType"): {"issueLinkTypes": [
            {"id": "1", "name": "Blocks", "inward": "is blocked by", "outward": "blocks", "self": "x"}]}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec)
        self.assertEqual(jira.link_types(), [{"name": "Blocks", "inward": "is blocked by", "outward": "blocks"}])


class CommandTest(Base):
    def test_jtk_plan_link_saves_a_plan_from_pairs_and_writes_nothing(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-2", "todo")
        self.serve()
        seed(self.jira, "TEAM-1")
        seed(self.jira, "TEAM-2")
        code, out, err = run(["plan", "link", "plataforma", "TEAM-1:TEAM-2"], self.jira)
        self.assertEqual(code, 0, err)
        self.assertIn("TEAM-2: blocked by TEAM-1", out)
        self.assertEqual(state.load_plan(plan_id(out))["kind"], "link")
        self.assertEqual(self.jira.writes, [])

    def test_a_pair_that_is_not_blocker_colon_blocked_is_refused(self):
        code, _, err = run(["plan", "link", "plataforma", "TEAM-1>TEAM-2"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("BLOCKER:BLOCKED", err)

    def test_more_links_than_the_limit_are_refused(self):
        for n in range(1, 5):
            seed(self.jira, f"TEAM-{n}")
        code, _, err = run(["plan", "link", "plataforma", "TEAM-1:TEAM-2", "TEAM-1:TEAM-3", "TEAM-1:TEAM-4",
                            "--max", "2"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("3 links; the limit is 2", err)


if __name__ == "__main__":
    unittest.main()
