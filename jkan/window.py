"""Dates for the reports: strict ISO days, the windows they make, and today in the team's time zone.

The CLI never reads natural language. It does read a short fixed vocabulary (`--when yesterday`, `--when last-week`): the
agent maps «ayer» to a name and the CLI does the calendar, so a wrong date can't come from the agent counting days.
Weeks run Monday to Sunday.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional, Tuple


class BadWindow(ValueError):
    """A date or a range the reports cannot use; the message says how to fix it."""


def parse_day(text: Optional[str]) -> _dt.date:
    try:
        return _dt.date.fromisoformat(text)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise BadWindow(f"{text!r} is not a date: use YYYY-MM-DD (the agent turns 'ayer' into a date)") from None


def span(since: str, until: Optional[str], today: _dt.date) -> Tuple[_dt.date, _dt.date]:
    start = parse_day(since)
    end = parse_day(until) if until else today
    if start > end:
        raise BadWindow(f"--since {start} is after --until {end}")
    return start, end


def horizon(until: Optional[str], today: _dt.date) -> _dt.date:
    end = parse_day(until) if until else today
    if end < today:
        raise BadWindow(f"--until {end} is before today ({today}): use jtk done for the past")
    return end


def weeks(count: int) -> int:
    if not 1 <= count <= 52:
        raise BadWindow(f"--weeks {count}: use a number from 1 to 52")
    return count


def today_in(zone: Optional[str]) -> _dt.date:
    """Today's date in `zone` (e.g. America/Argentina/Buenos_Aires); the local date when the zone is unknown."""
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo(zone)).date()  # type: ignore[arg-type]
    except (ImportError, KeyError, TypeError, ValueError):
        return _dt.date.today()


PAST = ("today", "yesterday", "this-week", "last-week", "this-month", "last-month")
AHEAD = ("today", "this-week", "next-week")
ONE_OF = "use --since D (and --until D) or --when " + "|".join(PAST)


def past(name: str, today: _dt.date) -> Tuple[_dt.date, _dt.date]:
    """The first and last day of a named window that ends today or before."""
    monday = today - _dt.timedelta(days=today.weekday())
    first_of_month = today.replace(day=1)
    windows = {
        "today": (today, today),
        "yesterday": (today - _dt.timedelta(days=1),) * 2,
        "this-week": (monday, today),
        "last-week": (monday - _dt.timedelta(days=7), monday - _dt.timedelta(days=1)),
        "this-month": (first_of_month, today),
        "last-month": ((first_of_month - _dt.timedelta(days=1)).replace(day=1), first_of_month - _dt.timedelta(days=1)),
    }
    if name not in windows:
        raise BadWindow(f"--when {name!r} is not a window: {', '.join(PAST)}")
    return windows[name]


def ahead(name: str, today: _dt.date) -> _dt.date:
    """The last day of a named window that starts today (the Sunday that closes the week)."""
    sunday = today + _dt.timedelta(days=6 - today.weekday())
    horizons = {"today": today, "this-week": sunday, "next-week": sunday + _dt.timedelta(days=7)}
    if name not in horizons:
        raise BadWindow(f"--when {name!r} does not look ahead: {', '.join(AHEAD)}")
    return horizons[name]


def resolve(since: Optional[str], until: Optional[str], when: Optional[str], today: _dt.date) -> Tuple[_dt.date, _dt.date]:
    """The window of a report that looks back: --when alone, or --since (and --until) alone."""
    if when and (since or until):
        raise BadWindow(f"--when replaces --since and --until: {ONE_OF}")
    if when:
        return past(when, today)
    if not since:
        raise BadWindow(f"no window: {ONE_OF}")
    return span(since, until, today)


def horizon_for(until: Optional[str], when: Optional[str], today: _dt.date) -> _dt.date:
    """The last day of a report that looks ahead: --when, or --until, or today."""
    if when and until:
        raise BadWindow("--when replaces --until: use one of them")
    return ahead(when, today) if when else horizon(until, today)
