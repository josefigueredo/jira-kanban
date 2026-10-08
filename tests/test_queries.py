from __future__ import annotations

import unittest
from datetime import date

from helpers import ROOT  # noqa: F401
from jkan import queries, window

TODAY = date(2026, 10, 8)


class WindowTest(unittest.TestCase):
    def test_span_defaults_until_to_today(self):
        self.assertEqual(window.span("2026-10-01", None, TODAY), (date(2026, 10, 1), TODAY))

    def test_span_keeps_both_ends(self):
        self.assertEqual(window.span("2026-10-01", "2026-10-03", TODAY), (date(2026, 10, 1), date(2026, 10, 3)))

    def test_since_after_until_is_refused(self):
        with self.assertRaises(window.BadWindow) as ctx:
            window.span("2026-10-05", "2026-10-03", TODAY)
        self.assertIn("after", str(ctx.exception))

    def test_a_phrase_is_not_a_date(self):
        with self.assertRaises(window.BadWindow) as ctx:
            window.parse_day("ayer")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))

    def test_horizon_cannot_be_in_the_past(self):
        self.assertEqual(window.horizon(None, TODAY), TODAY)
        self.assertEqual(window.horizon("2026-10-12", TODAY), date(2026, 10, 12))
        with self.assertRaises(window.BadWindow):
            window.horizon("2026-10-01", TODAY)

    def test_weeks_must_be_between_1_and_52(self):
        self.assertEqual(window.weeks(4), 4)
        for bad in (0, 53, -1):
            with self.assertRaises(window.BadWindow):
                window.weeks(bad)

    def test_today_in_a_bad_zone_falls_back_to_the_local_date(self):
        self.assertIsInstance(window.today_in("Nope/Nowhere"), date)
        self.assertIsInstance(window.today_in(None), date)


class QueryTest(unittest.TestCase):
    def test_changed_in_includes_the_last_day(self):
        self.assertEqual(
            queries.changed_in(None, date(2026, 10, 1), date(2026, 10, 7)),
            'assignee = currentUser() AND statusCategory in ("Done", "In Progress") '
            'AND statusCategoryChangedDate >= "2026-10-01" AND statusCategoryChangedDate < "2026-10-08" '
            "ORDER BY statusCategoryChangedDate DESC")

    def test_a_person_and_a_project_narrow_the_query(self):
        jql = queries.open_of("712020:abc", "PLATE")
        self.assertEqual(jql, 'assignee = "712020:abc" AND project = PLATE AND statusCategory != Done '
                              "ORDER BY priority DESC, duedate ASC")

    def test_done_since(self):
        self.assertEqual(queries.done_since(None, date(2026, 9, 14)),
                         'assignee = currentUser() AND statusCategory = Done AND statusCategoryChangedDate >= '
                         '"2026-09-14" ORDER BY statusCategoryChangedDate DESC')

    def test_unowned_and_by_keys(self):
        self.assertEqual(queries.unowned_in(["PLATE-1", "PLATE-2"]),
                         "parent in (PLATE-1, PLATE-2) AND assignee is EMPTY AND statusCategory != Done "
                         "ORDER BY priority DESC")
        self.assertEqual(queries.by_keys(["PLATE-3"]), "key in (PLATE-3)")

    def test_nothing_user_supplied_can_break_out_of_the_jql(self):
        with self.assertRaises(ValueError):
            queries.open_of('x" OR 1=1 --')
        with self.assertRaises(ValueError):
            queries.open_of(None, "PLATE OR 1=1")
        with self.assertRaises(ValueError):
            queries.by_keys(["PLATE-1) OR (a = b"])
        with self.assertRaises(ValueError):
            queries.by_keys([])


if __name__ == "__main__":
    unittest.main()
