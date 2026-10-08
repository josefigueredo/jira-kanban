from __future__ import annotations

import json
import unittest

from helpers import FailingJira, FakeJira, epic_with_children, make_project
from test_cli import run


class WhoTest(unittest.TestCase):
    def test_a_unique_match_prints_name_email_and_id_and_exits_0(self):
        code, out, _ = run(["who", "Matias Andres Fernandez", "--project", str(make_project()), "--jira-project", "PLATE"],
                           FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("Matías Andrés Fernandez", out)
        self.assertIn("matias.fernandez@example.com", out)
        self.assertIn("acc-matias", out)
        self.assertIn("unique", out)

    def test_a_typo_still_finds_the_person(self):
        code, out, _ = run(["who", "Matiaz Andres Fernandez", "--project", str(make_project()), "--jira-project", "PLATE"],
                           FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("acc-matias", out)

    def test_several_people_exit_1_and_all_are_listed_with_their_email(self):
        code, out, _ = run(["who", "Martin Fernandez", "--project", str(make_project()), "--jira-project", "PLATE"],
                           FakeJira())
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", out)
        self.assertIn("martin.fernandez@example.com", out)
        self.assertIn("martin.lopez@example.com", out)

    def test_nobody_exits_1(self):
        code, out, _ = run(["who", "Zzzz Qqqq", "--project", str(make_project()), "--jira-project", "PLATE"], FakeJira())
        self.assertEqual(code, 1)
        self.assertIn("none", out)

    def test_json_is_machine_readable_for_an_agent_to_branch_on(self):
        code, out, _ = run(["who", "Martin Fernandez", "--json", "--project", str(make_project()),
                            "--jira-project", "PLATE"], FakeJira())
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(data["status"], "ambiguous")
        self.assertEqual({c["id"] for c in data["candidates"]}, {"acc-martin-d", "acc-martin-l"})

    def test_it_searches_people_assignable_in_the_given_project(self):
        jira = FakeJira()
        run(["who", "Ana", "--project", str(make_project()), "--jira-project", "PLATE"], jira)
        self.assertEqual(set(jira.search_projects), {"PLATE"})

    def test_an_approximate_match_says_so_in_text_and_in_json(self):
        jira = FakeJira(users=[{"id": "acc-mario", "name": "Mario Fernandez", "email": "mario@example.com"}])
        code, out, _ = run(["who", "Maria Fernandez", "--project", str(make_project()), "--jira-project", "PLATE"], jira)
        self.assertEqual(code, 0)
        self.assertIn("approximate", out)
        code, out, _ = run(["who", "Maria Fernandez", "--json", "--project", str(make_project()),
                            "--jira-project", "PLATE"], jira)
        self.assertFalse(json.loads(out)["candidates"][0]["exact"])

    def test_an_exact_match_carries_no_warning(self):
        _, out, _ = run(["who", "Matias Andres Fernandez", "--project", str(make_project()), "--jira-project", "PLATE"],
                        FakeJira())
        self.assertNotIn("approximate", out)


class AssignTest(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()
        self.epic = epic_with_children(self.jira)  # PLATE-600 epic > PLATE-601 story > PLATE-602 subtask; PLATE-603 task
        self.project = make_project()

    def assign(self, *args):
        return run(["assign", *args, "--project", str(self.project)], self.jira)

    def test_a_dry_run_lists_what_would_change_and_writes_nothing(self):
        code, out, _ = self.assign("PLATE-601", "Matias Andres Fernandez")
        self.assertEqual(code, 0)
        self.assertIn("PLATE-601", out)
        self.assertIn("Matías Andrés Fernandez", out)
        self.assertIn("dry run", out)
        self.assertEqual(self.jira.writes, [])

    def test_apply_assigns_only_that_issue_without_tree(self):
        code, out, _ = self.assign("PLATE-601", "Matias Andres Fernandez", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.jira.writes, [("assign", "PLATE-601", "acc-matias")])
        self.assertIn("assigned 1 issue", out)

    def test_tree_assigns_the_issue_and_everything_under_it(self):
        code, _, _ = self.assign(self.epic, "Matias Andres Fernandez", "--tree", "--apply")
        self.assertEqual(code, 0)
        assigned = {w[1] for w in self.jira.writes if w[0] == "assign"}
        self.assertEqual(assigned, {"PLATE-600", "PLATE-601", "PLATE-602", "PLATE-603"})
        self.assertTrue(all(w[2] == "acc-matias" for w in self.jira.writes))

    def test_tree_in_a_dry_run_lists_the_whole_tree_and_writes_nothing(self):
        _, out, _ = self.assign(self.epic, "Matias Andres Fernandez", "--tree")
        for key in ("PLATE-600", "PLATE-601", "PLATE-602", "PLATE-603"):
            self.assertIn(key, out)
        self.assertEqual(self.jira.writes, [])

    def test_an_ambiguous_person_exits_1_lists_them_and_writes_nothing(self):
        code, _, err = self.assign("PLATE-601", "Martin Fernandez", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("martin.lopez@example.com", err)
        self.assertEqual(self.jira.writes, [])

    def test_people_are_searched_in_the_project_of_the_issue_key(self):
        self.assign("PLATE-601", "Ana Gomez")
        self.assertEqual(set(self.jira.search_projects), {"PLATE"})

    def test_one_rejected_assignment_is_reported_and_the_rest_still_go(self):
        class Refusing(FakeJira):
            def assign(self, key, account_id):
                if key == "PLATE-602":
                    raise FailingJira("HTTP 400 on assign")
                super().assign(key, account_id)

        self.jira = Refusing()
        self.epic = epic_with_children(self.jira)
        code, out, err = self.assign(self.epic, "Matias Andres Fernandez", "--tree", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("PLATE-602", err)
        self.assertEqual({w[1] for w in self.jira.writes if w[0] == "assign"}, {"PLATE-600", "PLATE-601", "PLATE-603"})
        self.assertIn("assigned 3 issue", out)

    def test_an_approximate_person_is_flagged_in_the_assign_preview(self):
        self.jira = FakeJira(users=[{"id": "acc-mario", "name": "Mario Fernandez", "email": "mario@example.com"}])
        self.epic = epic_with_children(self.jira)
        _, out, _ = self.assign("PLATE-601", "Maria Fernandez")
        self.assertIn("Mario Fernandez", out)
        self.assertIn("approximate", out)

    def test_an_exact_person_is_not_flagged_in_the_assign_preview(self):
        _, out, _ = self.assign("PLATE-601", "Matias Andres Fernandez")
        self.assertNotIn("approximate", out)


if __name__ == "__main__":
    unittest.main()
