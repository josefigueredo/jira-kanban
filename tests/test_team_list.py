from __future__ import annotations

import unittest

import team_fixtures as fx
from jkan import team

TODAY = fx.TODAY  # 2026-10-08


def open_work():
    return [fx.at("TEAM-1", "active", assignee=fx.ANA, created="2026-09-01"),
            fx.at("TEAM-2", "blocked", assignee=fx.ANA, created="2026-10-06"),
            fx.at("TEAM-3", "todo", assignee=None, created="2026-09-20"),
            fx.at("DESK-1", "todo", assignee=None, created="2026-08-01"),
            fx.at("DESK-2", "waiting", assignee=fx.BETO, created="2026-07-01"),
            fx.at("DESK-3", None, assignee=None, created="2026-10-07")]


def keys(rows):
    return [r["key"] for r in rows]


class ScopeTest(unittest.TestCase):
    def test_without_filters_the_list_has_exactly_what_the_status_report_counted(self):
        issues = open_work()
        rows = team.list_issues(issues, ["TEAM", "DESK"], TODAY)
        report = team.status_report(issues, fx.view(), fx.profiles())
        self.assertEqual(len(rows), report["n"])

    def test_only_the_boards_it_is_given_are_listed(self):
        self.assertEqual(sorted(keys(team.list_issues(open_work(), ["DESK"], TODAY))), ["DESK-1", "DESK-2", "DESK-3"])

    def test_without_filters_a_desk_list_matches_the_open_count_of_the_desk_report(self):
        issues = open_work()
        rows = team.list_issues(issues, ["DESK"], TODAY)
        desk = team.desk_report(issues, [], fx.view(), fx.profiles(), TODAY, 4)
        self.assertEqual(len(rows), desk["boards"][0]["open"])


class RowsTest(unittest.TestCase):
    def test_a_row_carries_what_a_manager_needs_to_decide_who_to_ask(self):
        row = team.list_issues([fx.at("TEAM-1", "active", assignee=fx.ANA, created="2026-10-06")], ["TEAM"], TODAY)[0]
        self.assertEqual(row, {"key": "TEAM-1", "title": "Summary of TEAM-1", "owner": "Ana Gómez", "status": "En curso",
                               "role": "active", "age_days": 2})

    def test_without_owner_without_role_and_without_creation_date_it_says_so_in_data(self):
        row = team.list_issues([fx.at("TEAM-1", None, assignee=None, created=None)], ["TEAM"], TODAY)[0]
        self.assertEqual((row["owner"], row["role"], row["age_days"]), (None, "none", None))

    def test_the_oldest_comes_first_ties_by_key_and_unknown_age_goes_last(self):
        issues = [fx.at("TEAM-9", "todo", created="2026-10-01"), fx.at("TEAM-2", "todo", created="2026-10-01"),
                  fx.at("TEAM-5", "todo", created=None), fx.at("TEAM-7", "todo", created="2026-09-01")]
        self.assertEqual(keys(team.list_issues(issues, ["TEAM"], TODAY)), ["TEAM-7", "TEAM-2", "TEAM-9", "TEAM-5"])


class FiltersTest(unittest.TestCase):
    def test_unassigned_keeps_only_what_has_no_owner(self):
        self.assertEqual(sorted(keys(team.list_issues(open_work(), ["TEAM", "DESK"], TODAY, unassigned=True))),
                         ["DESK-1", "DESK-3", "TEAM-3"])

    def test_older_than_keeps_that_many_days_or_more(self):
        rows = team.list_issues(open_work(), ["TEAM", "DESK"], TODAY, older_than=18)
        self.assertEqual(sorted(keys(rows)), ["DESK-1", "DESK-2", "TEAM-1", "TEAM-3"])
        self.assertEqual(len(team.list_issues(open_work(), ["TEAM"], TODAY, older_than=0)), 3)

    def test_older_than_with_age_roles_leaves_out_what_the_desk_does_not_age(self):
        rows = team.list_issues(open_work(), ["DESK"], TODAY, older_than=15, age_roles=("todo", "active", "blocked"))
        self.assertEqual(keys(rows), ["DESK-1"])  # DESK-2 waits for a third party; DESK-3 has no role

    def test_older_than_15_in_the_desk_matches_the_15_plus_bucket_of_the_report(self):
        issues = open_work()
        rows = team.list_issues(issues, ["DESK"], TODAY, older_than=15, age_roles=("todo", "active", "blocked"))
        desk = team.desk_report(issues, [], fx.view(), fx.profiles(), TODAY, 4)
        self.assertEqual(len(rows), desk["boards"][0]["age"]["15+ d"])

    def test_role_keeps_one_role_and_none_is_the_bucket_without_role(self):
        self.assertEqual(keys(team.list_issues(open_work(), ["TEAM", "DESK"], TODAY, role="blocked")), ["TEAM-2"])
        self.assertEqual(keys(team.list_issues(open_work(), ["TEAM", "DESK"], TODAY, role="none")), ["DESK-3"])

    def test_reporter_keeps_only_what_that_person_reported(self):
        issues = open_work()
        for i in issues:
            i["reporter"] = fx.ANA if i["key"] in ("TEAM-3", "DESK-2") else fx.BETO
        issues.append(fx.at("TEAM-4", "todo", assignee=None, reporter=None))
        self.assertEqual(sorted(keys(team.list_issues(issues, ["TEAM", "DESK"], TODAY, reporter="acc-ana"))),
                         ["DESK-2", "TEAM-3"])
        self.assertEqual(keys(team.list_issues(issues, ["TEAM", "DESK"], TODAY, unassigned=True, reporter="acc-ana")),
                         ["TEAM-3"])

    def test_filters_add_up(self):
        rows = team.list_issues(open_work(), ["TEAM", "DESK"], TODAY, unassigned=True, older_than=18, role="todo")
        self.assertEqual(sorted(keys(rows)), ["DESK-1", "TEAM-3"])

    def test_a_role_that_does_not_exist_is_refused(self):
        with self.assertRaisesRegex(ValueError, "role"):
            team.list_issues(open_work(), ["TEAM"], TODAY, role="delivered")

    def test_a_negative_age_is_refused(self):
        with self.assertRaisesRegex(ValueError, "older-than"):
            team.list_issues(open_work(), ["TEAM"], TODAY, older_than=-1)


if __name__ == "__main__":
    unittest.main()
