from __future__ import annotations

import contextlib
import io
import unittest

import team_fixtures as fx
from helpers import FakeJira, config_dir, issue, make_project
from jkan import board_profile, cli, views


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args + ["--project", str(make_project())], client=lambda project: jira, today=lambda: fx.TODAY)
    return code, out.getvalue(), err.getvalue()


class ViewFlagTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        views.save(fx.view())

    def test_done_next_and_blocked_look_at_the_boards_of_the_view(self):
        for args in (["done", "--since", "2026-10-01"], ["next"], ["blocked"]):
            jira = FakeJira()
            code, _, _ = run(args + ["--view", "plataforma"], jira)
            self.assertEqual(code, 0, args)
            self.assertIn(" AND project in (TEAM, DESK) ", jira.jqls[0], args)

    def test_the_heading_names_the_boards_instead_of_one_project(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("TEAM-1", category="done", changed="2026-10-07")]
        _, out, _ = run(["done", "--since", "2026-10-01", "--view", "plataforma"], jira)
        self.assertIn("**Proyecto:** TEAM, DESK", out)

    def test_the_first_board_that_knows_the_person_is_enough(self):
        jira = FakeJira()
        code, _, _ = run(["next", "--person", "Ana Gómez", "--view", "plataforma"], jira)
        self.assertEqual(code, 0)
        self.assertEqual(set(jira.search_projects), {"TEAM"})

    def test_a_person_assignable_only_in_a_later_board_is_still_found(self):
        class ByBoard(FakeJira):
            def search_users(self, query, project=None, limit=100):
                return super().search_users(query, project, limit) if project == "DESK" else []

        jira = ByBoard()
        code, out, err = run(["next", "--person", "Ana Gómez", "--view", "plataforma"], jira)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("DESK", set(jira.search_projects))
        self.assertIn("Ana Gómez", out)

    def test_two_people_are_never_guessed_between_boards(self):
        class Two(FakeJira):
            def search_users(self, query, project=None, limit=100):
                return super().search_users(query, project, limit) if project == "TEAM" else []

        code, _, err = run(["next", "--person", "Martin", "--view", "plataforma"], Two())
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)

    def test_an_unknown_view_is_refused_before_asking_jira(self):
        jira = FakeJira()
        code, _, err = run(["next", "--view", "nada"], jira)
        self.assertEqual(code, 1)
        self.assertIn("jtk team setup nada", err)
        self.assertEqual(jira.jqls, [])

    def test_a_view_and_a_jira_project_together_are_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["next", "--view", "plataforma", "--jira-project", "PLATE"], FakeJira())

    def test_without_the_flag_nothing_changes(self):
        jira = FakeJira()
        run(["next", "--jira-project", "PLATE"], jira)
        self.assertIn(" AND project = PLATE ", jira.jqls[0])


if __name__ == "__main__":
    unittest.main()
