"""Every approval that moves an issue to another status says so, in the window and in the terminal, always.

A person approved a `jtk apply` whose window read «Plan 2dad7732e661 · move · view plataforma · 1 issue(s)» and a
«Backlog → Done» chip: nothing said that the write changes a status. The notice now comes from the approval itself
(Summary.transitions), so a writer cannot leave it out by wording its rows differently."""
from __future__ import annotations

import copy
import json
import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import approval, kanban, plan, sync
from test_legacy_guard import Asked, run as run_guarded
from test_push_moves import set_status
from test_spec import GOOD

MOVE = {"id": "x" * 12, "version": 1, "kind": "move", "view": "plataforma", "created": "2026-10-10T12:00:00Z",
        "options": {"to_role": "delivered", "to_status": None, "allow_close": True},
        "items": [{"key": "TEAM-1", "title": "Uno", "from": {"id": "1", "name": "Backlog"},
                   "to": {"id": "3", "name": "Done", "role": "delivered"}, "transition": "1>3"},
                  {"key": "TEAM-2", "title": "Dos", "from": {"id": "1", "name": "Backlog"},
                   "to": {"id": "2", "name": "En curso", "role": "active"}, "transition": "1>2"}],
        "skipped": []}


class NoticeTest(unittest.TestCase):
    def test_a_summary_with_transitions_leads_with_the_notice_in_both_places(self):
        summary = approval.Summary("push 2 write(s)", "Subir cambios", [("A-1", "x", "y")], transitions=2)
        self.assertEqual(str(summary).splitlines()[0], "Cambia el estado de 2 issue(s)")
        html = approval.render_html(summary, 2)
        self.assertIn('<div class="state">Cambia el estado de 2 issue(s)</div>', html)
        self.assertLess(html.index('class="state"'), html.index("<h1>"))
        self.assertGreater(approval.window_height(summary),
                           approval.window_height(approval.Summary("push 2 write(s)", "Subir cambios", [("A-1", "x", "y")])))

    def test_without_transitions_there_is_no_notice(self):
        summary = approval.Summary("assign 1", "Asignar a Ana", [("A-1", "x", "-> Ana")])
        self.assertNotIn("Cambia el estado", str(summary) + approval.render_html(summary, 1))


class PlanApplyTest(unittest.TestCase):
    def test_a_move_plan_says_it_changes_status_and_how_many_it_closes(self):
        summary = plan.summary(MOVE)
        self.assertEqual(summary.transitions, 2)
        self.assertEqual(summary.heading, "Cambiar el estado de 2 issue(s) · cierra 1")
        self.assertEqual(summary.rows[0], ("TEAM-1", "Uno", "Acción: cambiar de estado\nEstado: Backlog -> Done"))
        self.assertTrue(str(summary).startswith("Cambia el estado de 2 issue(s)\n"))

    def test_assign_and_comment_plans_name_their_action_and_move_nothing(self):
        assign = dict(MOVE, kind="assign", options={"person": None},
                      items=[{"key": "TEAM-1", "title": "Uno", "from": None, "to": {"id": "a", "name": "Ana"}}])
        comment = dict(MOVE, kind="comment", options={"text": "hola"}, items=[{"key": "TEAM-1", "title": "Uno"}])
        self.assertEqual((plan.summary(assign).heading, plan.summary(assign).transitions), ("Reasignar 1 issue(s)", 0))
        self.assertEqual(plan.summary(assign).rows[0][2], "Acción: reasignar\nAsignado: unassigned -> Ana")
        self.assertEqual((plan.summary(comment).heading, plan.summary(comment).transitions), ("Comentar en 1 issue(s)", 0))
        self.assertEqual(plan.summary(comment).rows[0][2], "Acción: comentar\nComentario: hola")


class WritersTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()

    def test_create_counts_the_issues_it_will_move(self):
        spec = copy.deepcopy(GOOD)
        spec["items"][0].update(done=True, evidence=["https://github.com/org/repo/pull/7"])
        path = self.project / "spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        asked = Asked()
        run_guarded(["create", "--spec", str(path), "--project", str(self.project), "--jira-project", "PLATE",
                     "--apply", "--assign-open"], self.jira, asked)
        summary = asked.calls[0][1]
        moved = sum(1 for r in summary.rows if "mover a" in r[2])
        self.assertGreater(moved, 0)
        self.assertEqual(summary.transitions, moved)
        self.assertIn(f"y cambiar el estado de {moved}", summary.heading)

    def test_push_says_which_rows_change_status(self):
        key = epic_with_children(self.jira)
        sync.pull(self.jira, self.project, key)
        set_status(kanban.epic_dir(self.project, key) / "tasks/PLATE-603/task.md", "Done")
        asked = Asked()
        run_guarded(["push", key, "--project", str(self.project), "--apply", "--assign-open"], self.jira, asked)
        summary = asked.calls[0][1]
        self.assertEqual(summary.transitions, 1)
        self.assertIn(("PLATE-603", "", "Acción: cambiar de estado\nEstado: Backlog -> Done"), summary.rows)


if __name__ == "__main__":
    unittest.main()
