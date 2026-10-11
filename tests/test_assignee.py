from __future__ import annotations

import json
import unittest

from helpers import CONVENTIONS, FakeJira, described, make_project
from jkan import preview, spec, sync
from test_cli import run

MATIAS = "Matias Andres Fernandez"


def assigned_spec():
    return described({"epic": {"summary": "e"}, "items": [
        {"type": "task", "summary": "T1", "assignee": MATIAS,
         "subtasks": [{"summary": "s1"}, {"summary": "s2", "assignee": "ana.gomez@example.com"}]},
        {"type": "task", "summary": "T2"}]})


def assigned_to(jira):
    return {w[2]["summary"]: (w[2].get("assignee") or {}).get("accountId") for w in jira.writes if w[0] == "create"}


class SpecAssigneeTest(unittest.TestCase):
    def test_an_assignee_must_be_a_non_empty_name_email_or_account_id(self):
        bad = described({"epic": {"summary": "e", "assignee": ""}, "items": [
            {"type": "task", "summary": "t", "assignee": 3, "subtasks": [{"summary": "s", "assignee": "  "}]}]})
        findings = spec.validate(bad, CONVENTIONS)
        for ref in ("epic", "items[0]", "items[0].subtasks[0]"):
            self.assertIn(f"{ref}: assignee must be the name, email or accountId of a person", findings)

    def test_a_good_assignee_has_no_findings(self):
        self.assertEqual(spec.validate(assigned_spec(), CONVENTIONS), [])

    def test_subtasks_inherit_their_items_assignee_unless_they_name_their_own(self):
        queries = {op["summary"]: op["assignee_query"] for op in spec.plan(assigned_spec(), CONVENTIONS)}
        self.assertEqual(queries, {"e": None, "T1": MATIAS, "s1": MATIAS, "s2": "ana.gomez@example.com", "T2": None})


class CreateAssigneeTest(unittest.TestCase):
    def test_dry_run_resolves_the_people_and_writes_nothing(self):
        jira = FakeJira()
        result = sync.create(jira, make_project(), assigned_spec(), CONVENTIONS, apply=False)
        names = {op["summary"]: (op.get("person") or {}).get("name") for op in result["ops"]}
        self.assertEqual(names["T1"], "Matías Andrés Fernandez")
        self.assertEqual(names["s1"], "Matías Andrés Fernandez")
        self.assertEqual(names["s2"], "Ana Gómez")
        self.assertIsNone(names["T2"])
        self.assertEqual(jira.writes, [])

    def test_apply_creates_each_issue_assigned_to_its_person(self):
        jira = FakeJira()
        sync.create(jira, make_project(), assigned_spec(), CONVENTIONS, apply=True, assign_open=False)
        self.assertEqual(assigned_to(jira), {"e": None, "T1": "acc-matias", "s1": "acc-matias", "s2": "acc-ana", "T2": None})

    def test_an_explicit_assignee_is_not_an_open_item_to_decide(self):
        everyone = described({"epic": {"summary": "e", "assignee": MATIAS}, "items": [
            {"type": "task", "summary": "t", "assignee": MATIAS}]})
        jira = FakeJira()
        sync.create(jira, make_project(), everyone, CONVENTIONS, apply=True)  # assign_open left undecided
        self.assertEqual(assigned_to(jira), {"e": "acc-matias", "t": "acc-matias"})

    def test_an_explicit_assignee_beats_me_on_a_done_item_which_still_closes(self):
        done = described({"epic": {"summary": "e"}, "items": [
            {"type": "task", "summary": "Hecha", "assignee": MATIAS, "done": True, "evidence": ["https://example.com/pr/1"]}]})
        jira = FakeJira()
        sync.create(jira, make_project(), done, CONVENTIONS, apply=True, assign_open=False)
        self.assertEqual(assigned_to(jira)["Hecha"], "acc-matias")
        self.assertIn(("transition", "PLATE-601", "Done"), jira.writes)

    def test_people_are_searched_among_those_assignable_in_the_epics_project(self):
        jira = FakeJira()
        sync.create(jira, make_project(), assigned_spec(), CONVENTIONS, apply=False)
        self.assertEqual(set(jira.search_projects), {"PLATE"})

    def test_the_same_person_is_looked_up_once(self):
        jira = FakeJira()
        sync.create(jira, make_project(), assigned_spec(), CONVENTIONS, apply=False)
        self.assertEqual(len(jira.searches), len(set(jira.searches)))

    def test_an_ambiguous_assignee_refuses_the_create_before_any_write_even_in_a_dry_run(self):
        vague = described({"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "assignee": "Martin Fernandez"}]})
        for apply in (False, True):
            jira = FakeJira()
            with self.assertRaises(ValueError) as caught:
                sync.create(jira, make_project(), vague, CONVENTIONS, apply=apply, assign_open=False)
            self.assertIn("Martin Daniel Fernandez", str(caught.exception))
            self.assertIn("martin.lopez@example.com", str(caught.exception))
            self.assertIn("items[0]", str(caught.exception))
            self.assertEqual(jira.writes, [])

    def test_an_unknown_assignee_refuses_the_create(self):
        nobody = described({"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "assignee": "Zzzz Qqqq"}]})
        jira = FakeJira()
        with self.assertRaises(ValueError) as caught:
            sync.create(jira, make_project(), nobody, CONVENTIONS, apply=True, assign_open=False)
        self.assertIn("Zzzz Qqqq", str(caught.exception))
        self.assertEqual(jira.writes, [])

    def test_the_html_preview_flags_an_approximate_person(self):
        near = described({"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "assignee": "Maria Fernandez"}]})
        jira = FakeJira(users=[{"id": "acc-mario", "name": "Mario Fernandez", "email": "mario@example.com"}])
        page = preview.render(sync.create(jira, make_project(), near, CONVENTIONS, apply=False)["ops"], CONVENTIONS)
        self.assertIn("Mario Fernandez", page)
        self.assertIn("coincidencia aproximada", page)

    def test_the_html_preview_names_the_person(self):
        result = sync.create(FakeJira(), make_project(), assigned_spec(), CONVENTIONS, apply=False)
        page = preview.render(result["ops"], CONVENTIONS)
        self.assertIn("Matías Andrés Fernandez", page)
        self.assertIn("Ana Gómez", page)


class CreateCliAssigneeTest(unittest.TestCase):
    def test_the_tree_names_who_each_issue_goes_to(self):
        jira, project = FakeJira(), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps(assigned_spec()), encoding="utf-8")
        code, out, _ = run(["create", "--spec", str(path), "--project", str(project), "--jira-project", "PLATE",
                            "--no-assign-open"], jira)
        self.assertEqual(code, 0)
        self.assertIn("Matías Andrés Fernandez", out)
        self.assertIn("Ana Gómez", out)

    def test_an_ambiguous_assignee_exits_1_and_lists_the_candidates_on_stderr(self):
        jira, project = FakeJira(), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps(described({"epic": {"summary": "e"}, "items": [
            {"type": "task", "summary": "t", "assignee": "Martin Fernandez"}]})), encoding="utf-8")
        code, _, err = run(["create", "--spec", str(path), "--project", str(project), "--jira-project", "PLATE",
                            "--no-assign-open"], jira)
        self.assertEqual(code, 1)
        self.assertIn("martin.fernandez@example.com", err)

    def test_an_approximate_assignee_is_flagged_in_the_tree(self):
        jira, project = FakeJira(users=[{"id": "acc-mario", "name": "Mario Fernandez", "email": "mario@example.com"}]), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps(described({"epic": {"summary": "e"}, "items": [
            {"type": "task", "summary": "t", "assignee": "Maria Fernandez"}]})), encoding="utf-8")
        _, out, _ = run(["create", "--spec", str(path), "--project", str(project), "--jira-project", "PLATE",
                         "--no-assign-open"], jira)
        self.assertIn("Mario Fernandez", out)
        self.assertIn("coincidencia aproximada", out)


if __name__ == "__main__":
    unittest.main()
