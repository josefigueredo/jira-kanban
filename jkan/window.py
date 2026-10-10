"""Dates for the reports: strict ISO days, the windows they make, and today in the team's time zone.

The CLI never reads natural language: the agent turns "ayer" or "la semana pasada" into dates (see standup/SKILL.md).
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
