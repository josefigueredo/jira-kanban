"""One source for what each issue of a `jtk create` is: its state after the pass, who gets it, what the pass does to it.
The console dry run, the --html preview and the approval window each show a different amount, but never a different fact."""
from __future__ import annotations

import json
import re
import unittest

from helpers import CONVENTIONS, FakeJira, described, make_project
from jkan import facts, spec
from test_cli import run as run_cli
from test_legacy_guard import Asked, run as run_guarded


def op(**kw):
    base = {"ref": "r", "kind": "task", "summary": "s", "parent": None, "assignee": "ask"}
    return {**base, **kw}


class StatusTest(unittest.TestCase):
    def test_done_started_or_the_projects_first_status(self):
        self.assertEqual(facts.status(op(done=True), CONVENTIONS), "Done")
        self.assertEqual(facts.status(op(started=True), CONVENTIONS), "En progreso")
        self.assertEqual(facts.status(op(), CONVENTIONS), "Backlog")

    def test_a_project_can_name_its_first_status(self):
        self.assertEqual(facts.status(op(), {**CONVENTIONS, "initial_status": "Por hacer"}), "Por hacer")

    def test_done_wins_over_started(self):
        self.assertEqual(facts.status(op(done=True, started=True), CONVENTIONS), "Done")


class ActionTest(unittest.TestCase):
    def test_creating_is_enough_when_the_issue_stays_where_jira_puts_it(self):
        self.assertEqual(facts.action(op(), CONVENTIONS), "Crear")

    def test_an_issue_that_is_also_moved_says_where(self):
        self.assertEqual(facts.action(op(done=True), CONVENTIONS), "Crear y mover a Done")
        self.assertEqual(facts.action(op(started=True), CONVENTIONS), "Crear y mover a En progreso")


class AssigneeTest(unittest.TestCase):
    def test_the_words_for_the_console_and_the_html(self):
        said = {kind: facts.assignee(op(assignee=kind)) for kind in ("me-done", "me-started", "me", "none", "ask")}
        self.assertEqual(said, {"me-done": "Vos · completa", "me-started": "Vos · en curso", "me": "Vos",
                                "none": "Sin asignar", "ask": "A decidir"})

    def test_the_window_says_the_approvers_name_never_vos(self):
        for kind in ("me-done", "me-started", "me"):
            self.assertEqual(facts.assignee(op(assignee=kind), mine="Ana Gómez"), "Ana Gómez")
        self.assertEqual(facts.assignee(op(assignee="none"), mine="Ana Gómez"), "Sin asignar")

    def test_a_named_person_and_an_approximate_match(self):
        exact = op(assignee="person", person={"name": "Matías Fernández", "exact": True})
        near = op(assignee="person", person={"name": "Matías Fernández", "exact": False})
        self.assertEqual(facts.assignee(exact), "Matías Fernández")
        self.assertEqual(facts.assignee(near), "Matías Fernández · coincidencia aproximada")

    def test_only_what_nobody_has_yet_is_marked_off(self):
        self.assertTrue(facts.unassigned(op(assignee="none")))
        self.assertTrue(facts.unassigned(op(assignee="ask")))
        self.assertFalse(facts.unassigned(op(assignee="me")))


class PlaceholderTest(unittest.TestCase):
    def test_a_new_issue_is_named_by_its_place_in_the_creation_order(self):
        self.assertEqual(facts.placeholder(3), "NUEVO-3")


SPEC = described({"epic": {"summary": "Épica"}, "items": [
    {"type": "task", "summary": "Hecha", "done": True, "evidence": ["https://example.com/pr/1"]},
    {"type": "task", "summary": "En curso", "started": True},
    {"type": "task", "summary": "Pendiente"}]})


class ThreeViewsAgreeTest(unittest.TestCase):
    """The same spec, seen three ways: every fact one view shows is the fact the others show."""

    def setUp(self):
        self.project = make_project()
        path = self.project / "spec.json"
        path.write_text(json.dumps(SPEC), encoding="utf-8")
        self.base = ["create", "--spec", str(path), "--project", str(self.project), "--jira-project", "PLATE"]

    def console(self):
        _, out, _ = run_cli(self.base, FakeJira())
        lines = [ln for ln in out.splitlines() if re.match(r"^\s*(Issue|NUEVO-\d+)\s", ln)]
        return [re.split(r"\s{2,}", ln.strip()) for ln in lines]

    def html_statuses(self):
        html = self.project / "v.html"
        run_cli(self.base + ["--html", str(html)], FakeJira())
        page = html.read_text(encoding="utf-8")
        return [re.search(r'<div class="status">\s*(?:<[^>]+>\s*)*([^<\n]+)', s).group(1).strip()
                for s in re.findall(r'<section class="issue[^"]*" id="NUEVO-\d+">(.*?)</section>', page, re.S)]

    def window_rows(self):
        asked = Asked()
        run_guarded(self.base + ["--apply", "--assign-open"], FakeJira(), asked)
        return asked.calls[0][1].rows

    def test_the_console_has_a_state_column_and_the_same_keys_as_the_html(self):
        rows = self.console()
        self.assertEqual(rows[0], ["Issue", "Tipo", "Estado", "Asignado", "Título"])
        self.assertEqual([r[0] for r in rows[1:]], ["NUEVO-1", "NUEVO-2", "NUEVO-3", "NUEVO-4"])

    def test_console_html_and_window_agree_on_where_each_issue_ends(self):
        console = [r[2] for r in self.console()[1:]]
        self.assertEqual(console, ["Backlog", "Done", "En progreso", "Backlog"])
        self.assertEqual(self.html_statuses(), console)
        actions = [r[2].splitlines()[0] for r in self.window_rows()]
        self.assertEqual(actions, ["Acción: Crear", "Acción: Crear y mover a Done", "Acción: Crear y mover a En progreso", "Acción: Crear"])

    def test_the_window_stays_two_lines_a_card(self):
        for _type, _name, change in self.window_rows():
            self.assertEqual(len(change.splitlines()), 2)
            self.assertTrue(change.splitlines()[1].startswith("Asignado a: "))

    def test_the_approval_text_counts_the_moves_not_only_the_creations(self):
        asked = Asked()
        run_guarded(self.base + ["--apply", "--assign-open"], FakeJira(), asked)
        n, summary, _ = asked.calls[0]
        self.assertEqual(n, 4)
        self.assertIn("create 4 issue(s) in PLATE", summary)
        self.assertIn("move 2", summary)


if __name__ == "__main__":
    unittest.main()
