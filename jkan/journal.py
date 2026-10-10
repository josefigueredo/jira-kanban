"""jtk's own writes to Jira, one JSON line each in ./.jira-kanban/jira-writes.jsonl (same shape as WayOfWork's log).

Jira's changelog shows the account, not the tool. This log records every write jtk made (what, to which issue, from
which command, when), so a change can at least be ruled in or out as this skill's.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Callable, Optional


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def journal(project: Path, command: str, now: Optional[Callable[[], str]] = None,
            also: Optional[Callable[[dict], None]] = None) -> Callable[[dict], None]:
    """A writer for Jira(journal=...). It never raises: a log that cannot be written must not undo the write.

    `also` gets the same write as `{"command", **entry, "result": "ok"}`: jtk passes state.log_write so the common log
    (~/.local/state/jtk/writes.jsonl) holds everything jtk wrote. That line carries no `plan`, so it is never an applied plan."""
    clock = now or _utc_now

    def write(entry: dict) -> None:
        try:
            path = project / ".jira-kanban" / "jira-writes.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"ts": clock(), "tool": "jira-kanban", "command": command, **entry},
                                        ensure_ascii=False) + "\n")
        except OSError:
            pass
        if also is not None:
            try:
                also({"command": command, **entry, "result": "ok"})
            except Exception:  # noqa: BLE001 — the write to Jira already happened; a second log never undoes it
                pass

    return write
