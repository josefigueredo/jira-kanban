from __future__ import annotations

import unittest
from datetime import date

import team_fixtures as fx
from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import queries

GROUP = {"group": "team"}


class TeamQueriesTest(unittest.TestCase):
    def test_open_work_is_everything_not_closed_in_each_board_for_the_team_or_nobody(self):
        jql = queries.team_open(["TEAM", "DESK"], fx.profiles(), GROUP)
        self.assertEqual(jql, '((project = TEAM AND status not in (5, 6)) OR (project = DESK AND status not in (15, 16)))'
                              ' AND (assignee in membersOf("team") OR assignee is EMPTY)'
                              ' ORDER BY updated DESC')

    def test_a_board_with_no_closed_status_is_asked_whole(self):
        only_open = {"OPEN": {"statuses": [{"id": "1", "role": "todo"}, {"id": "2", "role": "active"}]}}
        self.assertEqual(queries.team_open(["OPEN"], only_open, None), "((project = OPEN)) ORDER BY updated DESC")

    def test_without_a_team_nobody_is_filtered_out(self):
        jql = queries.team_open(["TEAM"], fx.profiles(), None)
        self.assertEqual(jql, "((project = TEAM AND status not in (5, 6))) ORDER BY updated DESC")

    def test_people_become_quoted_account_ids(self):
        team = {"people": [{"id": "acc-1", "name": "Ana"}, {"id": "acc-2", "name": "Beto"}]}
        self.assertIn('(assignee in ("acc-1", "acc-2") OR assignee is EMPTY)', queries.team_open(["TEAM"], fx.profiles(), team))
        self.assertTrue(queries.team_closed(["TEAM"], fx.profiles(), team, ("delivered",), date(2026, 9, 1))
                        .endswith('AND assignee in ("acc-1", "acc-2") ORDER BY updated DESC'))

    def test_closed_work_names_the_statuses_and_the_day_and_asks_for_the_team_only(self):
        jql = queries.team_closed(["TEAM", "DESK"], fx.profiles(), GROUP, ("delivered",), date(2026, 9, 1))
        self.assertEqual(jql, '((project = TEAM AND status in (5)) OR (project = DESK AND status in (15)))'
                              ' AND updated >= "2026-09-01" AND assignee in membersOf("team")'
                              ' ORDER BY updated DESC')
        dropped = queries.team_closed(["TEAM"], fx.profiles(), GROUP, ("dropped",), date(2026, 9, 1))
        self.assertIn("status in (6)", dropped)

    def test_closed_work_is_none_when_no_board_has_such_a_status(self):
        only_open = {"OPEN": {"statuses": [{"id": "1", "role": "todo"}]}}
        self.assertIsNone(queries.team_closed(["OPEN"], only_open, GROUP, ("delivered",), date(2026, 9, 1)))

    def test_created_covers_the_last_day_too(self):
        jql = queries.team_created(["TEAM", "DESK"], date(2026, 10, 1), date(2026, 10, 8))
        self.assertEqual(jql, 'project in (TEAM, DESK) AND created >= "2026-10-01" AND created < "2026-10-09"'
                              ' ORDER BY created DESC')

    def test_ids_are_sorted_as_numbers_not_as_text(self):
        prof = {"X": {"statuses": [{"id": "10", "role": "delivered"}, {"id": "9", "role": "dropped"}]}}
        self.assertIn("status not in (9, 10)", queries.team_open(["X"], prof, None))

    def test_nothing_from_outside_reaches_the_query(self):
        bad_status = {"X": {"statuses": [{"id": "1) OR (1=1", "role": "delivered"}]}}
        with self.assertRaisesRegex(ValueError, "not status ids"):
            queries.team_open(["X"], bad_status, None)
        with self.assertRaisesRegex(ValueError, "not a project key"):
            queries.team_open(["x y"], {"x y": {"statuses": []}}, None)
        with self.assertRaisesRegex(ValueError, "not a group name"):
            queries.team_scope({"group": 'g") OR (1=1'})
        with self.assertRaisesRegex(ValueError, "not account ids"):
            queries.team_scope({"people": [{"id": 'a" OR "1"="1', "name": "x"}]})
        with self.assertRaisesRegex(ValueError, "not a project key"):
            queries.team_created(["UA", "u a"], date(2026, 10, 1), date(2026, 10, 2))

    def test_no_team_means_no_scope(self):
        self.assertIsNone(queries.team_scope(None))
        self.assertIsNone(queries.team_scope({}))


class ScopeTest(unittest.TestCase):
    def test_a_single_project_reads_as_before(self):
        jql = queries.open_of(None, "PLATE")
        self.assertIn(" AND project = PLATE ", jql)

    def test_a_list_of_projects_is_an_in_clause(self):
        jql = queries.changed_in(None, date(2026, 10, 1), date(2026, 10, 7), ["PLATE", "UA"])
        self.assertIn(" AND project in (PLATE, UA) ", jql)
        self.assertIn(" AND project = UA ", queries.open_of(None, ["UA"]))

    def test_every_key_of_the_list_is_checked(self):
        with self.assertRaisesRegex(ValueError, "not a project key"):
            queries.open_of(None, ["PLATE", "x; drop"])


if __name__ == "__main__":
    unittest.main()
