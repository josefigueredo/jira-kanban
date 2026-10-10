from __future__ import annotations

import unittest
from datetime import date

import team_fixtures as fx
from helpers import CONVENTIONS, FakeJira, config_dir, issue
from jkan import team

TODAY = fx.TODAY
VIEW = fx.view()


class StatusReportTest(unittest.TestCase):
    def setUp(self):
        self.profiles = fx.profiles(TEAM=2)
        self.report = team.status_report(
            [fx.at("TEAM-1", "todo", assignee=fx.ANA), fx.at("TEAM-2", "active", assignee=fx.ANA),
             fx.at("TEAM-3", "blocked", assignee=fx.ANA), fx.at("TEAM-4", "waiting", assignee=fx.BETO),
             fx.at("TEAM-5", "todo", assignee=None), fx.at("TEAM-6", None, assignee=fx.BETO),
             fx.at("DESK-1", "active", assignee=fx.ANA)], VIEW, self.profiles)

    def test_each_board_counts_its_roles_the_unowned_and_what_has_no_role(self):
        team_board, desk_board = self.report["boards"]
        self.assertEqual({k: team_board[k] for k in ("board", "n", "todo", "active", "blocked", "waiting", "none", "unassigned")},
                         {"board": "TEAM", "n": 6, "todo": 2, "active": 1, "blocked": 1, "waiting": 1, "none": 1, "unassigned": 1})
        self.assertEqual((desk_board["board"], desk_board["n"], desk_board["active"]), ("DESK", 1, 1))
        self.assertEqual(self.report["n"], 7)

    def test_each_person_per_board_with_wip_and_the_room_the_limit_leaves(self):
        rows = {(r["person"], r["board"]): r for r in self.report["people"]}
        self.assertEqual(list(rows), [("Ana Gómez", "DESK"), ("Ana Gómez", "TEAM"), ("Beto Ruiz", "TEAM")])
        ana = rows[("Ana Gómez", "TEAM")]
        self.assertEqual((ana["n"], ana["wip"], ana["wip_limit"], ana["room"]), (3, 2, 2, 0))  # active + blocked
        self.assertEqual((rows[("Ana Gómez", "DESK")]["wip_limit"], rows[("Ana Gómez", "DESK")]["room"]), (None, None))
        beto = rows[("Beto Ruiz", "TEAM")]
        self.assertEqual((beto["wip"], beto["none"], beto["room"]), (1, 1, 1))  # waiting counts; «sin rol» does not

    def test_the_unowned_do_not_appear_as_a_person(self):
        self.assertNotIn(None, [r["person"] for r in self.report["people"]])


class StalledReportTest(unittest.TestCase):
    def issues(self):
        return [fx.at("TEAM-1", "active", changed="2026-09-20", updated="2026-10-07"),
                fx.at("TEAM-2", "active", changed="2026-10-05"),
                fx.at("TEAM-3", "blocked", changed="2026-08-01"),
                fx.at("TEAM-4", "active", changed=None),
                fx.at("TEAM-5", "active", changed="2026-09-20", updated=None)]

    def test_only_active_work_that_has_not_changed_category_for_the_days_asked(self):
        report = team.stalled_report(self.issues(), TODAY, 7)
        self.assertEqual([r["issue"]["key"] for r in report["rows"]], ["TEAM-1", "TEAM-5"])
        self.assertEqual((report["days"], report["n_active"]), (7, 4))

    def test_it_shows_the_days_in_the_category_and_the_days_since_the_last_edit_apart(self):
        first, second = team.stalled_report(self.issues(), TODAY, 7)["rows"]
        self.assertEqual((first["days_in_category"], first["days_since_edit"]), (18, 1))
        self.assertIsNone(second["days_since_edit"])

    def test_a_lower_threshold_brings_more_and_the_oldest_comes_first(self):
        rows = team.stalled_report(self.issues(), TODAY, 3)["rows"]
        self.assertEqual([r["issue"]["key"] for r in rows], ["TEAM-1", "TEAM-5", "TEAM-2"])


class BlockedReportTest(unittest.TestCase):
    def test_blocked_by_role_flag_or_link_and_waiting_apart_and_closed_never(self):
        linked = fx.at("TEAM-2", "active", changed="2026-10-01",
                       blocked_by=[{"key": "UA-9", "summary": "Okta", "status": "En curso", "category": "in_progress",
                                    "assignee": "Ana"}])
        report = team.blocked_report(
            [fx.at("TEAM-1", "blocked", changed="2026-09-28"), linked, fx.at("TEAM-3", "todo", flagged=True, changed="2026-10-07"),
             fx.at("TEAM-4", "waiting", changed="2026-10-02"), fx.at("TEAM-5", "delivered", flagged=True),
             fx.at("TEAM-6", "active")], CONVENTIONS, TODAY)
        self.assertEqual([(r["issue"]["key"], r["by"]) for r in report["blocked"]],
                         [("TEAM-1", "Estado Blocked, sin link"), ("TEAM-2", "UA-9"), ("TEAM-3", "Flagged, sin link")])
        self.assertEqual([r["issue"]["key"] for r in report["waiting"]], ["TEAM-4"])
        self.assertEqual(report["blocked"][0]["days"], 10)

    def test_the_conventions_list_of_blocked_statuses_does_not_apply_to_a_profiled_board(self):
        in_blocked_status_name = fx.at("TEAM-1", "active", status="Blocked")
        self.assertEqual(team.blocked_report([in_blocked_status_name], CONVENTIONS, TODAY)["blocked"], [])


class FlowReportTest(unittest.TestCase):
    def test_deliveries_are_counted_by_their_delivery_day_inside_the_weeks_asked(self):
        delivered = [fx.at("TEAM-1", "delivered", resolved="2026-10-06"), fx.at("TEAM-2", "delivered", resolved="2026-09-29"),
                     fx.at("TEAM-3", "delivered", resolved="2026-09-20"),
                     fx.at("TEAM-4", "delivered", resolved=None, changed="2026-10-07")]
        dropped = [fx.at("TEAM-5", "dropped", changed="2026-10-01"), fx.at("TEAM-6", "dropped", changed="2026-09-01")]
        open_ = [fx.at("TEAM-7", "active", changed="2026-09-30")]
        report = team.flow_report(delivered, dropped, open_, TODAY, 2)
        self.assertEqual((report["since"], report["delivered_n"], report["dropped_n"]), ("2026-09-28", 3, 1))
        self.assertEqual([(w["week"], w["closed"], w["partial"]) for w in report["weekly"]],
                         [("2026-09-28", 1, False), ("2026-10-05", 2, True)])
        self.assertEqual([r["issue"]["key"] for r in report["wip"]], ["TEAM-7"])

    def test_lead_time_goes_from_creation_to_delivery_with_its_n(self):
        delivered = [fx.at("TEAM-1", "delivered", created="2026-10-01", resolved="2026-10-06"),
                     fx.at("TEAM-2", "delivered", created="2026-09-01", resolved="2026-09-29")]
        lead = team.flow_report(delivered, [], [], TODAY, 2)["lead"]
        self.assertEqual((lead["n"], lead["median"], lead["p85"]), (2, 5, 28))

    def test_nothing_delivered_has_no_lead_time(self):
        self.assertIsNone(team.flow_report([], [], [], TODAY, 4)["lead"])


class DigestReportTest(unittest.TestCase):
    def test_the_period_lists_what_was_delivered_dropped_and_created_and_today_s_blocked_and_stalled(self):
        report = team.digest_report(
            [fx.at("TEAM-1", "delivered", resolved="2026-10-02"), fx.at("TEAM-2", "delivered", resolved="2026-09-30")],
            [fx.at("TEAM-3", "dropped", changed="2026-10-08"), fx.at("TEAM-4", "dropped", changed="2026-10-09")],
            [fx.at("TEAM-5", "todo", created="2026-10-01"), fx.at("TEAM-6", "todo", created="2026-09-30")],
            [fx.at("TEAM-7", "blocked"), fx.at("TEAM-8", "waiting"), fx.at("TEAM-9", "active", changed="2026-09-01")],
            CONVENTIONS, date(2026, 10, 1), date(2026, 10, 8), TODAY, 7)
        self.assertEqual(([i["key"] for i in report["delivered"]], [i["key"] for i in report["dropped"]],
                          [i["key"] for i in report["created"]]), (["TEAM-1"], ["TEAM-3"], ["TEAM-5"]))
        self.assertEqual((report["blocked_now"], report["waiting_now"], report["stalled_now"]), (1, 1, 1))
        self.assertEqual((report["since"], report["until"]), ("2026-10-01", "2026-10-08"))


class DeskReportTest(unittest.TestCase):
    def setUp(self):
        self.profiles = fx.profiles()
        self.open = [fx.at("DESK-1", "todo", created="2026-10-07"), fx.at("DESK-2", "active", created="2026-10-01"),
                     fx.at("DESK-3", "blocked", created="2026-09-20"), fx.at("DESK-4", "waiting", created="2026-08-01"),
                     fx.at("DESK-5", "todo", created="2026-09-30", assignee=None), fx.at("TEAM-1", "todo")]
        self.delivered = [fx.at("DESK-9", "delivered", created="2026-10-01", resolved="2026-10-05"),
                          fx.at("DESK-8", "delivered", created="2026-08-01", resolved="2026-08-02")]

    def test_only_help_desk_boards_are_reported_and_what_waits_for_a_third_party_is_not_aged(self):
        report = team.desk_report(self.open, self.delivered, VIEW, self.profiles, TODAY, 4)
        self.assertEqual([r["board"] for r in report["boards"]], ["DESK"])
        row = report["boards"][0]
        self.assertEqual(row["age"], {"0–2 d": 1, "3–7 d": 1, "8–14 d": 1, "15+ d": 1})
        self.assertEqual((row["open"], row["waiting"], row["unassigned"]), (5, 1, 1))

    def test_resolution_time_counts_only_what_was_delivered_inside_the_weeks_asked(self):
        row = team.desk_report(self.open, self.delivered, VIEW, self.profiles, TODAY, 4)["boards"][0]
        self.assertEqual((row["resolved_n"], row["resolution"]["median"]), (1, 4))

    def test_a_view_without_a_help_desk_board_is_refused(self):
        with self.assertRaisesRegex(team.NoDesk, "no help desk board"):
            team.desk_report(self.open, [], fx.view(boards=("TEAM",)), self.profiles, TODAY, 4)


class RollupTest(unittest.TestCase):
    def test_one_row_per_view_with_the_numbers_a_sr_em_compares(self):
        open_ = [fx.at("TEAM-1", "blocked"), fx.at("TEAM-2", "active", changed="2026-09-01"), fx.at("TEAM-3", "todo")]
        delivered = [fx.at("TEAM-4", "delivered", created="2026-10-01", resolved="2026-10-06")]
        row = team.rollup_row(VIEW, open_, delivered, CONVENTIONS, TODAY)
        self.assertEqual({k: row[k] for k in ("view", "open", "blocked", "stalled", "delivered")},
                         {"view": "plataforma", "open": 3, "blocked": 1, "stalled": 1, "delivered": 1})
        self.assertEqual(row["lead"]["p85"], 5)


class GatherTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        self.profiles = fx.profiles()

    def test_open_work_is_asked_in_one_search_epics_are_dropped_and_roles_are_set(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("TEAM-1", status="En curso", status_id="2", category="in_progress"),
                                          issue("TEAM-2", issuetype="Epic")]
        issues, cut = team.gather_open(jira, VIEW, self.profiles, CONVENTIONS)
        self.assertEqual(len(jira.jqls), 1)
        self.assertTrue(jira.jqls[0].startswith("((project = TEAM AND status not in (5, 6)) OR (project = DESK"))
        self.assertEqual(([i["key"] for i in issues], issues[0]["role"], cut), (["TEAM-1"], "active", False))

    def test_a_search_that_reaches_the_cap_says_so(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue(f"TEAM-{n}") for n in range(team.CAP + 1)]
        issues, cut = team.gather_open(jira, VIEW, self.profiles, CONVENTIONS)
        self.assertEqual((len(issues), cut), (team.CAP, True))

    def test_closed_work_is_not_asked_when_no_board_has_such_a_status(self):
        jira = FakeJira()
        no_dropped = {"TEAM": {"statuses": [{"id": "1", "role": "todo"}]}}
        view = fx.view(boards=("TEAM",))
        self.assertEqual(team.gather_closed(jira, view, no_dropped, CONVENTIONS, ("dropped",), date(2026, 9, 1)), ([], False))
        self.assertEqual(jira.jqls, [])

    def test_created_work_is_asked_for_the_window(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("TEAM-1", created="2026-10-02")]
        issues, _ = team.gather_created(jira, VIEW, self.profiles, CONVENTIONS, date(2026, 10, 1), date(2026, 10, 8))
        self.assertIn('created >= "2026-10-01"', jira.jqls[0])
        self.assertEqual([i["key"] for i in issues], ["TEAM-1"])

    def test_missing_profiles_are_listed_in_the_order_of_the_view(self):
        self.assertEqual(team.missing_profiles(VIEW, {"DESK": {}}), ["TEAM"])


if __name__ == "__main__":
    unittest.main()
