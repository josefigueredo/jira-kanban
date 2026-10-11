"""--when: a fixed vocabulary for the windows the agent used to compute by hand («ayer», «la semana pasada»).
Weeks run Monday to Sunday, like the skills have always said."""
from __future__ import annotations

import unittest
from datetime import date

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import window

THURSDAY = date(2026, 10, 8)
MONDAY = date(2026, 10, 12)
SUNDAY = date(2026, 10, 11)


class PastWindowTest(unittest.TestCase):
    def test_the_dates_used_below_fall_on_the_weekdays_the_tests_say(self):
        self.assertEqual((THURSDAY.weekday(), MONDAY.weekday(), SUNDAY.weekday()), (3, 0, 6))

    def test_each_name_gives_its_days(self):
        d = lambda m, day: date(2026, m, day)  # noqa: E731
        self.assertEqual(window.past("today", THURSDAY), (d(10, 8), d(10, 8)))
        self.assertEqual(window.past("yesterday", THURSDAY), (d(10, 7), d(10, 7)))
        self.assertEqual(window.past("this-week", THURSDAY), (d(10, 5), d(10, 8)))
        self.assertEqual(window.past("last-week", THURSDAY), (d(9, 28), d(10, 4)))
        self.assertEqual(window.past("this-month", THURSDAY), (d(10, 1), d(10, 8)))
        self.assertEqual(window.past("last-month", THURSDAY), (d(9, 1), d(9, 30)))

    def test_the_edges_of_the_week_and_the_year(self):
        self.assertEqual(window.past("this-week", MONDAY), (MONDAY, MONDAY))
        self.assertEqual(window.past("last-week", MONDAY), (date(2026, 10, 5), SUNDAY))
        self.assertEqual(window.past("this-week", SUNDAY), (date(2026, 10, 5), SUNDAY))
        self.assertEqual(window.past("last-month", date(2026, 1, 15)), (date(2025, 12, 1), date(2025, 12, 31)))
        self.assertEqual(window.past("yesterday", date(2026, 3, 1)), (date(2026, 2, 28), date(2026, 2, 28)))

    def test_an_unknown_name_lists_the_valid_ones(self):
        with self.assertRaises(window.BadWindow) as ctx:
            window.past("ayer", THURSDAY)
        for name in window.PAST:
            self.assertIn(name, str(ctx.exception))


class AheadTest(unittest.TestCase):
    def test_the_horizon_is_a_sunday(self):
        self.assertEqual(window.ahead("today", THURSDAY), THURSDAY)
        self.assertEqual(window.ahead("this-week", THURSDAY), SUNDAY)
        self.assertEqual(window.ahead("next-week", THURSDAY), date(2026, 10, 18))
        self.assertEqual(window.ahead("this-week", SUNDAY), SUNDAY)
        self.assertEqual(window.ahead("next-week", SUNDAY), date(2026, 10, 18))

    def test_a_past_name_is_not_a_horizon(self):
        with self.assertRaises(window.BadWindow) as ctx:
            window.ahead("last-week", THURSDAY)
        self.assertIn("next-week", str(ctx.exception))


class ResolveTest(unittest.TestCase):
    def test_when_or_since_but_exactly_one(self):
        self.assertEqual(window.resolve(None, None, "last-week", THURSDAY), window.past("last-week", THURSDAY))
        self.assertEqual(window.resolve("2026-10-01", "2026-10-03", None, THURSDAY), (date(2026, 10, 1), date(2026, 10, 3)))
        for since, until, when in (("2026-10-01", None, "yesterday"), (None, "2026-10-03", "yesterday"), (None, None, None)):
            with self.assertRaises(window.BadWindow) as ctx:
                window.resolve(since, until, when, THURSDAY)
            self.assertIn("--when", str(ctx.exception))
            self.assertIn("--since", str(ctx.exception))

    def test_the_horizon_takes_when_or_until_but_not_both(self):
        self.assertEqual(window.horizon_for(None, "next-week", THURSDAY), date(2026, 10, 18))
        self.assertEqual(window.horizon_for("2026-10-12", None, THURSDAY), date(2026, 10, 12))
        self.assertEqual(window.horizon_for(None, None, THURSDAY), THURSDAY)
        with self.assertRaises(window.BadWindow):
            window.horizon_for("2026-10-12", "next-week", THURSDAY)


if __name__ == "__main__":
    unittest.main()
