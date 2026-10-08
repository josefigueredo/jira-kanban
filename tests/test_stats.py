from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, FakeJira, issue
from jkan import stats

TODAY = date(2026, 10, 8)  # a Thursday: its week starts on Monday 2026-10-05


class MathTest(unittest.TestCase):
    def test_percentile_is_nearest_rank(self):
        ten = list(range(1, 11))
        self.assertEqual((stats.percentile(ten, 50), stats.percentile(ten, 85)), (5, 9))
        self.assertEqual(stats.spread([4]), {"n": 1, "median": 4, "p85": 4})
        self.assertIsNone(stats.spread([]))

    def test_throughput_buckets_by_monday_and_keeps_empty_weeks(self):
        done = [issue("A", changed="2026-10-07"), issue("B", changed="2026-10-05"), issue("C", changed="2026-09-30"),
                issue("D", changed="2026-09-10"), issue("E", changed=None)]
        self.assertEqual(stats.throughput(done, TODAY, 3), [
            {"week": "2026-09-21", "closed": 0, "partial": False},
            {"week": "2026-09-28", "closed": 1, "partial": False},
            {"week": "2026-10-05", "closed": 2, "partial": True}])

    def test_lead_days_uses_resolution_then_the_last_change(self):
        done = [issue("A", created="2026-10-01", resolved="2026-10-04"), issue("B", created="2026-10-01", changed="2026-10-02"),
                issue("C", created=None)]
        self.assertEqual(stats.lead_days(done), [3, 1])

    def test_wip_age_flags_the_stalled(self):
        open_issues = [issue("A", category="in_progress", changed="2026-10-07"),
                       issue("B", category="in_progress", changed="2026-09-28"), issue("C"),
                       issue("D", category="in_progress", changed=None)]
        rows = stats.wip(open_issues, TODAY)
        self.assertEqual([(r["issue"]["key"], r["days"], r["stalled"]) for r in rows], [("B", 10, True), ("A", 1, False)])

    def test_on_time_only_counts_what_had_a_due_date(self):
        done = [issue("A", duedate="2026-10-05", resolved="2026-10-04"), issue("B", duedate="2026-10-05", resolved="2026-10-06"),
                issue("C", resolved="2026-10-06")]
        self.assertEqual(stats.on_time(done), {"n": 2, "on_time": 1, "pct": 50})
        self.assertIsNone(stats.on_time([issue("C")]))

    def test_mix_reads_the_area_prefix_and_the_type(self):
        done = [issue("A", summary="[BE] x"), issue("B", summary="[AI] y", issuetype="Historia"),
                issue("C", summary="[ZZ] z"), issue("D", summary="sin prefijo")]
        self.assertEqual(stats.mix(done, CONVENTIONS["areas"]),
                         {"by_area": {"BE": 1, "AI": 1, "(sin área)": 2}, "by_type": {"Tarea": 3, "Historia": 1}})

    def test_oldest_open(self):
        rows = stats.oldest([issue("A", created="2026-09-01"), issue("B", created="2026-08-01"), issue("C", created=None)], TODAY, 1)
        self.assertEqual([(r["issue"]["key"], r["days"]) for r in rows], [("B", 68)])


class LoadTest(unittest.TestCase):
    OPEN = [issue("A", category="in_progress"), issue("B", category="in_progress", flagged=True),
            issue("C", duedate="2026-10-01"), issue("D", duedate="2026-10-12"), issue("E", duedate="2026-10-20")]

    def test_numbers_are_counts_of_what_is_open(self):
        numbers = stats.load_numbers([issue("X", changed="2026-10-06")], self.OPEN, TODAY, 2, CONVENTIONS)
        self.assertEqual({k: numbers[k] for k in ("open", "in_progress", "blocked", "overdue", "due_soon")},
                         {"open": 5, "in_progress": 2, "blocked": 1, "overdue": 1, "due_soon": 1})
        self.assertEqual([w["closed"] for w in numbers["weekly"]], [0, 1])
        self.assertIsNone(numbers["verdict"])  # no wip_limit: no verdict invented

    def test_a_wip_limit_gives_room(self):
        self.assertEqual(stats.load_numbers([], self.OPEN, TODAY, 1, dict(CONVENTIONS, wip_limit=3))["verdict"],
                         {"wip_limit": 3, "room": 1})
        self.assertEqual(stats.load_numbers([], self.OPEN, TODAY, 1, dict(CONVENTIONS, wip_limit=2))["verdict"]["room"], 0)


class ComputeTest(unittest.TestCase):
    def test_compute_with_nothing_does_not_crash(self):
        result = stats.compute([], [], TODAY, 4, CONVENTIONS)
        self.assertEqual((result["lead"], result["on_time"], result["wip"], result["oldest"]), (None, None, [], []))
        self.assertEqual(len(result["weekly"]), 4)


class GatherHistoryTest(unittest.TestCase):
    def test_gather_history_drops_epics_and_starts_at_the_first_week(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: ([issue("D", changed="2026-10-06"), issue("E", issuetype="Epic")]
                                          if "statusCategory = Done" in jql else [issue("O"), issue("P", issuetype="Epic")])
        done, open_issues = stats.gather_history(jira, None, TODAY, 3, CONVENTIONS)
        self.assertEqual(([i["key"] for i in done], [i["key"] for i in open_issues]), (["D"], ["O"]))
        self.assertIn('statusCategoryChangedDate >= "2026-09-21"', jira.jqls[0])


if __name__ == "__main__":
    unittest.main()
