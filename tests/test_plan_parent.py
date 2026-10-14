"""jtk plan parent: move issues to another epic with the same plan, approval and log as every other write."""
from __future__ import annotations

import unittest

from helpers import FakeJira, state_dir
from jkan import applier, plan, state
from test_plan_cli import Base, plan_id, run

NOW = lambda: "2026-10-14T12:00:00Z"  # noqa: E731
VIEW = {"name": "plataforma", "boards": ["TEAM"]}


def seed(jira, key, issuetype, parent=None, summary=None):
    jira.issues[key] = {"key": key, "summary": summary or f"Summary of {key}", "description": "", "issuetype": issuetype,
                        "status": "Backlog", "parent": parent, "category": "todo", "flagged": False}
    return {"key": key, "summary": jira.issues[key]["summary"]}


class World(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.jira = FakeJira()
        seed(self.jira, "TEAM-10", "Epic", summary="Épica vieja")
        seed(self.jira, "TEAM-20", "Epic", summary="confluence-team-kit")
        self.a = seed(self.jira, "TEAM-1", "Tarea", parent="TEAM-10")
        self.b = seed(self.jira, "TEAM-2", "Tarea", parent="TEAM-10")
        self.sub = seed(self.jira, "TEAM-3", "Subtarea", parent="TEAM-1")
        self.there = seed(self.jira, "TEAM-4", "Tarea", parent="TEAM-20")


class PlanTest(World):
    def test_each_issue_goes_from_its_epic_to_the_target_and_the_odd_ones_are_left_out(self):
        body = plan.parent(self.jira, VIEW, [self.a, self.b, self.sub, self.there], "TEAM-20", now=NOW)
        self.assertEqual(body["kind"], "parent")
        self.assertEqual(body["options"], {"to": {"key": "TEAM-20", "title": "confluence-team-kit"}})
        self.assertEqual([(i["key"], i["from"], i["to"]) for i in body["items"]],
                         [("TEAM-1", {"key": "TEAM-10"}, {"key": "TEAM-20"}),
                          ("TEAM-2", {"key": "TEAM-10"}, {"key": "TEAM-20"})])
        self.assertEqual(body["skipped"], [{"key": "TEAM-3", "why": "a subtask hangs from a task, not from an epic"},
                                           {"key": "TEAM-4", "why": "already there"}])

    def test_the_target_must_be_an_epic(self):
        with self.assertRaises(plan.Refused) as ctx:
            plan.parent(self.jira, VIEW, [self.a], "TEAM-2", now=NOW)
        self.assertIn("not an epic", str(ctx.exception))

    def test_the_window_says_where_they_go_and_links_them(self):
        body = state.save_plan(plan.parent(self.jira, VIEW, [self.a, self.b], "TEAM-20", now=NOW))
        summary = plan.summary(body, browse=lambda key: "https://x.atlassian.net/browse/" + key)
        self.assertEqual(summary.heading, "Mover a la épica TEAM-20")
        self.assertIn(("confluence-team-kit", ""), summary.badges)
        self.assertEqual(summary.rows[0], ("TEAM-1", "Summary of TEAM-1", "TEAM-10 -> TEAM-20"))
        self.assertEqual(summary.transitions, 0)
        self.assertEqual(summary.links[0], "https://x.atlassian.net/browse/TEAM-1")
        self.assertIn("TEAM-1: TEAM-10 -> TEAM-20", plan.describe(body))


class ApplyTest(World):
    def test_it_writes_the_new_parent_logs_it_and_a_second_run_writes_nothing(self):
        saved = state.save_plan(plan.parent(self.jira, VIEW, [self.a, self.b], "TEAM-20", now=NOW))
        outcomes, code = applier.run(self.jira, saved, lambda n, s, c: None, "jtk apply x", now=NOW)
        self.assertEqual(code, 0)
        self.assertEqual(self.jira.writes, [("parent", "TEAM-1", "TEAM-20"), ("parent", "TEAM-2", "TEAM-20")])
        self.assertEqual(self.jira.issues["TEAM-1"]["parent"], "TEAM-20")
        entry = state.entries(saved["id"])[0]
        self.assertEqual((entry["action"], entry["de"], entry["a"]), ("parent", {"key": "TEAM-10"}, {"key": "TEAM-20"}))
        applier.run(self.jira, saved, lambda n, s, c: None, "jtk apply x", now=NOW)
        self.assertEqual(len(self.jira.writes), 2)

    def test_an_issue_moved_by_someone_else_since_the_plan_is_left_alone(self):
        saved = state.save_plan(plan.parent(self.jira, VIEW, [self.a], "TEAM-20", now=NOW))
        self.jira.issues["TEAM-1"]["parent"] = "TEAM-99"
        outcomes, _ = applier.run(self.jira, saved, lambda n, s, c: None, "jtk apply x", now=NOW)
        self.assertEqual(outcomes, [{"key": "TEAM-1", "result": "changed"}])
        self.assertEqual(self.jira.writes, [])

    def test_revert_puts_it_back_in_its_old_epic(self):
        saved = state.save_plan(plan.parent(self.jira, VIEW, [self.a], "TEAM-20", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jtk apply x", now=NOW)
        back = plan.revert(self.jira, saved, {}, now=NOW)
        self.assertEqual([(i["key"], i["from"], i["to"]) for i in back["items"]],
                         [("TEAM-1", {"key": "TEAM-20"}, {"key": "TEAM-10"})])


class CommandTest(Base):
    def test_jtk_plan_parent_saves_a_plan_and_writes_nothing(self):
        self.put("TEAM-1", "todo")
        self.serve()
        seed(self.jira, "TEAM-1", "Tarea", parent="TEAM-10")
        seed(self.jira, "TEAM-20", "Epic", summary="confluence-team-kit")
        code, out, _ = run(["plan", "parent", "plataforma", "TEAM-1", "--to", "TEAM-20"], self.jira)
        self.assertEqual(code, 0, out)
        self.assertIn("TEAM-1: TEAM-10 -> TEAM-20", out)
        self.assertEqual(state.load_plan(plan_id(out))["kind"], "parent")
        self.assertEqual(self.jira.writes, [])


if __name__ == "__main__":
    unittest.main()
