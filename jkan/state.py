"""Where a plan and the log of writes live: ~/.local/state/jtk (or $JTK_STATE_DIR).

A plan is a file `jtk apply` runs exactly; its id is the start of its hash, and the file is refused if it no longer matches.
The hash catches accidents, it does not authenticate: the approval is asked over what apply shows from the file.
The log is append-only, one JSON line per write; re-applying a plan skips what the log already marks `ok`."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Set

ID = re.compile(r"[0-9a-f]{12}")


class BadPlan(ValueError):
    """The plan file is missing, unreadable or no longer what was planned."""


def state_dir() -> Path:
    return Path(os.environ.get("JTK_STATE_DIR") or Path.home() / ".local" / "state" / "jtk")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(body: dict) -> str:
    core = {k: v for k, v in body.items() if k not in ("hash", "id")}
    text = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_path(plan_id: str) -> Path:
    if not ID.fullmatch(plan_id or ""):
        raise BadPlan(f"{plan_id!r} is not a plan id (12 lower-case hex characters)")
    return state_dir() / "plans" / f"{plan_id}.json"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_plan(body: dict) -> dict:
    full = digest(body)
    plan = dict(body, hash=full, id=full[:12])
    _write_json(plan_path(plan["id"]), plan)
    return plan


def load_plan(plan_id: str) -> dict:
    path = plan_path(plan_id)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BadPlan(f"no plan {plan_id} in {path.parent}") from None
    except (OSError, ValueError) as exc:
        raise BadPlan(f"{path.name} cannot be read: {exc}") from None
    if not isinstance(plan, dict) or plan.get("version") != 1:
        raise BadPlan(f"{path.name} is not a plan this jtk understands")
    if plan.get("hash") != digest(plan) or plan.get("id") != plan_id or str(plan.get("hash", ""))[:12] != plan_id:
        raise BadPlan(f"{path.name} was changed after it was planned (its hash does not match): plan again")
    return plan


def log_path() -> Path:
    return state_dir() / "writes.jsonl"


def can_log() -> bool:
    """True when the log can be appended to: apply asks this before the person approves, not after the first write."""
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8"):
            pass
        return True
    except OSError:
        return False


def log_write(entry: dict, now: Optional[Callable[[], str]] = None) -> bool:
    """Append one line; False when it could not be written (the caller decides how loud to be: the write already happened)."""
    stamp = (now or utc_now)()
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": stamp, "tool": "jtk", **entry}, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def entries(plan_id: str) -> List[dict]:
    try:
        lines = log_path().read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, NotADirectoryError):
        return []
    found = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("plan") == plan_id:
            found.append(entry)
    return found


def applied(plan_id: str) -> Set[str]:
    return {e["key"] for e in entries(plan_id) if e.get("result") == "ok" and "key" in e}
