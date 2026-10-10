# jira-em fase 3: escritura con guarda, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a manager move, reassign and comment on several issues of their team at once (`jk plan …` then `jk apply <id>`) with a guard that only a person at a real terminal can pass, and put that same guard on the legacy `jk create|push|assign --apply`.

**Architecture:** `plan` only reads Jira and saves a hashed file under `$JK_STATE_DIR` (default `~/.local/state/jk`) with everything a write needs already resolved (status ids, transition id, person id). `apply` loads that file, shows it, asks `guard.confirm` for `APRUEBO <n>` on `/dev/tty`, rereads each issue before writing, and appends to a global log that makes re-applying idempotent. The guard lives in the shared core (`guard.py`, `state.py`); planning and applying are write-side modules (`plan.py`, `applier.py`, `plan_cli.py`) wired in `cli.py`, the composition root.

**Tech Stack:** Python 3 stdlib only (3.9 compatible), `unittest`, the in-repo `FakeJira`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-10-jira-em-fase-3-design.md` (binding). Also `docs/superpowers/specs/2026-10-09-jira-em-design.md` («Guardia de escritura»; the 2026-10-10 spec wins where they differ).

## Global Constraints

- Tests: `python3 -m unittest discover -s tests` must be green on `python3` **and** `/usr/bin/python3` (3.9) after every task. Baseline today: 477 tests.
- The suite never touches the network, the real `~/.config/jk`, the real `~/.local/state/jk` or real Jira. `tests/helpers.py` isolates both directories (Task 2).
- Code, skills and CLI messages in **English**; documentation for people in Rioplatense Spanish (AGENTS.md). Output tokens of apply/plan are English: `applied`, `already there`, `changed`, `ambiguous`, `no path`, `required fields`, `error: …` (the spec's Spanish tokens `aplicado`, `ya estaba`, `cambió`, `ambiguo` map to these).
- Exit codes of `plan`/`apply`: `0` done, `1` refused or something changed or failed, `2` could not (Jira, disk, log), `3` a person must do it (no terminal, not approved). The constant is `guard.EXIT_NEEDS_PERSON`.
- The guard has **no bypass**: no flag, no environment variable, no config file. Only `cli.main(…, confirm=…)` can replace it, and nothing on the command line reaches that parameter.
- Planning never writes to Jira (`FakeJira.writes == []`). The approval token is `APRUEBO <n>` with `n` = writes about to happen; exact match, one attempt.
- Module sides (`tests/test_boundaries.py`): `guard`, `state` are CORE (import no sibling that is READ/WRITE); `plan`, `applier`, `plan_cli` are WRITE (may import READ modules); the READ side never imports WRITE.
- Commits: conventional commits, **no** Co-Authored-By or AI attribution (user's global rule overrides any harness reminder). No push, no merge to `main` without being asked.
- Never print, log or commit Jira credentials (`IC_JIRA_*`). Nothing in this plan may write to a real Jira: the real acceptance (Task 11) is manual, by the user, in a sandbox project.

## Review Focus

Failure modes the spec implies but a straight reading of the tasks would not exercise; each has a test in the task named.

1. **Issue keys that carry JQL** (`TEAM-1) OR project = X`, lowercase, trailing newline): refused before any query runs. → Task 4 (`select`), Task 7 (CLI).
2. **A plan file edited or renamed after planning** (hash/name mismatch, `../` in the id, uppercase hex). → Task 2, Task 7.
3. **Somebody else moved or reassigned the issue between plan and apply**, or the saved transition no longer leads to the planned status. → Task 6.
4. **Re-applying after a partial failure** must retry only what failed and must not re-comment. → Task 6.
5. **State directory unwritable / log unwritable**: plan refuses with exit 2; apply reports exit 2 instead of pretending it recorded. → Task 6, Task 7.

---

### Task 1: The guard

**Files:**
- Create: `jkan/guard.py`
- Create: `tests/test_guard.py`
- Modify: `tests/test_boundaries.py:13` (add `"guard"` to `CORE`)

**Interfaces:**
- Produces: `guard.confirm(n: int, summary: str, command: str, streams=None, open_tty=None) -> None` (returns when approved, raises `guard.NotApproved`); `guard.NotApproved(Exception)`; `guard.APPROVAL = "APRUEBO"`; `guard.EXIT_NEEDS_PERSON = 3`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_guard.py`:

```python
from __future__ import annotations

import inspect
import os
import unittest

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import guard


class Tty:
    """A stand-in for /dev/tty: it answers one line and remembers what it was shown."""

    def __init__(self, answer):
        self.answer, self.shown = answer, []

    def write(self, text):
        self.shown.append(text)

    def flush(self):
        pass

    def readline(self):
        return self.answer + "\n"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Stream:
    """stdin/stdout/stderr: reading from it is a bug, because the approval comes from /dev/tty."""

    def __init__(self, tty=True):
        self.tty = tty

    def isatty(self):
        return self.tty

    def readline(self):
        raise AssertionError("the approval must not be read from stdin")


REAL = (Stream(), Stream(), Stream())


def ask(n, answer, streams=REAL):
    tty = Tty(answer)
    guard.confirm(n, "THE SUMMARY", "jk apply abc", streams=streams, open_tty=lambda: tty)
    return tty


class ApprovalTest(unittest.TestCase):
    def test_the_exact_phrase_with_the_right_number_approves_and_the_person_sees_the_summary(self):
        tty = ask(3, "APRUEBO 3")
        shown = "".join(tty.shown)
        self.assertIn("THE SUMMARY", shown)
        self.assertIn("APRUEBO 3", shown)

    def test_anything_else_is_not_an_approval(self):
        for answer in ("APRUEBO 2", "APRUEBO 4", "aprueba 3", "apruebo 3", "APRUEBO 3 ", " APRUEBO 3", "APRUEBO  3",
                       "APRUEBO 03", "APRUEBO", "si", "yes", ""):
            with self.assertRaisesRegex(guard.NotApproved, "nothing was written", msg=repr(answer)):
                ask(3, answer)

    def test_it_never_reads_stdin(self):
        ask(1, "APRUEBO 1")  # Stream.readline raises if it is touched

    def test_nothing_to_approve_is_a_bug_of_the_caller(self):
        with self.assertRaises(ValueError):
            ask(0, "APRUEBO 0")


class TerminalTest(unittest.TestCase):
    def test_every_standard_stream_must_be_a_terminal(self):
        for streams in ((Stream(False), Stream(), Stream()), (Stream(), Stream(False), Stream()),
                        (Stream(), Stream(), Stream(False))):
            opened = []
            with self.assertRaisesRegex(guard.NotApproved, "Run it yourself"):
                guard.confirm(2, "S", "jk apply abc", streams=streams, open_tty=lambda: opened.append(1))
            self.assertEqual(opened, [])

    def test_the_refusal_prints_the_exact_command_to_run(self):
        with self.assertRaises(guard.NotApproved) as caught:
            guard.confirm(2, "S", "jk apply abc123", streams=(Stream(False),) * 3)
        self.assertIn("  jk apply abc123", str(caught.exception))
        self.assertIn("nothing was written", str(caught.exception))

    def test_a_stream_that_cannot_say_if_it_is_a_terminal_counts_as_not_one(self):
        with self.assertRaises(guard.NotApproved):
            guard.confirm(1, "S", "jk apply abc", streams=(object(), Stream(), Stream()))

    def test_without_dev_tty_it_refuses(self):
        def no_tty():
            raise OSError("Device not configured")

        with self.assertRaisesRegex(guard.NotApproved, "Run it yourself"):
            guard.confirm(1, "S", "jk apply abc", streams=REAL, open_tty=no_tty)


class NoBypassTest(unittest.TestCase):
    def test_the_only_knobs_are_the_streams_and_the_tty_opener_for_tests(self):
        names = list(inspect.signature(guard.confirm).parameters)
        self.assertEqual(names, ["n", "summary", "command", "streams", "open_tty"])

    def test_no_environment_variable_skips_it(self):
        saved = dict(os.environ)
        try:
            for name in ("JK_YES", "JK_APPROVE", "YES", "CI", "FORCE", "JK_ASSUME_YES"):
                os.environ[name] = "1"
            with self.assertRaises(guard.NotApproved):
                guard.confirm(1, "S", "jk apply abc", streams=(Stream(False),) * 3)
        finally:
            os.environ.clear()
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m unittest discover -s tests -p "test_guard.py" 2>&1 | tail -6`
Expected: errors `ImportError: cannot import name 'guard' from 'jkan'` (or `AttributeError`), nothing passes.

- [ ] **Step 3: Implement `jkan/guard.py`**

```python
"""The one gate every write to Jira passes through: a person at a real terminal types «APRUEBO <n>».

The script enforces it, not the model's discipline: with no terminal it writes nothing and prints the command for the
person to run in their own window. The answer is read from /dev/tty (never stdin), once, and must match exactly. There
is no flag, environment variable or config that skips it; tests replace it only through cli.main(confirm=...)."""
from __future__ import annotations

import sys
from typing import Callable, Optional, Sequence

APPROVAL = "APRUEBO"
EXIT_NEEDS_PERSON = 3


class NotApproved(Exception):
    """Nothing was written: there is no terminal, or the person did not type the approval."""


def _is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _open_tty():
    return open("/dev/tty", "r+", encoding="utf-8")


def _needs_terminal(command: str) -> str:
    return ("this write needs a person at an interactive terminal and none is attached; nothing was written.\n"
            f"Run it yourself in a terminal window:\n  {command}")


def confirm(n: int, summary: str, command: str, streams: Optional[Sequence] = None,
            open_tty: Optional[Callable] = None) -> None:
    """Return when a person approved `n` writes; raise NotApproved otherwise. `streams` and `open_tty` exist for tests."""
    if n < 1:
        raise ValueError("there is nothing to approve")
    streams = streams if streams is not None else (sys.stdin, sys.stdout, sys.stderr)
    if not all(_is_tty(s) for s in streams):
        raise NotApproved(_needs_terminal(command))
    try:
        tty = (open_tty or _open_tty)()
    except OSError:
        raise NotApproved(_needs_terminal(command)) from None
    with tty:
        tty.write(f"{summary}\n\nType {APPROVAL} {n} to write {n} change(s) to Jira; anything else cancels: ")
        tty.flush()
        answer = tty.readline().rstrip("\r\n")
    if answer != f"{APPROVAL} {n}":
        raise NotApproved(f"not approved (expected exactly «{APPROVAL} {n}»); nothing was written.")
```

- [ ] **Step 4: Add `guard` to the core in the boundaries test**

In `tests/test_boundaries.py` change the `CORE` line to:

```python
CORE = {"jira", "config", "journal", "people", "guard"}
```

- [ ] **Step 5: Run the guard tests and the whole suite**

Run: `python3 -m unittest discover -s tests -p "test_guard.py" 2>&1 | tail -4`
Expected: `Ran 10 tests … OK`.
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` and `/usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: both `OK` (487 tests).

- [ ] **Step 6: Commit**

```bash
git add jkan/guard.py tests/test_guard.py tests/test_boundaries.py
git commit -m "feat(guard): APRUEBO gate that only a person at a terminal can pass"
```

---

### Task 2: State: plan files and the writes log

**Files:**
- Create: `jkan/state.py`
- Create: `tests/test_state.py`
- Modify: `tests/helpers.py:12-20` (isolate `JK_STATE_DIR` like `JK_CONFIG_DIR`)
- Modify: `tests/test_boundaries.py:13` (add `"state"` to `CORE`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (all in `jkan/state.py`): `BadPlan(ValueError)`; `state_dir() -> Path`; `utc_now() -> str`; `digest(body: dict) -> str`; `plan_path(plan_id: str) -> Path`; `save_plan(body: dict) -> dict` (adds `hash` and `id`); `load_plan(plan_id: str) -> dict`; `log_write(entry: dict, now=None) -> bool`; `entries(plan_id: str) -> List[dict]`; `applied(plan_id: str) -> Set[str]`. In `tests/helpers.py`: `state_dir() -> Path` (fresh isolated dir, sets `JK_STATE_DIR`).

- [ ] **Step 1: Isolate the state directory in the test helpers**

In `tests/helpers.py`, directly under the existing `config_dir()` call (`config_dir()  # every test run starts isolated…`), add:

```python
def state_dir() -> Path:
    """Point jk at an empty state directory, so no test reads or writes the real ~/.local/state/jk."""
    path = Path(tempfile.mkdtemp(prefix="jk-state-"))
    os.environ["JK_STATE_DIR"] = str(path)
    return path


state_dir()  # every test run starts isolated
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_state.py`:

```python
from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from helpers import state_dir
from jkan import state

BODY = {"version": 1, "kind": "move", "view": "plataforma", "created": "2026-10-10T12:00:00Z",
        "options": {"to_role": "active"}, "items": [{"key": "TEAM-1"}], "skipped": []}


class PlanFileTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()

    def test_saving_adds_a_hash_and_a_12_hex_id_that_is_its_prefix(self):
        plan = state.save_plan(BODY)
        self.assertRegex(plan["id"], r"^[0-9a-f]{12}$")
        self.assertEqual(plan["hash"][:12], plan["id"])
        self.assertEqual(plan["hash"], state.digest(BODY))
        self.assertTrue((self.base / "plans" / f"{plan['id']}.json").is_file())

    def test_the_same_content_is_the_same_plan_and_other_content_is_another(self):
        self.assertEqual(state.save_plan(BODY)["id"], state.save_plan(dict(BODY))["id"])
        self.assertNotEqual(state.save_plan(BODY)["id"], state.save_plan(dict(BODY, view="otro"))["id"])

    def test_load_gives_back_what_was_saved(self):
        saved = state.save_plan(BODY)
        self.assertEqual(state.load_plan(saved["id"]), saved)

    def test_a_plan_edited_after_planning_is_refused(self):
        saved = state.save_plan(BODY)
        path = state.plan_path(saved["id"])
        edited = json.loads(path.read_text(encoding="utf-8"))
        edited["items"].append({"key": "TEAM-99"})
        path.write_text(json.dumps(edited), encoding="utf-8")
        with self.assertRaisesRegex(state.BadPlan, "changed after it was planned"):
            state.load_plan(saved["id"])

    def test_a_plan_renamed_to_another_id_is_refused(self):
        saved = state.save_plan(BODY)
        other = "0" * 12
        state.plan_path(saved["id"]).rename(self.base / "plans" / f"{other}.json")
        with self.assertRaisesRegex(state.BadPlan, "changed after it was planned"):
            state.load_plan(other)

    def test_an_id_that_could_walk_out_of_the_folder_is_refused(self):
        for bad in ("../x", "..", "abc", "ABCDEF123456", "abcdef12345g", "abcdef123456\n", "abcdef1234567", ""):
            with self.assertRaisesRegex(state.BadPlan, "not a plan id", msg=repr(bad)):
                state.plan_path(bad)

    def test_a_missing_or_unreadable_plan_says_so(self):
        with self.assertRaisesRegex(state.BadPlan, "no plan"):
            state.load_plan("a" * 12)
        path = state.plan_path("b" * 12)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(state.BadPlan, "cannot be read"):
            state.load_plan("b" * 12)
        path.write_text("[1]", encoding="utf-8")
        with self.assertRaisesRegex(state.BadPlan, "is not a plan"):
            state.load_plan("b" * 12)

    def test_a_state_folder_that_cannot_be_written_raises_an_oserror(self):
        blocker = self.base / "plans"
        blocker.write_text("a file where the folder should be", encoding="utf-8")
        with self.assertRaises(OSError):
            state.save_plan(BODY)


class LogTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()

    def test_every_write_is_one_json_line_with_a_timestamp(self):
        self.assertTrue(state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"}, now=lambda: "T1"))
        self.assertTrue(state.log_write({"plan": "p1", "key": "TEAM-2", "result": "error: boom"}, now=lambda: "T2"))
        lines = (self.base / "writes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[0]), {"ts": "T1", "tool": "jk", "plan": "p1", "key": "TEAM-1", "result": "ok"})
        self.assertEqual(len(lines), 2)
        self.assertRegex(state.utc_now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_applied_are_only_the_ok_entries_of_that_plan(self):
        state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"})
        state.log_write({"plan": "p1", "key": "TEAM-2", "result": "error: boom"})
        state.log_write({"plan": "p2", "key": "TEAM-3", "result": "ok"})
        self.assertEqual(state.applied("p1"), {"TEAM-1"})
        self.assertEqual(state.applied("nada"), set())

    def test_garbage_lines_are_ignored(self):
        state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"})
        with (self.base / "writes.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("not json\n[1]\n\n")
        self.assertEqual([e["key"] for e in state.entries("p1")], ["TEAM-1"])

    def test_a_log_that_cannot_be_written_says_so_instead_of_raising(self):
        with mock.patch.object(state, "state_dir", return_value=self.base / "writes.jsonl"):
            (self.base / "writes.jsonl").write_text("file", encoding="utf-8")
            self.assertFalse(state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"}))

    def test_the_default_location_is_under_the_home_when_the_variable_is_missing(self):
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("JK_STATE_DIR", None)
            self.assertTrue(re.search(r"\.local/state/jk$", str(state.state_dir())))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to see it fail**

Run: `python3 -m unittest discover -s tests -p "test_state.py" 2>&1 | tail -5`
Expected: `ImportError: cannot import name 'state'`.

- [ ] **Step 4: Implement `jkan/state.py`**

```python
"""Where a plan and the log of writes live: ~/.local/state/jk (or $JK_STATE_DIR).

A plan is a file `jk apply` runs exactly; its id is the start of its hash, and the file is refused if it no longer matches.
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
    return Path(os.environ.get("JK_STATE_DIR") or Path.home() / ".local" / "state" / "jk")


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
        raise BadPlan(f"{path.name} is not a plan this jk understands")
    if plan.get("hash") != digest(plan) or plan.get("id") != plan_id or str(plan.get("hash", ""))[:12] != plan_id:
        raise BadPlan(f"{path.name} was changed after it was planned (its hash does not match): plan again")
    return plan


def log_path() -> Path:
    return state_dir() / "writes.jsonl"


def log_write(entry: dict, now: Optional[Callable[[], str]] = None) -> bool:
    """Append one line; False when it could not be written (the caller decides how loud to be: the write already happened)."""
    stamp = (now or utc_now)()
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": stamp, "tool": "jk", **entry}, ensure_ascii=False) + "\n")
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
```

- [ ] **Step 5: Add `state` to the core in the boundaries test**

In `tests/test_boundaries.py` change the `CORE` line to:

```python
CORE = {"jira", "config", "journal", "people", "guard", "state"}
```

- [ ] **Step 6: Run the state tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_state.py" 2>&1 | tail -4`
Expected: `Ran 12 tests … OK`.
Run both full suites as in Task 1, Step 5. Expected: `OK` on both.

- [ ] **Step 7: Commit**

```bash
git add jkan/state.py tests/test_state.py tests/helpers.py tests/test_boundaries.py
git commit -m "feat(state): hashed plan files and an append-only writes log"
```

---

### Task 3: Jira operations for plan and apply, and the fake

**Files:**
- Modify: `jkan/jira.py` (add `transitions`, `transition_by_id`, `add_comment`, `snapshot` after `transition`, line ~256)
- Modify: `tests/helpers.py` (`FakeJira`: new state and methods; `assign` learns about the board and failures)
- Create: `tests/plan_fixtures.py`
- Create: `tests/test_jira_write.py`

**Interfaces:**
- Produces on `Jira` and `FakeJira`: `transitions(key) -> List[{"id": str, "name": str, "to": {"id": str, "name": str}, "required": List[str]}]`; `transition_by_id(key, transition_id: str) -> None`; `add_comment(key, text: str) -> None`; `snapshot(key) -> {"status_id": str, "status": str, "assignee": {"id","name"} | None}`. `Jira.assign(key, None)` already unassigns (sends `{"accountId": null}`).
- `FakeJira` extras: `board: Dict[str, dict]`, `workflow: Dict[str, List[dict]]` (status id → transitions leaving it), `fail_writes: Set[str]`, `put(key, status_id, status, assignee=None)`.
- `tests/plan_fixtures.py`: `workflow(jira, required=None)` (transition id `"<src>><dst>"` between every pair of statuses of each fixture board), `put(jira, key, role, assignee=None) -> dict` (registers the issue in the fake and returns it as a search would).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jira_write.py`:

```python
from __future__ import annotations

import unittest

import plan_fixtures as pf
import team_fixtures as fx
from helpers import FailingJira, FakeJira
from jkan import jira as jira_mod
from test_jira import Recorder, client

TRANSITIONS = {"transitions": [
    {"id": "21", "name": "Start", "to": {"id": "10115", "name": "PROCESANDO"}, "fields": {}},
    {"id": "31", "name": "Close", "to": {"id": "10116", "name": "Done"},
     "fields": {"resolution": {"required": True, "hasDefaultValue": False},
                "assignee": {"required": True, "hasDefaultValue": True},
                "comment": {"required": False, "hasDefaultValue": False}}}]}


class RealJiraTest(unittest.TestCase):
    def test_transitions_say_where_each_one_goes_and_what_it_requires(self):
        jira, rec = client({("GET", "/rest/api/3/issue/PLATE-1/transitions"): TRANSITIONS})
        found = jira.transitions("PLATE-1")
        self.assertEqual(found, [
            {"id": "21", "name": "Start", "to": {"id": "10115", "name": "PROCESANDO"}, "required": []},
            {"id": "31", "name": "Close", "to": {"id": "10116", "name": "Done"}, "required": ["resolution"]}])
        self.assertEqual(rec.calls[0][0], "GET")
        self.assertIn("expand=transitions.fields", rec.calls[0][1])

    def test_a_transition_is_posted_by_its_id_and_journaled(self):
        log = []
        rec = Recorder({("POST", "/rest/api/3/issue/PLATE-1/transitions"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        jira.transition_by_id("PLATE-1", "21")
        self.assertEqual(rec.calls[0], ("POST", "/rest/api/3/issue/PLATE-1/transitions", {"transition": {"id": "21"}}))
        self.assertEqual(log, [{"action": "transition", "key": "PLATE-1", "transition": "21"}])

    def test_a_comment_is_plain_text_on_the_v2_endpoint(self):
        log = []
        rec = Recorder({("POST", "/rest/api/2/issue/PLATE-1/comment"): {"id": "1"}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        jira.add_comment("PLATE-1", "hola")
        self.assertEqual(rec.calls[0], ("POST", "/rest/api/2/issue/PLATE-1/comment", {"body": "hola"}))
        self.assertEqual(log, [{"action": "comment", "key": "PLATE-1"}])

    def test_the_snapshot_is_only_the_status_id_and_the_owner(self):
        owned = {"fields": {"status": {"id": 10115, "name": "PROCESANDO"},
                            "assignee": {"accountId": "acc-ana", "displayName": "Ana Gómez"}}}
        free = {"fields": {"status": {"id": "10041", "name": "Backlog"}, "assignee": None}}
        jira, rec = client({("GET", "/rest/api/3/issue/PLATE-1"): owned, ("GET", "/rest/api/3/issue/PLATE-2"): free})
        self.assertEqual(jira.snapshot("PLATE-1"), {"status_id": "10115", "status": "PROCESANDO",
                                                    "assignee": {"id": "acc-ana", "name": "Ana Gómez"}})
        self.assertEqual(jira.snapshot("PLATE-2"), {"status_id": "10041", "status": "Backlog", "assignee": None})
        self.assertIn("fields=status,assignee", rec.calls[0][1])

    def test_assigning_nobody_unassigns(self):
        rec = Recorder({("PUT", "/rest/api/3/issue/PLATE-1/assignee"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec)
        jira.assign("PLATE-1", None)
        self.assertEqual(rec.calls[0][2], {"accountId": None})


class FakeJiraTest(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()
        pf.workflow(self.jira, required={"1>6": ["resolution"]})
        pf.put(self.jira, "TEAM-1", "todo")

    def test_it_lists_the_transitions_that_leave_the_current_status(self):
        found = {t["id"]: t for t in self.jira.transitions("TEAM-1")}
        self.assertEqual(sorted(found), ["1>2", "1>3", "1>4", "1>5", "1>6"])
        self.assertEqual(found["1>6"]["required"], ["resolution"])
        self.assertEqual(found["1>2"]["to"], {"id": "2", "name": "En curso"})

    def test_a_transition_moves_the_issue_and_is_recorded_as_a_write(self):
        self.jira.transition_by_id("TEAM-1", "1>2")
        self.assertEqual(self.jira.snapshot("TEAM-1")["status_id"], "2")
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2")])

    def test_a_transition_that_does_not_leave_the_current_status_is_refused(self):
        with self.assertRaises(FailingJira):
            self.jira.transition_by_id("TEAM-1", "2>3")
        self.assertEqual(self.jira.writes, [])

    def test_assign_and_comment_show_up_in_the_snapshot_and_the_writes(self):
        self.jira.assign("TEAM-1", "acc-ana")
        self.jira.add_comment("TEAM-1", "hola")
        self.assertEqual(self.jira.snapshot("TEAM-1")["assignee"], {"id": "acc-ana", "name": "Ana Gómez"})
        self.assertEqual(self.jira.writes, [("assign", "TEAM-1", "acc-ana"), ("comment", "TEAM-1", "hola")])
        self.jira.assign("TEAM-1", None)
        self.assertIsNone(self.jira.snapshot("TEAM-1")["assignee"])

    def test_an_issue_marked_to_fail_raises_on_every_kind_of_write(self):
        self.jira.fail_writes.add("TEAM-1")
        for call in (lambda: self.jira.transition_by_id("TEAM-1", "1>2"), lambda: self.jira.assign("TEAM-1", "acc-ana"),
                     lambda: self.jira.add_comment("TEAM-1", "x")):
            with self.assertRaises(FailingJira):
                call()
        self.assertEqual(self.jira.writes, [])

    def test_the_fixture_issue_looks_like_a_search_result(self):
        issue = pf.put(self.jira, "TEAM-2", "active", fx.ANA)
        self.assertEqual((issue["key"], issue["status_id"], issue["role"], issue["assignee"]),
                         ("TEAM-2", "2", "active", fx.ANA))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m unittest discover -s tests -p "test_jira_write.py" 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'plan_fixtures'`.

- [ ] **Step 3: Create `tests/plan_fixtures.py`**

```python
"""Fixtures for the plan and apply tests: a workflow where every status of a fixture board can go to every other one, and
issues registered both in the fake Jira (what snapshot() sees) and in the shape a search returns (what plan selects)."""
from __future__ import annotations

import team_fixtures as fx
from jkan import roles


def workflow(jira, required=None) -> None:
    """Transition ids are '<from>><to>' (1>2 is Backlog -> En curso); `required` maps a transition id to its required fields."""
    for base in fx.BASE.values():
        ids = {str(base + n + 1): name for n, (_, name, _) in enumerate(fx.STATUSES)}
        for src in ids:
            jira.workflow[src] = [{"id": f"{src}>{dst}", "name": f"to {name}", "to": {"id": dst, "name": name},
                                   "required": list((required or {}).get(f"{src}>{dst}", []))}
                                  for dst, name in ids.items() if dst != src]


def put(jira, key: str, role: str, assignee=None, **over) -> dict:
    project = roles.project_of(key)
    status_id = str(fx.BASE[project] + fx.IDS[role])
    jira.put(key, status_id, fx.STATUSES[fx.IDS[role] - 1][1], assignee)
    return fx.at(key, role, assignee=assignee, **over)
```

- [ ] **Step 4: Extend `FakeJira` in `tests/helpers.py`**

In `FakeJira.__init__`, after the `self.groups = …` line, add:

```python
        self.board: Dict[str, dict] = {}  # key -> {"status_id", "status", "assignee"}: what snapshot() sees
        self.workflow: Dict[str, List[dict]] = {}  # status id -> the transitions that leave it
        self.fail_writes: set = set()  # keys whose writes raise, like a Jira that rejects them
```

Replace the existing `assign` method with:

```python
    def assign(self, key: str, account_id: Optional[str]) -> None:
        if key in self.fail_writes:
            raise FailingJira(f"HTTP 400 on assign of {key}")
        self.issues[key]["assignee"] = account_id
        if key in self.board:
            owner = None if account_id is None else {"id": account_id, "name": (self.user(account_id) or {}).get("name", account_id)}
            self.board[key]["assignee"] = owner
        self.writes.append(("assign", key, account_id))
```

After the existing `transition` method (before `def epic_with_children`), add these methods to the class:

```python
    # ---- plan / apply -------------------------------------------------------------------------------------------
    def put(self, key: str, status_id: str, status: str, assignee: Optional[dict] = None) -> str:
        """An issue as snapshot() sees it; `assignee` is {"id", "name"} or None."""
        self.board[key] = {"status_id": status_id, "status": status, "assignee": dict(assignee) if assignee else None}
        self.issues.setdefault(key, {"key": key, "assignee": None})
        return key

    def snapshot(self, key: str) -> dict:
        shot = self.board[key]
        return {"status_id": shot["status_id"], "status": shot["status"],
                "assignee": dict(shot["assignee"]) if shot["assignee"] else None}

    def transitions(self, key: str) -> List[dict]:
        return [dict(t, to=dict(t["to"]), required=list(t.get("required", [])))
                for t in self.workflow.get(self.board[key]["status_id"], [])]

    def transition_by_id(self, key: str, transition_id: str) -> None:
        if key in self.fail_writes:
            raise FailingJira(f"HTTP 400 on transition of {key}")
        chosen = next((t for t in self.workflow.get(self.board[key]["status_id"], []) if t["id"] == transition_id), None)
        if chosen is None:
            raise FailingJira(f"HTTP 400: transition {transition_id} is not available for {key}")
        self.board[key].update(status_id=chosen["to"]["id"], status=chosen["to"]["name"])
        self.writes.append(("transition_id", key, transition_id))

    def add_comment(self, key: str, text: str) -> None:
        if key in self.fail_writes:
            raise FailingJira(f"HTTP 400 on comment of {key}")
        self.writes.append(("comment", key, text))
```

- [ ] **Step 5: Implement the four operations in `jkan/jira.py`**

After the `transition` method (the last method of `Jira`), add:

```python
    def transitions(self, key: str) -> List[dict]:
        """What the issue can do now: id, name, destination and the fields each transition requires. Read only."""
        raw = self._send("GET", f"/rest/api/3/issue/{key}/transitions?expand=transitions.fields").get("transitions", [])
        found = []
        for t in raw:
            to = t.get("to") or {}
            required = sorted(fid for fid, meta in (t.get("fields") or {}).items()
                              if meta.get("required") and not meta.get("hasDefaultValue"))
            found.append({"id": str(t["id"]), "name": t.get("name") or "",
                          "to": {"id": str(to.get("id", "")), "name": to.get("name", "")}, "required": required})
        return found

    def transition_by_id(self, key: str, transition_id: str) -> None:
        self._send("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": transition_id}})
        self._journal({"action": "transition", "key": key, "transition": transition_id})

    def add_comment(self, key: str, text: str) -> None:
        self._send("POST", f"/rest/api/2/issue/{key}/comment", {"body": text})
        self._journal({"action": "comment", "key": key})

    def snapshot(self, key: str) -> dict:
        """The status id and the owner now, which is all apply rereads before a write. Read only."""
        fields = self._send("GET", f"/rest/api/3/issue/{key}?fields=status,assignee")["fields"]
        status, owner = fields.get("status") or {}, fields.get("assignee")
        return {"status_id": str(status.get("id", "")), "status": status.get("name", ""),
                "assignee": {"id": owner["accountId"], "name": owner.get("displayName") or ""} if owner else None}
```

- [ ] **Step 6: Run the new tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_jira_write.py" 2>&1 | tail -4`
Expected: `Ran 11 tests … OK`.
Run both full suites. Expected: `OK` (the old `assign` tests still pass: `FakeJira.assign` keeps its `issues[key]["assignee"]` behavior).

- [ ] **Step 7: Commit**

```bash
git add jkan/jira.py tests/helpers.py tests/plan_fixtures.py tests/test_jira_write.py
git commit -m "feat(jira): transitions by id, comments, and a snapshot of status and owner"
```

---

### Task 4: Plan: selection, move, and the readable summary

**Files:**
- Create: `jkan/plan.py`
- Create: `tests/test_plan.py`
- Modify: `tests/test_boundaries.py:15-17` (add `"plan"` to `WRITE`)

**Interfaces:**
- Consumes: Task 2 `state.utc_now`; Task 3 `Jira.transitions`/`search`; existing `team.list_issues(open_issues, boards, today, unassigned, older_than, role)`, `roles.project_of`, `roles.annotate`, `board_profile.open_statuses`.
- Produces (`jkan/plan.py`): `Refused(ValueError)`; `TO_ROLES`; `CLOSING`; `DEFAULT_MAX = 25`; `LIMIT_MAX = 200`; `check_max(value) -> int`; `select(jira, view, profiles, conv, open_issues, today, keys, unassigned, older_than, role, limit) -> List[dict]`; `check_profiles(selection, profiles) -> None`; `move(jira, view, selection, profiles, to_role, to_status=None, allow_close=False, now=None) -> dict` (plan body, no `id`/`hash` yet); `describe(plan, only=None) -> str`; internal `_route(jira, key, target_ids)` and `_envelope(...)`, reused by Tasks 5 and 8.
- Plan body shape (move): `{"version": 1, "kind": "move", "view": str, "created": str, "options": {"to_role", "to_status", "allow_close"}, "items": [{"key", "from": {"id","name"}, "to": {"id","name","role"}, "transition": str}], "skipped": [{"key", "why", ...}]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plan.py`:

```python
from __future__ import annotations

import unittest

import plan_fixtures as pf
import team_fixtures as fx
from helpers import CONVENTIONS, FakeJira
from jkan import board_profile, plan, state

TODAY = fx.TODAY
NOW = lambda: "2026-10-10T12:00:00Z"  # noqa: E731


class Base(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()
        pf.workflow(self.jira)
        self.profiles = fx.profiles()
        self.view = fx.view()
        self.issues = {}

    def put(self, key, role, assignee=None, **over):
        self.issues[key] = pf.put(self.jira, key, role, assignee, **over)
        return self.issues[key]

    def serve_searches(self):
        """Answer `key in (…)` the way Jira would: the issues we know by those keys."""
        def answer(jql):
            wanted = jql.split("key in (", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
            return [self.issues[k] for k in wanted if k in self.issues]
        self.jira.search_answer = answer

    def select(self, keys=(), open_issues=(), unassigned=False, older_than=None, role=None, limit=25):
        return plan.select(self.jira, self.view, self.profiles, CONVENTIONS, list(open_issues), TODAY, list(keys),
                           unassigned, older_than, role, limit)


class SelectTest(Base):
    def test_explicit_keys_are_fetched_from_jira_in_the_given_order(self):
        self.put("TEAM-2", "todo")
        self.put("TEAM-1", "todo")
        self.serve_searches()
        self.assertEqual([i["key"] for i in self.select(["TEAM-1", "TEAM-2"])], ["TEAM-1", "TEAM-2"])
        self.assertEqual(self.jira.jqls, ["key in (TEAM-1, TEAM-2)"])

    def test_filters_select_from_the_open_issues_of_the_view_oldest_first(self):
        a = self.put("TEAM-1", "todo", created="2026-09-01")
        b = self.put("TEAM-2", "todo", created="2026-08-01")
        c = self.put("TEAM-3", "todo", assignee=fx.ANA, created="2026-07-01")
        got = self.select(open_issues=[a, b, c], unassigned=True)
        self.assertEqual([i["key"] for i in got], ["TEAM-2", "TEAM-1"])
        self.assertEqual(self.jira.jqls, [])  # nothing needed fetching

    def test_keys_and_filters_add_up_without_repeating_an_issue(self):
        a = self.put("TEAM-1", "todo")
        self.put("TEAM-5", "active", fx.ANA)
        self.serve_searches()
        got = self.select(["TEAM-1", "TEAM-5"], open_issues=[a], unassigned=True)
        self.assertEqual([i["key"] for i in got], ["TEAM-1", "TEAM-5"])
        self.assertEqual(self.jira.jqls, ["key in (TEAM-5)"])

    def test_saying_nothing_is_refused_there_is_no_all(self):
        with self.assertRaisesRegex(plan.Refused, "say which issues"):
            self.select()

    def test_an_issue_outside_the_boards_of_the_view_is_refused(self):
        with self.assertRaisesRegex(plan.Refused, r"OTHER-1 is not in the boards of view 'plataforma' \(TEAM, DESK\)"):
            self.select(["OTHER-1"])

    def test_a_key_that_carries_jql_is_refused_before_any_query(self):
        for bad in ("TEAM-1) OR project = X", "team-1", "TEAM-1\n", "TEAM-", "TEAM-1,TEAM-2", "TEAM-1 TEAM-2", "-1", ""):
            with self.assertRaisesRegex(plan.Refused, "is not an issue key", msg=repr(bad)):
                self.select([bad])
        self.assertEqual(self.jira.jqls, [])

    def test_a_key_jira_does_not_show_is_refused(self):
        self.serve_searches()
        with self.assertRaisesRegex(plan.Refused, "TEAM-9"):
            self.select(["TEAM-9"])

    def test_more_than_the_limit_is_refused_and_says_how_to_raise_it(self):
        issues = [self.put(f"TEAM-{n}", "todo") for n in range(1, 4)]
        with self.assertRaisesRegex(plan.Refused, r"3 issues; the limit is 2 \(raise it with --max, up to 200\)"):
            self.select(open_issues=issues, unassigned=True, limit=2)
        self.assertEqual(len(self.select(open_issues=issues, unassigned=True, limit=3)), 3)

    def test_the_filters_matching_nothing_is_refused(self):
        with self.assertRaisesRegex(plan.Refused, "no issue matches"):
            self.select(open_issues=[], unassigned=True)

    def test_max_is_between_1_and_200(self):
        self.assertEqual((plan.check_max(None), plan.check_max(1), plan.check_max(200)), (25, 1, 200))
        for bad in (0, 201, -5):
            with self.assertRaisesRegex(plan.Refused, "--max"):
                plan.check_max(bad)


class ProfileTest(Base):
    def test_a_board_with_undecided_statuses_is_refused_when_it_is_touched(self):
        self.profiles["TEAM"] = fx.profile("TEAM", decide_waiting=False)
        touched = [self.put("TEAM-1", "todo")]
        with self.assertRaisesRegex(plan.Refused, "TEAM has 1 status.*without a role.*jk board set"):
            plan.check_profiles(touched, self.profiles)

    def test_a_board_that_is_not_touched_does_not_matter(self):
        self.profiles["TEAM"] = fx.profile("TEAM", decide_waiting=False)
        plan.check_profiles([self.put("DESK-1", "todo")], self.profiles)


class MoveTest(Base):
    def move(self, keys, to_role="active", **kw):
        selection = [self.put(k, "todo") if k not in self.issues else self.issues[k] for k in keys]
        return plan.move(self.jira, self.view, selection, self.profiles, to_role, now=NOW, **kw)

    def test_a_move_records_the_origin_the_destination_and_the_transition_id(self):
        body = self.move(["TEAM-1"])
        self.assertEqual(body["kind"], "move")
        self.assertEqual((body["view"], body["version"], body["created"]), ("plataforma", 1, "2026-10-10T12:00:00Z"))
        self.assertEqual(body["items"], [{"key": "TEAM-1", "from": {"id": "1", "name": "Backlog"},
                                          "to": {"id": "2", "name": "En curso", "role": "active"}, "transition": "1>2"}])
        self.assertEqual(body["skipped"], [])
        self.assertEqual(body["options"], {"to_role": "active", "to_status": None, "allow_close": False})

    def test_planning_never_writes(self):
        self.move(["TEAM-1", "TEAM-2"])
        self.assertEqual(self.jira.writes, [])

    def test_closing_needs_allow_close_and_the_plan_counts_the_closes(self):
        with self.assertRaisesRegex(plan.Refused, "closes issues: add --allow-close"):
            self.move(["TEAM-1"], "delivered")
        with self.assertRaisesRegex(plan.Refused, "closes issues"):
            self.move(["TEAM-1"], "dropped")
        body = self.move(["TEAM-1"], "delivered", allow_close=True)
        self.assertIn("closes 1", plan.describe(dict(body, id="x" * 12)))

    def test_a_role_that_does_not_exist_is_refused(self):
        with self.assertRaisesRegex(plan.Refused, "role must be one of"):
            self.move(["TEAM-1"], "finished")

    def test_an_issue_already_in_the_destination_is_skipped_not_moved(self):
        self.put("TEAM-1", "active")
        self.put("TEAM-2", "todo")
        body = self.move(["TEAM-1", "TEAM-2"])
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "already there"}])

    def test_two_transitions_to_the_role_make_it_ambiguous_and_to_status_resolves_it(self):
        board_profile.assign(self.profiles["TEAM"], "active", ["Blocked"])  # now En curso (2) and Blocked (3) are both «active»
        selection = [self.put("TEAM-1", "todo")]
        with self.assertRaisesRegex(plan.Refused, "nothing to move: TEAM-1: ambiguous"):
            plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW)
        body = plan.move(self.jira, self.view, selection + [self.put("TEAM-2", "todo")], self.profiles, "active",
                         to_status="2", now=NOW)
        self.assertEqual([(i["key"], i["to"]["id"]) for i in body["items"]], [("TEAM-1", "2"), ("TEAM-2", "2")])
        self.assertEqual(body["options"]["to_status"], "2")

    def test_the_ambiguous_issue_lists_its_options_while_others_still_move(self):
        board_profile.assign(self.profiles["TEAM"], "active", ["Blocked"])  # En curso (2) and Blocked (3) are both «active»
        self.jira.workflow["4"] = [t for t in self.jira.workflow["4"] if t["id"] != "4>3"]  # from «waiting» only 2 is reachable
        a, b = self.put("TEAM-1", "todo"), self.put("TEAM-2", "waiting")
        body = plan.move(self.jira, self.view, [a, b], self.profiles, "active", now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "ambiguous",
                                            "options": ["Blocked (transition 1>3)", "En curso (transition 1>2)"]}])

    def test_to_status_must_play_the_role_asked(self):
        with self.assertRaisesRegex(plan.Refused, "status 3 of TEAM does not play the role active"):
            self.move(["TEAM-1"], to_status="3")

    def test_when_nothing_can_move_the_plan_is_refused_with_every_reason(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-3", "blocked")
        self.jira.workflow["1"] = []
        self.jira.workflow["3"] = [dict(t, required=["resolution"]) if t["to"]["id"] == "2" else t for t in self.jira.workflow["3"]]
        with self.assertRaises(plan.Refused) as caught:
            plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-3"]], self.profiles, "active", now=NOW)
        self.assertIn("TEAM-1: no path", str(caught.exception))
        self.assertIn("TEAM-3: required fields", str(caught.exception))

    def test_a_mixed_selection_keeps_what_can_move_and_lists_the_rest(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-3", "blocked")
        self.jira.workflow["3"] = [dict(t, required=["resolution"]) if t["to"]["id"] == "2" else t for t in self.jira.workflow["3"]]
        body = plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-3"]], self.profiles, "active", now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-1"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-3", "why": "required fields", "fields": ["resolution"]}])


class DescribeTest(Base):
    def test_the_summary_names_every_issue_what_changes_and_what_was_left_out(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-2", "active")
        body = plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-2"]], self.profiles, "active", now=NOW)
        text = plan.describe(dict(body, id="abcdef123456"))
        self.assertIn("Plan abcdef123456 · move · view plataforma · 1 issue(s)", text)
        self.assertIn("TEAM-1: Backlog -> En curso", text)
        self.assertIn("Left out:", text)
        self.assertIn("TEAM-2: already there", text)

    def test_only_shows_just_those_issues(self):
        self.put("TEAM-1", "todo")
        self.put("TEAM-2", "todo")
        body = plan.move(self.jira, self.view, [self.issues["TEAM-1"], self.issues["TEAM-2"]], self.profiles, "active", now=NOW)
        text = plan.describe(dict(body, id="abcdef123456"), only=["TEAM-2"])
        self.assertIn("1 issue(s)", text)
        self.assertNotIn("TEAM-1:", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m unittest discover -s tests -p "test_plan.py" 2>&1 | tail -5`
Expected: `ImportError: cannot import name 'plan'`.

- [ ] **Step 3: Implement `jkan/plan.py` (selection, move, describe)**

```python
"""Plans: what `jk plan move|assign|comment|revert` decides about a selection of issues, written as a file `jk apply` runs
exactly. Planning only reads Jira. Everything a write needs (the status it leaves and reaches, the transition id, the person)
is resolved here, once; apply never evaluates the query again."""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from . import board_profile, roles, state, team

KEY = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
TO_ROLES = ("todo", "active", "blocked", "waiting", "delivered", "dropped")
CLOSING = ("delivered", "dropped")
DEFAULT_MAX, LIMIT_MAX = 25, 200
MAX_TEXT = 30000


class Refused(ValueError):
    """The plan cannot be made as asked; nothing was saved."""


def check_max(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_MAX
    if not 1 <= value <= LIMIT_MAX:
        raise Refused(f"--max must be between 1 and {LIMIT_MAX}")
    return value


def select(jira, view: dict, profiles: Dict[str, dict], conv: dict, open_issues: List[dict], today, keys: List[str],
           unassigned: bool, older_than: Optional[int], role: Optional[str], limit: int) -> List[dict]:
    """The issues the plan is about: what the filters pick out of the open issues, then the explicit keys, each once."""
    filtering = unassigned or older_than is not None or role is not None
    if not keys and not filtering:
        raise Refused("say which issues: pass keys or at least one of --unassigned, --older-than, --role")
    for key in keys:
        if not KEY.fullmatch(key):
            raise Refused(f"{key!r} is not an issue key")
        if roles.project_of(key) not in view["boards"]:
            raise Refused(f"{key} is not in the boards of view {view['name']!r} ({', '.join(view['boards'])})")
    chosen: Dict[str, dict] = {}
    if filtering:
        by_key = {i["key"]: i for i in open_issues}
        for row in team.list_issues(open_issues, view["boards"], today, unassigned, older_than, role):
            chosen[row["key"]] = by_key[row["key"]]
    missing = [k for k in dict.fromkeys(keys) if k not in chosen]
    if missing:
        found = {i["key"]: i for i in roles.annotate(jira.search(f"key in ({', '.join(missing)})"), profiles)}
        absent = [k for k in missing if k not in found]
        if absent:
            raise Refused(f"Jira does not show {', '.join(absent)}")
        for key in missing:
            chosen[key] = found[key]
    selection = list(chosen.values())
    if not selection:
        raise Refused("no issue matches")
    if len(selection) > limit:
        raise Refused(f"{len(selection)} issues; the limit is {limit} (raise it with --max, up to {LIMIT_MAX})")
    return selection


def check_profiles(selection: List[dict], profiles: Dict[str, dict]) -> None:
    for board in sorted({roles.project_of(i["key"]) for i in selection}):
        pending = board_profile.open_statuses(profiles[board])
        if pending:
            raise Refused(f"the profile of {board} has {len(pending)} status(es) without a role: decide them with "
                          f"jk board set before planning a write")


def _envelope(kind: str, view: dict, options: dict, items: List[dict], skipped: List[dict],
              now: Optional[Callable[[], str]] = None) -> dict:
    return {"version": 1, "kind": kind, "view": view["name"], "created": (now or state.utc_now)(),
            "options": options, "items": items, "skipped": skipped}


def _why(skipped: List[dict]) -> str:
    return "; ".join(f"{s['key']}: {s['why']}" for s in skipped)


def _route(jira, key: str, target_ids: List[str]):
    """The one transition from where the issue is to one of `target_ids`, or the reason there is none."""
    options = [t for t in jira.transitions(key) if t["to"]["id"] in target_ids]
    if not options:
        return None, {"key": key, "why": "no path"}
    if len(options) > 1:
        return None, {"key": key, "why": "ambiguous",
                      "options": sorted(f"{t['to']['name']} (transition {t['id']})" for t in options)}
    if options[0]["required"]:
        return None, {"key": key, "why": "required fields", "fields": options[0]["required"]}
    return options[0], None


def move(jira, view: dict, selection: List[dict], profiles: Dict[str, dict], to_role: str,
         to_status: Optional[str] = None, allow_close: bool = False,
         now: Optional[Callable[[], str]] = None) -> dict:
    if to_role not in TO_ROLES:
        raise Refused(f"role must be one of {', '.join(TO_ROLES)}, not {to_role!r}")
    if to_role in CLOSING and not allow_close:
        raise Refused(f"moving to {to_role} closes issues: add --allow-close")
    items, skipped = [], []
    for issue in selection:
        profile = profiles[roles.project_of(issue["key"])]
        targets = [s["id"] for s in profile["statuses"] if s["role"] == to_role]
        if to_status is not None:
            if to_status not in targets:
                raise Refused(f"status {to_status} of {profile['project']} does not play the role {to_role}")
            targets = [to_status]
        if not targets:
            skipped.append({"key": issue["key"], "why": f"{profile['project']} has no status with the role {to_role}"})
        elif issue["status_id"] in targets:
            skipped.append({"key": issue["key"], "why": "already there"})
        else:
            chosen, skip = _route(jira, issue["key"], targets)
            if skip:
                skipped.append(skip)
                continue
            items.append({"key": issue["key"], "from": {"id": issue["status_id"], "name": issue["status"]},
                          "to": {"id": chosen["to"]["id"], "name": chosen["to"]["name"], "role": to_role},
                          "transition": chosen["id"]})
    if not items:
        raise Refused("nothing to move: " + _why(skipped))
    return _envelope("move", view, {"to_role": to_role, "to_status": to_status, "allow_close": allow_close},
                     items, skipped, now)


def _who(person: Optional[dict]) -> str:
    return person["name"] if person else "unassigned"


def describe(plan: dict, only: Optional[List[str]] = None) -> str:
    """What the plan will do, in words. Apply shows this before asking for the approval."""
    items = [i for i in plan["items"] if only is None or i["key"] in only]
    head = f"Plan {plan['id']} · {plan['kind']} · view {plan['view']} · {len(items)} issue(s)"
    if plan["kind"] == "move":
        closes = sum(1 for i in items if i["to"].get("role") in CLOSING)
        head += f" · closes {closes}" if closes else ""
        rows = [f"  {i['key']}: {i['from']['name']} -> {i['to']['name']}" for i in items]
    elif plan["kind"] == "assign":
        rows = [f"  {i['key']}: {_who(i['from'])} -> {_who(i['to'])}" for i in items]
    else:
        rows = [f"  {i['key']}" for i in items] + [f"  Comment: {plan['options']['text']}"]
    lines = [head] + rows
    if plan.get("skipped"):
        lines.append("Left out:")
        for skip in plan["skipped"]:
            extra = f" ({', '.join(skip['options'])})" if skip.get("options") else ""
            extra += f" ({', '.join(skip['fields'])})" if skip.get("fields") else ""
            lines.append(f"  {skip['key']}: {skip['why']}{extra}")
    return "\n".join(lines)
```

- [ ] **Step 4: Add `plan` to the write side in the boundaries test**

In `tests/test_boundaries.py` change the `WRITE` line to:

```python
WRITE = {"sync", "spec", "description", "evidence", "kanban", "template", "preview", "plan"}
```

- [ ] **Step 5: Run the plan tests, then fix what the draft got wrong**

Run: `python3 -m unittest discover -s tests -p "test_plan.py" 2>&1 | tail -15`
Expected: all pass. If `test_the_ambiguous_issue_lists_its_options_when_others_can_move` fails, read the failure before touching code: the test builds TEAM-2 as «Done» (status id `5`) so that both `5>2` and `5>3` reach a role-`active` status, while TEAM-1 (Backlog, id `1`) only reaches `2` after the `1>3` transition was removed from its workflow; adjust the fixture lines of that test, not `plan.move`.

- [ ] **Step 6: Run both suites**

Run both full suites as in Task 1, Step 5. Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add jkan/plan.py tests/test_plan.py tests/test_boundaries.py
git commit -m "feat(plan): select issues and plan a move by status id and transition id"
```

---

### Task 5: Plan: assign and comment

**Files:**
- Modify: `jkan/plan.py` (add `assign`, `comment`)
- Modify: `tests/test_plan.py` (new test classes)

**Interfaces:**
- Consumes: Task 4 `_envelope`, `_why`, `Refused`, `MAX_TEXT`, `describe`.
- Produces: `plan.assign(view, selection, person, now=None) -> dict` where `person` is `{"id","name",…}` as `people.resolve_in` returns; `plan.comment(view, selection, text, now=None) -> dict`.
- Plan body shapes: assign `{"kind": "assign", "options": {"person": {"id","name"}}, "items": [{"key", "from": {"id","name"}|None, "to": {"id","name"}}], "skipped": […]}`; comment `{"kind": "comment", "options": {"text": str}, "items": [{"key"}], "skipped": []}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan.py`, before the `if __name__` block:

```python
ANA = {"id": "acc-ana", "name": "Ana Gómez", "email": "ana@example.com", "score": 1.0, "exact": True}


class AssignTest(Base):
    def test_an_assign_records_who_had_it_and_who_gets_it(self):
        a = self.put("TEAM-1", "todo")
        b = self.put("TEAM-2", "todo", fx.BETO)
        body = plan.assign(self.view, [a, b], ANA, now=NOW)
        self.assertEqual(body["kind"], "assign")
        self.assertEqual(body["options"], {"person": {"id": "acc-ana", "name": "Ana Gómez"}})
        self.assertEqual(body["items"], [
            {"key": "TEAM-1", "from": None, "to": {"id": "acc-ana", "name": "Ana Gómez"}},
            {"key": "TEAM-2", "from": {"id": "acc-beto", "name": "Beto Ruiz"}, "to": {"id": "acc-ana", "name": "Ana Gómez"}}])

    def test_who_already_has_it_is_left_out_and_if_all_do_there_is_no_plan(self):
        a = self.put("TEAM-1", "todo", fx.ANA)
        b = self.put("TEAM-2", "todo")
        body = plan.assign(self.view, [a, b], ANA, now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "already there"}])
        with self.assertRaisesRegex(plan.Refused, "nothing to assign: TEAM-1: already there"):
            plan.assign(self.view, [a], ANA, now=NOW)

    def test_the_summary_reads_from_to(self):
        a = self.put("TEAM-1", "todo")
        text = plan.describe(dict(plan.assign(self.view, [a], ANA, now=NOW), id="abcdef123456"))
        self.assertIn("TEAM-1: unassigned -> Ana Gómez", text)


class CommentTest(Base):
    def test_a_comment_keeps_the_text_once_and_one_item_per_issue(self):
        a, b = self.put("TEAM-1", "todo"), self.put("TEAM-2", "active")
        body = plan.comment(self.view, [a, b], "  Revisamos esto el jueves.  ", now=NOW)
        self.assertEqual(body["kind"], "comment")
        self.assertEqual(body["options"], {"text": "Revisamos esto el jueves."})
        self.assertEqual(body["items"], [{"key": "TEAM-1"}, {"key": "TEAM-2"}])

    def test_an_empty_or_huge_text_is_refused(self):
        a = self.put("TEAM-1", "todo")
        for bad in ("", "   ", "\n\t"):
            with self.assertRaisesRegex(plan.Refused, "the comment is empty"):
                plan.comment(self.view, [a], bad, now=NOW)
        with self.assertRaisesRegex(plan.Refused, "too long"):
            plan.comment(self.view, [a], "x" * (plan.MAX_TEXT + 1), now=NOW)

    def test_the_summary_shows_the_text_that_will_be_posted(self):
        a = self.put("TEAM-1", "todo")
        text = plan.describe(dict(plan.comment(self.view, [a], "hola equipo", now=NOW), id="abcdef123456"))
        self.assertIn("Comment: hola equipo", text)
        self.assertIn("TEAM-1", text)
```

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_plan.py" 2>&1 | tail -6`
Expected: `AttributeError: module 'jkan.plan' has no attribute 'assign'` for the new tests.

- [ ] **Step 3: Implement**

In `jkan/plan.py`, after `move` and before `_who`, add:

```python
def assign(view: dict, selection: List[dict], person: dict, now: Optional[Callable[[], str]] = None) -> dict:
    target = {"id": person["id"], "name": person["name"]}
    items, skipped = [], []
    for issue in selection:
        owner = issue.get("assignee")
        if owner and owner["id"] == person["id"]:
            skipped.append({"key": issue["key"], "why": "already there"})
        else:
            items.append({"key": issue["key"], "from": {"id": owner["id"], "name": owner["name"]} if owner else None,
                          "to": dict(target)})
    if not items:
        raise Refused("nothing to assign: " + _why(skipped))
    return _envelope("assign", view, {"person": target}, items, skipped, now)


def comment(view: dict, selection: List[dict], text: str, now: Optional[Callable[[], str]] = None) -> dict:
    clean = (text or "").strip()
    if not clean:
        raise Refused("the comment is empty")
    if len(clean) > MAX_TEXT:
        raise Refused(f"the comment is too long ({len(clean)} characters; the limit is {MAX_TEXT})")
    return _envelope("comment", view, {"text": clean}, [{"key": i["key"]} for i in selection], [], now)
```

- [ ] **Step 4: Run the tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_plan.py" 2>&1 | tail -4` → `OK`.
Run both full suites. Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add jkan/plan.py tests/test_plan.py
git commit -m "feat(plan): plan an assign and a comment"
```

---

### Task 6: Apply engine

**Files:**
- Create: `jkan/applier.py`
- Create: `tests/test_applier.py`
- Modify: `tests/test_boundaries.py` (add `"applier"` to `WRITE`)

**Interfaces:**
- Consumes: Task 1 `guard.NotApproved`; Task 2 `state.applied/log_write`; Task 3 `Jira.snapshot/transitions/transition_by_id/assign/add_comment`; Task 4 `plan.describe`.
- Produces: `applier.run(jira, plan, confirm, command, now=None) -> (outcomes: List[{"key","result"}], code: int)` where `result` is one of `applied`, `already there`, `already applied`, `changed`, `error: …`, and `code` is 0/1/2; `applier.render(outcomes) -> str`. `confirm` has the signature of `guard.confirm` (`confirm(n, summary, command)`); `NotApproved` propagates out of `run` untouched with nothing written.
- Log entry written for each write attempt: `{"command": "apply", "plan", "key", "action", "result": "ok" | "error: …", "de": <from>, "a": <to>}` (no `de`/`a` for comments).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_applier.py`:

```python
from __future__ import annotations

import unittest
from unittest import mock

import plan_fixtures as pf
import team_fixtures as fx
from helpers import FakeJira, state_dir
from jkan import applier, guard, plan, state

NOW = lambda: "2026-10-10T12:00:00Z"  # noqa: E731
ANA = {"id": "acc-ana", "name": "Ana Gómez", "email": "a@x", "score": 1.0, "exact": True}


class Approver:
    """A confirm() that approves and remembers what it was asked."""

    def __init__(self):
        self.calls = []

    def __call__(self, n, summary, command):
        self.calls.append((n, summary, command))


def refuse(n, summary, command):
    raise guard.NotApproved("not approved; nothing was written.")


class Base(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.jira = FakeJira()
        pf.workflow(self.jira)
        self.profiles = fx.profiles()
        self.view = fx.view()
        self.issues = {}
        self.approve = Approver()

    def put(self, key, role, assignee=None):
        self.issues[key] = pf.put(self.jira, key, role, assignee)
        return self.issues[key]

    def saved_move(self, keys, role="active", to="active"):
        selection = [self.put(k, role) for k in keys]
        return state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, to, now=NOW))

    def run(self, saved, confirm=None):
        return applier.run(self.jira, saved, confirm or self.approve, f"jk apply {saved['id']}", now=NOW)


class MoveTest(Base):
    def test_it_applies_exactly_the_saved_transition_and_logs_what_changed(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        outcomes, code = self.run(saved)
        self.assertEqual(code, 0)
        self.assertEqual(outcomes, [{"key": "TEAM-1", "result": "applied"}, {"key": "TEAM-2", "result": "applied"}])
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2"), ("transition_id", "TEAM-2", "1>2")])
        entry = state.entries(saved["id"])[0]
        self.assertEqual((entry["command"], entry["key"], entry["action"], entry["result"]), ("apply", "TEAM-1", "move", "ok"))
        self.assertEqual((entry["de"]["id"], entry["a"]["id"]), ("1", "2"))

    def test_the_person_is_asked_once_with_the_real_count_the_summary_and_the_command(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        self.run(saved)
        n, summary, command = self.approve.calls[0]
        self.assertEqual((len(self.approve.calls), n, command), (1, 2, f"jk apply {saved['id']}"))
        self.assertIn("TEAM-1: Backlog -> En curso", summary)

    def test_without_approval_nothing_is_written_and_nothing_is_logged(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        with self.assertRaises(guard.NotApproved):
            self.run(saved, refuse)
        self.assertEqual(self.jira.writes, [])
        self.assertEqual(state.entries(saved["id"]), [])

    def test_an_issue_somebody_moved_after_planning_is_left_alone(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2"], role="todo")
        self.jira.board["TEAM-1"].update(status_id="3", status="Blocked")
        outcomes, code = self.run(saved)
        self.assertEqual(outcomes, [{"key": "TEAM-1", "result": "changed"}, {"key": "TEAM-2", "result": "applied"}])
        self.assertEqual(code, 1)
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-2", "1>2")])

    def test_an_issue_already_in_the_destination_is_not_touched_and_is_not_a_failure(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.jira.board["TEAM-1"].update(status_id="2", status="En curso")
        outcomes, code = self.run(saved)
        self.assertEqual((outcomes, code), ([{"key": "TEAM-1", "result": "already there"}], 0))
        self.assertEqual(self.jira.writes, [])

    def test_a_saved_transition_that_no_longer_reaches_the_planned_status_is_not_used(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.jira.workflow["1"] = [dict(t, to={"id": "5", "name": "Done"}) if t["id"] == "1>2" else t
                                   for t in self.jira.workflow["1"]]  # same id, different destination
        outcomes, code = self.run(saved)
        self.assertEqual((outcomes, code), ([{"key": "TEAM-1", "result": "changed"}], 1))
        self.assertEqual(self.jira.writes, [])

    def test_a_saved_transition_that_disappeared_is_not_used(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.jira.workflow["1"] = [t for t in self.jira.workflow["1"] if t["id"] != "1>2"]
        self.assertEqual(self.run(saved)[0], [{"key": "TEAM-1", "result": "changed"}])

    def test_one_failure_does_not_stop_the_others_and_the_code_is_not_zero(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2", "TEAM-3"], role="todo")
        self.jira.fail_writes.add("TEAM-2")
        outcomes, code = self.run(saved)
        self.assertEqual([o["result"].split(":")[0] for o in outcomes], ["applied", "error", "applied"])
        self.assertEqual(code, 1)
        self.assertEqual(sorted(state.applied(saved["id"])), ["TEAM-1", "TEAM-3"])
        failed = [e for e in state.entries(saved["id"]) if e["key"] == "TEAM-2"][0]
        self.assertTrue(failed["result"].startswith("error: "))


class ReapplyTest(Base):
    def test_reapplying_retries_only_what_failed_and_asks_for_that_count(self):
        saved = self.saved_move(["TEAM-1", "TEAM-2", "TEAM-3"], role="todo")
        self.jira.fail_writes.add("TEAM-2")
        self.run(saved)
        self.jira.fail_writes.clear()
        self.jira.writes.clear()
        again = Approver()
        outcomes, code = self.run(saved, again)
        self.assertEqual([(o["key"], o["result"]) for o in outcomes],
                         [("TEAM-1", "already applied"), ("TEAM-2", "applied"), ("TEAM-3", "already applied")])
        self.assertEqual((code, again.calls[0][0]), (0, 1))
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-2", "1>2")])

    def test_a_plan_that_is_fully_applied_asks_nothing_and_writes_nothing(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        self.run(saved)
        self.jira.writes.clear()
        again = Approver()
        outcomes, code = self.run(saved, again)
        self.assertEqual((outcomes, code, again.calls, self.jira.writes),
                         ([{"key": "TEAM-1", "result": "already applied"}], 0, [], []))


class AssignTest(Base):
    def saved(self, owner):
        selection = [self.put("TEAM-1", "todo", owner)]
        return state.save_plan(plan.assign(self.view, selection, ANA, now=NOW))

    def test_it_assigns_and_logs_who_had_it(self):
        saved = self.saved(fx.BETO)
        outcomes, code = self.run(saved)
        self.assertEqual((outcomes, code), ([{"key": "TEAM-1", "result": "applied"}], 0))
        self.assertEqual(self.jira.writes, [("assign", "TEAM-1", "acc-ana")])
        entry = state.entries(saved["id"])[0]
        self.assertEqual((entry["action"], entry["de"]["id"], entry["a"]["id"]), ("assign", "acc-beto", "acc-ana"))

    def test_somebody_else_took_it_meanwhile(self):
        saved = self.saved(fx.BETO)
        self.jira.board["TEAM-1"]["assignee"] = {"id": "acc-other", "name": "Otra"}
        self.assertEqual(self.run(saved)[0], [{"key": "TEAM-1", "result": "changed"}])
        self.assertEqual(self.jira.writes, [])

    def test_it_is_already_theirs(self):
        saved = self.saved(None)
        self.jira.board["TEAM-1"]["assignee"] = {"id": "acc-ana", "name": "Ana Gómez"}
        self.assertEqual(self.run(saved), ([{"key": "TEAM-1", "result": "already there"}], 0))

    def test_a_plan_whose_target_is_nobody_unassigns(self):
        self.put("TEAM-1", "todo", fx.ANA)
        body = {"version": 1, "kind": "assign", "view": "plataforma", "created": NOW(), "options": {"person": None},
                "items": [{"key": "TEAM-1", "from": {"id": "acc-ana", "name": "Ana Gómez"}, "to": None}], "skipped": []}
        self.assertEqual(self.run(state.save_plan(body))[0], [{"key": "TEAM-1", "result": "applied"}])
        self.assertEqual(self.jira.writes, [("assign", "TEAM-1", None)])


class CommentTest(Base):
    def test_a_comment_is_posted_once_even_if_the_plan_is_applied_again(self):
        selection = [self.put("TEAM-1", "todo"), self.put("TEAM-2", "todo")]
        saved = state.save_plan(plan.comment(self.view, selection, "hola", now=NOW))
        self.run(saved)
        self.run(saved)
        self.assertEqual(self.jira.writes, [("comment", "TEAM-1", "hola"), ("comment", "TEAM-2", "hola")])
        self.assertNotIn("de", state.entries(saved["id"])[0])


class LogTest(Base):
    def test_a_log_that_cannot_be_written_is_exit_2_not_a_silent_success(self):
        saved = self.saved_move(["TEAM-1"], role="todo")
        with mock.patch.object(state, "log_write", return_value=False):
            outcomes, code = self.run(saved)
        self.assertEqual(code, 2)
        self.assertIn("not recorded", outcomes[0]["result"])
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2")])

    def test_render_aligns_the_keys(self):
        text = applier.render([{"key": "TEAM-1", "result": "applied"}, {"key": "TEAM-10", "result": "changed"}])
        self.assertEqual(text.splitlines(), ["TEAM-1   applied", "TEAM-10  changed"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_applier.py" 2>&1 | tail -5`
Expected: `ImportError: cannot import name 'applier'`.

- [ ] **Step 3: Implement `jkan/applier.py`**

```python
"""Apply: runs a saved plan exactly, after a person approved it. Before each write it rereads the issue and leaves alone
anything that is no longer as planned. One issue never stops the others; the log makes running it again safe."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from . import plan as plan_mod
from . import state

GOOD = ("applied", "already there", "already applied")


def _move(jira, item: dict) -> str:
    key, snap = item["key"], jira.snapshot(item["key"])
    if snap["status_id"] == item["to"]["id"]:
        return "already there"
    if snap["status_id"] != item["from"]["id"]:
        return "changed"
    if not any(t["id"] == item["transition"] and t["to"]["id"] == item["to"]["id"] for t in jira.transitions(key)):
        return "changed"
    jira.transition_by_id(key, item["transition"])
    return "applied"


def _assign(jira, item: dict) -> str:
    owner = jira.snapshot(item["key"])["assignee"]
    now_id = owner["id"] if owner else None
    target = item["to"]["id"] if item["to"] else None
    if now_id == target:
        return "already there"
    if now_id != (item["from"]["id"] if item["from"] else None):
        return "changed"
    jira.assign(item["key"], target)
    return "applied"


def _one(jira, plan: dict, item: dict) -> str:
    try:
        if plan["kind"] == "move":
            return _move(jira, item)
        if plan["kind"] == "assign":
            return _assign(jira, item)
        jira.add_comment(item["key"], plan["options"]["text"])
        return "applied"
    except Exception as exc:  # noqa: BLE001 — one issue never stops the rest; the reason goes to the table and the log
        return f"error: {exc}"


def _entry(plan: dict, item: dict, result: str) -> dict:
    base = {"command": "apply", "plan": plan["id"], "key": item["key"], "action": plan["kind"], "result": result}
    return base if plan["kind"] == "comment" else dict(base, de=item["from"], a=item["to"])


def run(jira, plan: dict, confirm: Callable, command: str,
        now: Optional[Callable[[], str]] = None) -> Tuple[List[dict], int]:
    """Apply what the log does not already mark done. `confirm` (guard.confirm) raises NotApproved before any write."""
    done = state.applied(plan["id"])
    pending = [i for i in plan["items"] if i["key"] not in done]
    results = {i["key"]: "already applied" for i in plan["items"] if i["key"] in done}
    unlogged = False
    if pending:
        confirm(len(pending), plan_mod.describe(plan, [i["key"] for i in pending]), command)
        for item in pending:
            result = _one(jira, plan, item)
            if result == "applied" or result.startswith("error"):
                logged = state.log_write(_entry(plan, item, "ok" if result == "applied" else result), now)
                if not logged:
                    unlogged = True
                    result += " (not recorded in the log: re-running would repeat it)"
            results[item["key"]] = result
    outcomes = [{"key": i["key"], "result": results[i["key"]]} for i in plan["items"]]
    if unlogged:
        return outcomes, 2
    return outcomes, 0 if all(o["result"] in GOOD for o in outcomes) else 1


def render(outcomes: List[dict]) -> str:
    width = max((len(o["key"]) for o in outcomes), default=0)
    return "\n".join(f"{o['key']:<{width}}  {o['result']}" for o in outcomes)
```

- [ ] **Step 4: Add `applier` to the write side in the boundaries test**

In `tests/test_boundaries.py`, extend `WRITE` with `"applier"`:

```python
WRITE = {"sync", "spec", "description", "evidence", "kanban", "template", "preview", "plan", "applier"}
```

- [ ] **Step 5: Run the tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_applier.py" 2>&1 | tail -4` → `Ran 15 tests … OK`.
Run both full suites. Expected: `OK`. If `test_a_log_that_cannot_be_written…` fails because the result text lacks `not recorded`, the implementation's wording is the source of truth: keep `"(not recorded in the log: …)"` and the test's substring `not recorded`.

- [ ] **Step 6: Commit**

```bash
git add jkan/applier.py tests/test_applier.py tests/test_boundaries.py
git commit -m "feat(apply): run a saved plan after approval, rereading every issue before writing"
```

---

### Task 7: `jk plan` and `jk apply` on the command line

**Files:**
- Create: `jkan/plan_cli.py`
- Create: `tests/test_plan_cli.py`
- Modify: `jkan/team_cli.py:100,198` (rename `_context` → `context`)
- Modify: `jkan/cli.py` (imports, `main` signature and dispatch)
- Modify: `tests/test_boundaries.py` (add `"plan_cli"` to `WRITE`)

**Interfaces:**
- Consumes: Tasks 1–6; `team_cli.context(name) -> (view, profiles)` (raises `team_cli.Refusal`); `team.gather_open(jira, view, profiles, conv) -> (issues, truncated)`; `people.resolve_in(jira, query, boards) -> person`.
- Produces: `plan_cli.VERBS = ("move", "assign", "comment", "revert")`; `plan_cli.run_plan(argv, jira, conv, today) -> int`; `plan_cli.run_apply(argv, jira, confirm) -> int`; `cli.main(argv=None, client=…, today=None, confirm=guard.confirm)`. (`revert` is parsed here but implemented in Task 8: until then it is refused with a clear message.)

- [ ] **Step 1: Rename `_context` to `context` in `team_cli`**

In `jkan/team_cli.py` replace `def _context(name: str):` with `def context(name: str):` and the call in `_report` (`view, profiles = _context(args.view)`) with `view, profiles = context(args.view)`.
Run: `rg -n "_context" jkan tests` — Expected: no results.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_plan_cli.py`:

```python
from __future__ import annotations

import contextlib
import functools
import io
import json
import re
import unittest

import plan_fixtures as pf
import team_fixtures as fx
from helpers import FakeJira, config_dir, state_dir
from jkan import board_profile, cli, guard, state, views


class NoTerminal:
    def isatty(self):
        return False


def run(args, jira, confirm=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args, client=lambda project: jira, today=lambda: fx.TODAY, confirm=confirm or approve)
    return code, out.getvalue(), err.getvalue()


def approve(n, summary, command):
    return None


def plan_id(out):
    return re.search(r"jk apply ([0-9a-f]{12})", out).group(1)


class Base(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.config = config_dir()
        for prof in fx.profiles().values():
            board_profile.save(prof)
        views.save(fx.view())
        self.jira = FakeJira()
        pf.workflow(self.jira)
        self.issues = {}

    def put(self, key, role, assignee=None, **over):
        self.issues[key] = pf.put(self.jira, key, role, assignee, **over)
        return self.issues[key]

    def serve(self, open_=()):
        known = dict(self.issues)

        def answer(jql):
            if "key in (" in jql:
                wanted = jql.split("key in (", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
                return [known[k] for k in wanted if k in known]
            return list(open_)
        self.jira.search_answer = answer


class PlanTest(Base):
    def test_planning_a_move_saves_a_file_prints_the_summary_and_writes_nothing(self):
        self.put("TEAM-1", "todo")
        self.serve()
        code, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("TEAM-1: Backlog -> En curso", out)
        self.assertIn("Nothing was written to Jira", out)
        saved = state.load_plan(plan_id(out))
        self.assertEqual((saved["kind"], saved["view"], saved["items"][0]["transition"]), ("move", "plataforma", "1>2"))
        self.assertEqual(self.jira.writes, [])

    def test_the_filters_pick_the_open_issues_of_the_view(self):
        a = self.put("TEAM-1", "todo", created="2026-09-01")
        b = self.put("TEAM-2", "todo", fx.ANA)
        self.serve(open_=[a, b])
        code, out, _ = run(["plan", "assign", "plataforma", "--unassigned", "--person", "Ana Gómez"], self.jira)
        self.assertEqual(code, 0)
        saved = state.load_plan(plan_id(out))
        self.assertEqual([i["key"] for i in saved["items"]], ["TEAM-1"])
        self.assertEqual(saved["options"]["person"]["id"], "acc-ana")

    def test_a_comment_plan(self):
        self.put("TEAM-1", "todo")
        self.serve()
        code, out, _ = run(["plan", "comment", "plataforma", "TEAM-1", "--text", "hola equipo"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(state.load_plan(plan_id(out))["options"]["text"], "hola equipo")

    def test_an_ambiguous_person_is_never_guessed_and_nothing_is_saved(self):
        self.put("TEAM-1", "todo")
        self.serve()
        code, _, err = run(["plan", "assign", "plataforma", "TEAM-1", "--person", "Martin"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)
        self.assertFalse((self.base / "plans").exists())

    def test_refusals_exit_1_with_the_reason_and_save_nothing(self):
        self.put("TEAM-1", "todo")
        self.serve()
        cases = [(["plan", "move", "plataforma", "TEAM-1", "--to", "delivered"], "--allow-close"),
                 (["plan", "move", "plataforma", "OTHER-1", "--to", "active"], "not in the boards"),
                 (["plan", "move", "plataforma", "--to", "active"], "say which issues"),
                 (["plan", "comment", "plataforma", "TEAM-1", "--text", " "], "the comment is empty"),
                 (["plan", "move", "plataforma", "TEAM-1", "--to", "active", "--max", "500"], "--max"),
                 (["plan", "move", "nope", "TEAM-1", "--to", "active"], "nope")]
        for args, text in cases:
            code, _, err = run(args, self.jira)
            self.assertEqual(code, 1, args)
            self.assertIn(text, err)
        self.assertFalse((self.base / "plans").exists())

    def test_a_key_that_carries_jql_is_refused_before_jira_is_asked(self):
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1) OR project = X", "--to", "active"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("is not an issue key", err)
        self.assertEqual(self.jira.jqls, [])

    def test_a_board_without_profile_or_with_undecided_statuses_is_refused(self):
        self.put("TEAM-1", "todo")
        self.serve()
        board_profile.save(fx.profile("TEAM", decide_waiting=False))
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("without a role", err)
        (self.config / "profiles" / "DESK.json").unlink()
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no profile for DESK", err)

    def test_a_search_that_hit_its_cap_refuses_to_plan_from_filters(self):
        self.jira.search_answer = lambda jql: [fx.at(f"TEAM-{n}", "todo", assignee=None) for n in range(1, 1002)]
        code, _, err = run(["plan", "assign", "plataforma", "--unassigned", "--person", "Ana Gómez", "--max", "200"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("cap", err)

    def test_a_state_folder_that_cannot_be_written_is_exit_2(self):
        self.put("TEAM-1", "todo")
        self.serve()
        (self.base / "plans").write_text("a file where the folder should be", encoding="utf-8")
        code, _, err = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())

    def test_filters_are_the_same_ones_as_list_and_a_bad_role_is_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["plan", "move", "plataforma", "TEAM-1", "--to", "active", "--role", "delivered"], self.jira)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["plan", "move", "plataforma", "TEAM-1", "--to", "nope"], self.jira)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["plan", "explode", "plataforma"], self.jira)


class ApplyTest(Base):
    def planned(self, key="TEAM-1"):
        self.put(key, "todo")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", key, "--to", "active"], self.jira)
        return plan_id(out)

    def test_applying_with_an_approval_writes_and_prints_the_table(self):
        pid = self.planned()
        code, out, _ = run(["apply", pid], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("TEAM-1  applied", out)
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2")])

    def test_without_approval_it_exits_3_and_writes_nothing(self):
        pid = self.planned()

        def refuse(n, summary, command):
            raise guard.NotApproved("not approved; nothing was written.")

        code, _, err = run(["apply", pid], self.jira, confirm=refuse)
        self.assertEqual((code, self.jira.writes), (3, []))
        self.assertIn("nothing was written", err)

    def test_under_the_real_guard_without_a_terminal_it_prints_the_command_and_exits_3(self):
        pid = self.planned()
        real = functools.partial(guard.confirm, streams=(NoTerminal(),) * 3)
        code, _, err = run(["apply", pid], self.jira, confirm=real)
        self.assertEqual((code, self.jira.writes), (3, []))
        self.assertIn(f"  jk apply {pid}", err)

    def test_an_unknown_edited_or_malformed_plan_is_exit_1(self):
        pid = self.planned()
        for bad in ("0" * 12, "../x", "ZZZ"):
            code, _, err = run(["apply", bad], self.jira)
            self.assertEqual(code, 1, bad)
            self.assertTrue(err.strip())
        path = state.plan_path(pid)
        edited = json.loads(path.read_text(encoding="utf-8"))
        edited["items"][0]["key"] = "TEAM-99"
        path.write_text(json.dumps(edited), encoding="utf-8")
        code, _, err = run(["apply", pid], self.jira)
        self.assertEqual((code, self.jira.writes), (1, []))
        self.assertIn("changed after it was planned", err)

    def test_a_plan_of_a_view_that_no_longer_exists_is_refused(self):
        pid = self.planned()
        (self.config / "views" / "plataforma.json").unlink()
        code, _, err = run(["apply", pid], self.jira)
        self.assertEqual((code, self.jira.writes), (1, []))
        self.assertIn("plataforma", err)

    def test_one_changed_issue_makes_the_exit_code_1(self):
        pid = self.planned()
        self.jira.board["TEAM-1"].update(status_id="3", status="Blocked")
        code, out, _ = run(["apply", pid], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("TEAM-1  changed", out)

    def test_apply_takes_exactly_one_id_and_nothing_else(self):
        for args in (["apply"], ["apply", "a" * 12, "--yes"], ["apply", "a" * 12, "b" * 12]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run(args, self.jira)

    def test_a_read_only_command_never_needs_the_guard(self):
        code, _, _ = run(["team", "list"], self.jira)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_plan_cli.py" 2>&1 | tail -6`
Expected: errors (`TypeError: main() got an unexpected keyword argument 'confirm'`).

- [ ] **Step 4: Implement `jkan/plan_cli.py`**

```python
"""jk plan move|assign|comment|revert and jk apply: guarded writes to Jira. A plan only reads Jira and saves a file; apply
runs that file exactly, after a person at a terminal approved it (guard.py).

Exit codes: 0 done, 1 refused or something changed or failed, 2 could not (Jira, disk, log), 3 a person has to do it
(no terminal, or not approved)."""
from __future__ import annotations

import argparse
import sys
from typing import Callable, List

from . import applier, guard, people, plan, state, team, team_cli
from .jira import JiraError

OK, FINDINGS, CANNOT = 0, 1, 2
VERBS = ("move", "assign", "comment", "revert")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jk plan", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)

    def selecting(p: argparse.ArgumentParser) -> None:
        p.add_argument("view")
        p.add_argument("keys", nargs="*", help="issue keys, e.g. PLATE-12; they must be in the boards of the view")
        p.add_argument("--unassigned", action="store_true", help="select the open issues nobody owns")
        p.add_argument("--older-than", type=int, metavar="DAYS", help="select open issues created DAYS ago or before")
        p.add_argument("--role", choices=team.COUNTED + ("none",), help="select open issues in this role")
        p.add_argument("--max", type=int, help=f"most issues a plan may hold (default {plan.DEFAULT_MAX}, up to {plan.LIMIT_MAX})")

    move = sub.add_parser("move", help="plan moving issues to the status that plays a role (reads Jira, writes a file)")
    selecting(move)
    move.add_argument("--to", required=True, choices=plan.TO_ROLES, help="the role the issues should reach")
    move.add_argument("--to-status", metavar="ID", help="a status id of the profile, when the role has several")
    move.add_argument("--allow-close", action="store_true", help="needed to move to delivered or dropped")
    give = sub.add_parser("assign", help="plan assigning issues to one person (reads Jira, writes a file)")
    selecting(give)
    give.add_argument("--person", required=True, help="a name, email or accountId; never guessed between several")
    note = sub.add_parser("comment", help="plan the same plain-text comment on issues (reads Jira, writes a file)")
    selecting(note)
    note.add_argument("--text", required=True)
    undo = sub.add_parser("revert", help="plan the inverse of an applied plan (it does not guarantee undoing)")
    undo.add_argument("id")
    return parser


def _announce(saved: dict) -> int:
    print(plan.describe(saved))
    print(f"\nPlan {saved['id']} saved in {state.plan_path(saved['id'])}. Nothing was written to Jira.\n"
          f"To apply it, run this in your own terminal (it asks for your approval there):\n  jk apply {saved['id']}")
    return OK


def _plan(args, jira, conv: dict, today) -> int:
    if args.verb == "revert":
        raise plan.Refused("revert is not available yet")
    view, profiles = team_cli.context(args.view)
    limit = plan.check_max(args.max)
    client = jira()
    filtering = args.unassigned or args.older_than is not None or args.role is not None
    open_issues = []
    if filtering:
        open_issues, truncated = team.gather_open(client, view, profiles, conv)
        if truncated:
            raise plan.Refused(f"the search hit the cap of {team.CAP} issues, so the filters would miss some: "
                               f"name the issues by key")
    selection = plan.select(client, view, profiles, conv, open_issues, today, args.keys, args.unassigned,
                            args.older_than, args.role, limit)
    plan.check_profiles(selection, profiles)
    if args.verb == "move":
        body = plan.move(client, view, selection, profiles, args.to, args.to_status, args.allow_close)
    elif args.verb == "assign":
        body = plan.assign(view, selection, people.resolve_in(client, args.person, view["boards"]))
    else:
        body = plan.comment(view, selection, args.text)
    return _announce(state.save_plan(body))


def run_plan(argv: List[str], jira: Callable[[], object], conv: dict, today: Callable) -> int:
    args = _parser().parse_args(argv)
    try:
        return _plan(args, jira, conv, today())
    except ValueError as exc:  # Refused, Refusal, BadPlan, BadView, NotResolved: a decision for the person, not a crash
        sys.stderr.write(f"jk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT


def run_apply(argv: List[str], jira: Callable[[], object], confirm: Callable) -> int:
    parser = argparse.ArgumentParser(prog="jk apply", description="Run a saved plan after a person approves it.")
    parser.add_argument("id", help="the plan id that jk plan printed")
    args = parser.parse_args(argv)
    try:
        saved = state.load_plan(args.id)
        team_cli.context(saved["view"])
        outcomes, code = applier.run(jira(), saved, confirm, f"jk apply {saved['id']}")
    except guard.NotApproved as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return guard.EXIT_NEEDS_PERSON
    except ValueError as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT
    print(applier.render(outcomes))
    return code
```

- [ ] **Step 5: Wire it in `jkan/cli.py`**

Imports: change the `from . import (…)` block to include `guard` and `plan_cli`:

```python
from . import (board_cli, board_profile, config, guard, journal, kanban, people, plan_cli, preview, render, roles, standup,
               stats, sync, team_cli, views, window)
```

Change the `main` signature to:

```python
def main(argv: Optional[List[str]] = None, client: Callable = _client,
         today: Optional[Callable[[], _dt.date]] = None, confirm: Callable = guard.confirm) -> int:
```

Right after the `team` dispatch block (before `parser = argparse.ArgumentParser(prog="jk", description=__doc__)`), add:

```python
    if argv and argv[0] in ("plan", "apply"):  # the guarded writes; the global log is their record, so no per-project journal
        here = Path(".").resolve()
        plan_conv = config.load_conventions(here)
        make = lambda: client(here) if client is not _client else _client(here, command=None)  # noqa: E731
        if argv[0] == "apply":
            return plan_cli.run_apply(argv[1:], make, confirm)
        return plan_cli.run_plan(argv[1:], make, plan_conv,
                                 today or (lambda: window.today_in(plan_conv.get("timezone"))))
```

Also extend the module docstring's first line mention: add `plan | apply` after `team`: change `board setup|set|show|check|survey.` to `board setup|set|show|check|survey | team … | plan … | apply.` (keep the rest of the sentence).

- [ ] **Step 6: Add `plan_cli` to the write side in the boundaries test**

```python
WRITE = {"sync", "spec", "description", "evidence", "kanban", "template", "preview", "plan", "applier", "plan_cli"}
```

- [ ] **Step 7: Run the tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_plan_cli.py" 2>&1 | tail -6`
Expected: `OK`. If a refusal test shows a different message, fix the implementation to match the message in the test only when the test's text is the spec's intent (`not in the boards`, `say which issues`, `without a role`, `no profile for DESK`); do not weaken a test.
Run both full suites. Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add jkan/plan_cli.py jkan/cli.py jkan/team_cli.py tests/test_plan_cli.py tests/test_boundaries.py
git commit -m "feat(plan): jk plan and jk apply, behind the guard"
```

---

### Task 8: Revert

**Files:**
- Modify: `jkan/plan.py` (add `revert`)
- Modify: `jkan/plan_cli.py` (`_plan`: replace the placeholder refusal)
- Modify: `tests/test_plan.py`, `tests/test_plan_cli.py`

**Interfaces:**
- Consumes: Task 4 `_route`, `_envelope`, `Refused`; Task 2 `state.entries`; Task 3 `Jira.snapshot`.
- Produces: `plan.revert(jira, original: dict, profiles, now=None) -> dict` (a plan body of the same `kind` as the original, with `options = {"revert_of": <id>}`). Move items go back to the logged `de` status; assign items go back to the logged previous owner (`to: None` when nobody had it); comments are never reverted and are listed in `skipped`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan.py` before the `if __name__` block:

```python
class RevertTest(Base):
    def applied_move(self, keys=("TEAM-1", "TEAM-2")):
        from jkan import applier
        selection = [self.put(k, "todo") for k in keys]
        saved = state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        self.jira.writes.clear()
        return saved

    def test_reverting_a_move_goes_back_to_the_status_it_left_by_its_own_transition(self):
        saved = self.applied_move()
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual((body["kind"], body["options"]), ("move", {"revert_of": saved["id"]}))
        self.assertEqual(body["items"], [
            {"key": k, "from": {"id": "2", "name": "En curso"}, "to": {"id": "1", "name": "Backlog", "role": "todo"},
             "transition": "2>1"} for k in ("TEAM-1", "TEAM-2")])
        self.assertEqual(self.jira.writes, [])

    def test_an_issue_that_moved_on_since_is_left_out(self):
        saved = self.applied_move()
        self.jira.board["TEAM-1"].update(status_id="5", status="Done")
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual([i["key"] for i in body["items"]], ["TEAM-2"])
        self.assertEqual(body["skipped"], [{"key": "TEAM-1", "why": "changed"}])

    def test_a_workflow_without_a_way_back_is_marked(self):
        saved = self.applied_move(("TEAM-1",))
        self.jira.workflow["2"] = []
        with self.assertRaisesRegex(plan.Refused, "TEAM-1: no path"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)

    def test_reverting_an_assign_goes_back_to_who_had_it_including_nobody(self):
        from jkan import applier
        selection = [self.put("TEAM-1", "todo"), self.put("TEAM-2", "todo", fx.BETO)]
        saved = state.save_plan(plan.assign(self.view, selection, ANA, now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual(body["kind"], "assign")
        self.assertEqual(body["items"], [
            {"key": "TEAM-1", "from": {"id": "acc-ana", "name": "Ana Gómez"}, "to": None},
            {"key": "TEAM-2", "from": {"id": "acc-ana", "name": "Ana Gómez"}, "to": {"id": "acc-beto", "name": "Beto Ruiz"}}])
        self.assertIn("TEAM-1: Ana Gómez -> unassigned", plan.describe(dict(body, id="abcdef123456")))

    def test_comments_cannot_be_reverted_and_the_plan_says_so(self):
        from jkan import applier
        saved = state.save_plan(plan.comment(self.view, [self.put("TEAM-1", "todo")], "hola", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        with self.assertRaisesRegex(plan.Refused, "TEAM-1: comments are not reverted"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)

    def test_a_plan_that_wrote_nothing_has_nothing_to_revert(self):
        selection = [self.put("TEAM-1", "todo")]
        saved = state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW))
        with self.assertRaisesRegex(plan.Refused, "wrote nothing"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)
```

Also add `from helpers import state_dir` to the imports of `tests/test_plan.py` and, in `Base.setUp`, add the line `self.state = state_dir()` (the applier writes the log).

Append to `tests/test_plan_cli.py`, before the `if __name__` block:

```python
class RevertCliTest(Base):
    def test_revert_plans_the_inverse_of_an_applied_plan_and_it_needs_its_own_approval(self):
        self.put("TEAM-1", "todo")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        first = plan_id(out)
        run(["apply", first], self.jira)
        self.jira.writes.clear()
        code, out, _ = run(["plan", "revert", first], self.jira)
        self.assertEqual(code, 0)
        second = plan_id(out)
        self.assertNotEqual(first, second)
        self.assertIn("TEAM-1: En curso -> Backlog", out)
        self.assertEqual(self.jira.writes, [])
        asked = []
        run(["apply", second], self.jira, confirm=lambda n, s, c: asked.append((n, c)))
        self.assertEqual(asked, [(1, f"jk apply {second}")])
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "2>1")])

    def test_reverting_a_plan_that_does_not_exist_or_wrote_nothing_is_refused(self):
        code, _, err = run(["plan", "revert", "0" * 12], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no plan", err)
        self.put("TEAM-1", "todo")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        code, _, err = run(["plan", "revert", plan_id(out)], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("wrote nothing", err)
```

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_plan.py" 2>&1 | tail -5` and `… -p "test_plan_cli.py"`.
Expected: `AttributeError: module 'jkan.plan' has no attribute 'revert'` and `revert is not available yet`.

- [ ] **Step 3: Implement `plan.revert`**

In `jkan/plan.py`, after `comment`, add:

```python
def _status_role(profiles: Dict[str, dict], key: str, status_id: str) -> Optional[str]:
    profile = profiles.get(roles.project_of(key)) or {"statuses": []}
    return next((s["role"] for s in profile["statuses"] if s["id"] == status_id), None)


def revert(jira, original: dict, profiles: Dict[str, dict], now: Optional[Callable[[], str]] = None) -> dict:
    """The inverse of what the log says `original` wrote. It does not guarantee undoing: an issue that changed since, or a
    workflow with no way back, is left out and said; comments are never reverted."""
    view = {"name": original["view"]}
    items, skipped = [], []
    wrote = [e for e in state.entries(original["id"]) if e.get("result") == "ok"]
    if not wrote:
        raise Refused(f"plan {original['id']} wrote nothing, so there is nothing to revert")
    for entry in wrote:
        key = entry["key"]
        if original["kind"] == "comment":
            skipped.append({"key": key, "why": "comments are not reverted"})
            continue
        snap = jira.snapshot(key)
        if original["kind"] == "assign":
            if (snap["assignee"] or {}).get("id") != entry["a"]["id"]:
                skipped.append({"key": key, "why": "changed"})
            else:
                items.append({"key": key, "from": dict(entry["a"]), "to": dict(entry["de"]) if entry["de"] else None})
            continue
        if snap["status_id"] != entry["a"]["id"]:
            skipped.append({"key": key, "why": "changed"})
            continue
        chosen, skip = _route(jira, key, [entry["de"]["id"]])
        if skip:
            skipped.append(skip)
            continue
        items.append({"key": key, "from": {"id": snap["status_id"], "name": snap["status"]},
                      "to": {"id": chosen["to"]["id"], "name": chosen["to"]["name"],
                             "role": _status_role(profiles, key, chosen["to"]["id"])},
                      "transition": chosen["id"]})
    if not items:
        raise Refused("nothing to revert: " + _why(skipped))
    options = {"revert_of": original["id"]}
    return _envelope(original["kind"], view, options, items, skipped, now)
```

(The inverse of an `assign` plan has `kind: "assign"` and the original person is not needed in `options`; `describe` for `assign` uses only `items`.)

- [ ] **Step 4: Use it from the command line**

In `jkan/plan_cli.py`, replace the first two lines of `_plan`:

```python
    if args.verb == "revert":
        raise plan.Refused("revert is not available yet")
```

with:

```python
    if args.verb == "revert":
        original = state.load_plan(args.id)
        _, profiles = team_cli.context(original["view"])
        return _announce(state.save_plan(plan.revert(jira(), original, profiles)))
```

- [ ] **Step 5: Run the tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_plan.py" 2>&1 | tail -4`, `… -p "test_plan_cli.py"`, then both full suites. Expected: `OK`.
Note on `test_a_workflow_without_a_way_back_is_marked`: with `workflow["2"] = []` the issue (now at status `2`) has no transitions, so `_route` returns `no path`, and with only one issue the plan is refused with `TEAM-1: no path`.

- [ ] **Step 6: Commit**

```bash
git add jkan/plan.py jkan/plan_cli.py tests/test_plan.py tests/test_plan_cli.py
git commit -m "feat(plan): revert plans the inverse of an applied plan, and says what it cannot undo"
```

---

### Task 9: The guard on the legacy `--apply`

**Files:**
- Modify: `jkan/cli.py` (`_assign`, the `create` and `push` branches; new `_approve`)
- Create: `tests/test_legacy_guard.py`
- Modify: the existing tests that run `--apply` (found in Step 4)
- Modify: `tests/helpers.py` (add `approve`)

**Interfaces:**
- Consumes: Task 1 `guard.NotApproved`, `guard.EXIT_NEEDS_PERSON`; Task 7 `cli.main(…, confirm=…)`.
- Produces: `cli._approve(confirm, n, summary, argv) -> Optional[int]` (`None` = go ahead; otherwise the exit code to return, already printed to stderr).
- `n`: `create` → `len(dry["ops"])`; `push` → `len(dry["changes"]) + len(dry["new"])`; `assign` → `len(dry["issues"])`. `n == 0` writes nothing and asks nothing.

- [ ] **Step 1: Write the failing tests**

In `tests/helpers.py`, after `make_project`, add:

```python
def approve(n, summary, command):
    """A confirm() for tests of the legacy --apply: the person approved. Real runs go through guard.confirm."""
    return None
```

Create `tests/test_legacy_guard.py`:

```python
from __future__ import annotations

import contextlib
import functools
import io
import json
import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import cli, guard
from test_spec import GOOD


class Asked:
    def __init__(self, approve=True):
        self.approve, self.calls = approve, []

    def __call__(self, n, summary, command):
        self.calls.append((n, summary, command))
        if not self.approve:
            raise guard.NotApproved("not approved; nothing was written.")


def run(args, jira, confirm):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args, client=lambda project: jira, confirm=confirm)
    return code, out.getvalue(), err.getvalue()


class AssignTest(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()
        self.epic = epic_with_children(self.jira)  # PLATE-600 epic > PLATE-601 story > PLATE-602 subtask; PLATE-603 task
        self.project = str(make_project())

    def args(self, key, *extra):
        return ["assign", key, "Matias Andres Fernandez", "--project", self.project, *extra]

    def test_a_dry_run_never_asks(self):
        asked = Asked()
        self.assertEqual(run(self.args("PLATE-601"), self.jira, asked)[0], 0)
        self.assertEqual((asked.calls, self.jira.writes), ([], []))

    def test_apply_asks_with_the_real_count_and_the_command_to_run(self):
        asked = Asked()
        code, out, _ = run(self.args(self.epic, "--tree", "--apply"), self.jira, asked)
        self.assertEqual(code, 0)
        n, summary, command = asked.calls[0]
        self.assertEqual(n, 4)
        self.assertIn("assign 4 issue(s) to Matías Andrés Fernandez", summary)
        self.assertTrue(command.startswith("jk assign PLATE-600 "))
        self.assertIn("--tree --apply", command)
        self.assertIn("assigned 4 issue", out)

    def test_without_approval_nothing_is_written_and_the_exit_code_is_3(self):
        code, _, err = run(self.args("PLATE-601", "--apply"), self.jira, Asked(approve=False))
        self.assertEqual((code, self.jira.writes), (guard.EXIT_NEEDS_PERSON, []))
        self.assertIn("nothing was written", err)

    def test_the_real_guard_refuses_without_a_terminal_and_prints_the_command(self):
        class NoTty:
            def isatty(self):
                return False

        real = functools.partial(guard.confirm, streams=(NoTty(),) * 3)
        code, _, err = run(self.args("PLATE-601", "--apply"), self.jira, real)
        self.assertEqual((code, self.jira.writes), (3, []))
        self.assertIn("Run it yourself", err)
        self.assertIn("jk assign PLATE-601", err)


class CreateTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.spec = self.project / "spec.json"
        self.spec.write_text(json.dumps(GOOD), encoding="utf-8")

    def args(self, *extra):
        return ["create", "--spec", str(self.spec), "--project", str(self.project), "--jira-project", "PLATE", *extra]

    def test_a_dry_run_never_asks_and_apply_asks_for_the_number_of_issues(self):
        asked = Asked()
        self.assertEqual(run(self.args(), self.jira, asked)[0], 0)
        self.assertEqual(asked.calls, [])
        code, _, _ = run(self.args("--apply", "--assign-open"), self.jira, asked)
        self.assertEqual(code, 0)
        n, summary, _ = asked.calls[0]
        self.assertEqual(n, len([w for w in self.jira.writes if w[0] == "create"]))
        self.assertIn(f"create {n} issue(s) in PLATE", summary)

    def test_without_approval_nothing_is_created_and_no_local_folder_appears(self):
        code, _, err = run(self.args("--apply", "--assign-open"), self.jira, Asked(approve=False))
        self.assertEqual((code, self.jira.writes), (3, []))
        self.assertFalse((self.project / ".jira-kanban" / "PLATE-600").exists())
        self.assertIn("nothing was written", err)


class PushTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        self.args = lambda *extra: ["push", self.key, "--project", str(self.project), *extra]  # noqa: E731
        cli.main(["pull", self.key, "--project", str(self.project)], client=lambda p: self.jira)

    def edit(self):
        task = self.project / ".jira-kanban" / self.key / "tasks/PLATE-603/task.md"
        task.write_text(task.read_text(encoding="utf-8").replace("status: Backlog", "status: Done"), encoding="utf-8")

    def test_apply_asks_for_changes_plus_new_issues_and_nothing_else_is_asked_in_a_dry_run(self):
        self.edit()
        asked = Asked()
        self.assertEqual(run(self.args(), self.jira, asked)[0], 0)
        self.assertEqual(asked.calls, [])
        self.assertEqual(run(self.args("--apply"), self.jira, asked)[0], 0)
        self.assertEqual(asked.calls[0][0], 1)
        self.assertEqual(self.jira.issues["PLATE-603"]["status"], "Done")

    def test_without_approval_nothing_is_pushed(self):
        self.edit()
        code, _, _ = run(self.args("--apply"), self.jira, Asked(approve=False))
        self.assertEqual((code, self.jira.writes), (3, []))

    def test_with_nothing_to_write_there_is_nothing_to_approve(self):
        asked = Asked(approve=False)
        code, _, _ = run(self.args("--apply"), self.jira, asked)
        self.assertEqual((code, asked.calls), (0, []))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_legacy_guard.py" 2>&1 | tail -6`
Expected: failures, because `--apply` writes without asking.

- [ ] **Step 3: Implement the guard in `jkan/cli.py`**

Add `import shlex` to the standard imports. After the `OK, FINDINGS, CANNOT = 0, 1, 2` line add:

```python
NEEDS_PERSON = guard.EXIT_NEEDS_PERSON
```

Before `def _assign`, add:

```python
def _approve(confirm: Callable, n: int, summary: str, argv: List[str]) -> Optional[int]:
    """None when the write may go ahead (nothing to write, or a person approved); otherwise the exit code to return."""
    if n == 0:
        return None
    try:
        confirm(n, summary, "jk " + shlex.join(argv))
    except guard.NotApproved as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return NEEDS_PERSON
    return None
```

Change `_assign`'s signature to `def _assign(jira, key: str, who: str, tree: bool, apply: bool, confirm: Callable, argv: List[str]) -> int:` and, right after the `approximate match` print block and before `result = sync.assign(…)`, add:

```python
    if apply:
        planned = sync.assign(jira, key, person, tree=tree, apply=False)["issues"]
        code = _approve(confirm, len(planned), f"assign {len(planned)} issue(s) to {person['name']}", argv)
        if code is not None:
            return code
```

In `main`, change the assign call to `return _assign(jira, args.key, args.who, args.tree, args.apply, confirm, argv)`.

In the `create` branch, replace

```python
            epic_spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            try:
                result = sync.create(jira, project, epic_spec, conv, apply=args.apply, assign_open=args.assign_open)
```

with

```python
            epic_spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            try:
                if args.apply:  # a silent dry run says how many issues the person is about to approve
                    planned = sync.create(jira, project, epic_spec, conv, apply=False, assign_open=args.assign_open)["ops"]
                    code = _approve(confirm, len(planned), f"create {len(planned)} issue(s) in {conv['project']}", argv)
                    if code is not None:
                        return code
                result = sync.create(jira, project, epic_spec, conv, apply=args.apply, assign_open=args.assign_open)
```

In the `push` branch, replace

```python
        try:
            result = sync.push(jira, project, args.epic, apply=args.apply, conv=conv, assign_open=args.assign_open)
```

with

```python
        try:
            if args.apply:
                planned = sync.push(jira, project, args.epic, apply=False, conv=conv, assign_open=args.assign_open)
                n = len(planned["changes"]) + len(planned["new"])
                code = _approve(confirm, n, f"push {n} write(s) to {args.epic}", argv)
                if code is not None:
                    return code
            result = sync.push(jira, project, args.epic, apply=args.apply, conv=conv, assign_open=args.assign_open)
```

- [ ] **Step 4: Run the whole suite and fix the old tests that now meet the guard**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -30`
Expected: `test_legacy_guard.py` passes, and the old tests that pass `--apply` through `cli.main` without a `confirm` fail (exit 3). They are exactly the files `rg -l -- "--apply" tests` lists (`test_cli.py`, `test_push_check.py`, `test_push_moves.py`, `test_push_output.py`, `test_transitions.py`, `test_who_assign.py`) minus the new one. For each, find the `cli.main(` call in its `run` helper and pass the approving confirm: add `approve` to its `from helpers import …` line and `confirm=approve` to the call, e.g. in `tests/test_cli.py`:

```python
from helpers import FakeJira, approve, epic_with_children, make_project
…
        code = cli.main(args, client=lambda project: jira, confirm=approve)
```

Do the same in each failing file (a file that imports another file's `run` needs no change). Do not touch any assertion.
Run both full suites. Expected: `OK` on both (no test weakened; the only change in old tests is the injected `confirm`).

- [ ] **Step 5: Commit**

```bash
git add jkan/cli.py tests
git commit -m "feat(guard): create, push and assign --apply need a person at a terminal too"
```

---

### Task 10: The `jira-em-ops` skill, install, boundaries, docs

**Files:**
- Create: `ops/SKILL.md`
- Modify: `install.sh` (the `--with-write` list and its header comment)
- Modify: `tests/test_skills.py`, `tests/test_install.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-10-jira-em-fase-3-design.md` (add «Resultados de la fase 3»)

**Interfaces:**
- Consumes: `plan_cli.VERBS`.
- Produces: skill `jira-em-ops` at `<repo>/ops`, installed only with `--with-write`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_skills.py`:
- add `plan_cli` to the import: `from jkan import board_cli, plan_cli, team_cli`;
- change `SKILLS` to `((".", "jira-kanban"), ("standup", "jira-standup"), ("em", "jira-em"), ("ops", "jira-em-ops"))`;
- add these tests to `SkillsTest`:

```python
    def test_the_ops_skill_is_about_changing_the_team_and_points_to_the_read_only_ones(self):
        description = frontmatter("ops")["description"]
        self.assertIn("team", description)
        self.assertIn("jira-em", description)
        self.assertIn("jira-kanban", description)

    def test_the_ops_skill_only_plans_and_never_runs_apply_or_the_legacy_writers(self):
        text = (ROOT / "ops" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("jk.py", text)
        for forbidden in ("jk create", "jk push", "jk assign"):
            self.assertNotIn(forbidden, text)
        self.assertIn("Never run `jk apply`", text)

    def test_every_plan_command_the_ops_skill_mentions_exists(self):
        text = (ROOT / "ops" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jk plan (\w+)", text):
            self.assertIn(verb, plan_cli.VERBS, verb)
        for verb in re.findall(r"jk team (\w+)", text):
            self.assertIn(verb, team_cli.VERBS, verb)

    def test_the_descriptions_do_not_overlap_on_the_phrases_that_pick_a_skill(self):
        self.assertNotIn("Read only", frontmatter("ops")["description"])
        self.assertNotIn("assign", frontmatter("em")["description"].lower())
```

In `tests/test_install.py`, in `test_with_write_adds_the_skill_that_writes_to_jira` (view it first with `rg -n "test_with_write" -A12 tests/test_install.py`) add assertions that `jira-em-ops` is linked for `.agents` (`str(ROOT / "ops")`) and the three hosts; and in the default-install test add `self.assertFalse(os.path.lexists(home / ".agents/skills/jira-em-ops"))`.

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_skills.py" 2>&1 | tail -6` and `… -p "test_install.py"`.
Expected: `FileNotFoundError … ops/SKILL.md` and the install assertions failing.

- [ ] **Step 3: Create `ops/SKILL.md`**

```markdown
---
name: jira-em-ops
description: Use when a manager wants to change several issues of their team at once ("pasá estos tickets a en curso", "asigná los que no tienen dueño", "comentá en estos tickets", "deshacé lo que apliqué"). It only prepares the change; a person approves it in their own terminal. To read the team use jira-em, and to create or sync epics use jira-kanban.
---

# jira-em-ops

Prepares changes to **several issues of the team's boards**: move to a status, assign, comment. It never writes to Jira
by itself: `jk plan …` only reads and saves a plan; the person runs `jk apply <id>` in a terminal window and types
`APRUEBO <n>` there.

```bash
jk plan move    VIEW [KEY …] [--unassigned] [--older-than D] [--role R] --to ROLE [--to-status ID] [--allow-close] [--max N]
jk plan assign  VIEW [KEY …] [--unassigned] [--older-than D] [--role R] --person "<name>" [--max N]
jk plan comment VIEW [KEY …] [--unassigned] [--older-than D] [--role R] --text "<text>" [--max N]
jk plan revert  PLAN_ID
```

| The user asks | Run |
|---|---|
| move these tickets to in progress / blocked / done | `jk plan move VIEW KEY … --to active\|blocked\|delivered` (closing also needs `--allow-close`) |
| assign what nobody owns (to Ana) | `jk plan assign VIEW --unassigned --person "Ana"` |
| comment the same text on these tickets | `jk plan comment VIEW KEY … --text "…"` |
| undo what I applied | `jk plan revert PLAN_ID` (it does not guarantee undoing) |
| which tickets are those (before planning) | `jk team status VIEW --list` or `jk team desk VIEW --list`, with `--unassigned`, `--older-than DAYS`, `--role ROLE` |

## Steps

1. **Find the view and the issues.** `jk team list` shows the views. If the user names counts ("the 7 unassigned"), list
   them first with `--list` so the plan is about exactly those issues.
2. **Plan.** Run the `jk plan …` command and show its output as it is: it already names every issue, what changes and
   what was left out. A plan has at most 25 issues (`--max` up to 200).
3. **Hand it over.** Give the user the line the plan prints, `jk apply <id>`, and tell them to run it **in their own
   terminal window**. Then stop and wait: do not poll, do not retry.
4. **After they applied it**, offer `jk team status VIEW` to see the result, or `jk plan revert <id>` if they want it back.

## Rules

- **Never run `jk apply`**, nor the older writers (create, push, assign) with `--apply`. Only a person at a
  terminal can approve a write; an approval typed in the chat counts for nothing.
- Exit code 3 means "a person has to do this", not "try again". Exit code 1 means the plan was refused: read the reason,
  fix the selection, plan again.
- Read only otherwise: never `jk board` writes other than the profile commands the user asks for.
- If a plan says a board's profile has statuses without a role, stop: that is a decision for the user
  (`jk board set`), never yours.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
```

- [ ] **Step 4: Install it only with `--with-write`**

In `install.sh` change the `--with-write` case to:

```bash
  --with-write) SKILLS+=("jira-kanban:" "jira-em-ops:ops") ;;
```

and in the header comment, change the `--with-write` line to mention both: `#   ./install.sh --with-write  also the skills that write to Jira: jira-kanban and jira-em-ops`. Keep the header at the same number of lines (the `-h` option prints lines 2-10 of the file).

- [ ] **Step 5: README**

In `README.md`, directly after the table of `jk team` commands (find it with `rg -n "jk team rollup" README.md`), add a section in Rioplatense Spanish:

```markdown
### Cambiar varios issues a la vez (con guarda)

Sirve para pasar de «7 sin asignar» a «asignados». Es en dos pasos, y el segundo **solo lo hace una persona**:

| Comando | Qué hace |
|---|---|
| `jk plan move VIEW [KEY …] --to ROL` | Arma un plan para mover issues al estado que cumple ese rol. Solo lee Jira y guarda un archivo con las claves, el estado de origen, el de destino y la transición |
| `jk plan assign VIEW [KEY …] --person "Ana"` | Plan para reasignar. La persona nunca se adivina: si hay dos, lista las dos |
| `jk plan comment VIEW [KEY …] --text "…"` | Plan para dejar el mismo comentario |
| `jk plan revert ID` | Plan inverso de uno aplicado; no garantiza deshacer y lo dice |
| `jk apply ID` | Aplica **exactamente** ese plan. Muestra qué va a hacer y pide escribir `APRUEBO <n>` |

Las claves pueden ir solas o combinadas con `--unassigned`, `--older-than DÍAS` y `--role ROL` (los mismos filtros que `--list`). Un plan lleva hasta 25 issues (`--max`, hasta 200); mover a `delivered` o `dropped` exige `--allow-close`.

**`apply` necesita una terminal de verdad**: no funciona desde el chat, ni desde `!` de Claude Code, ni con un `echo APRUEBO 3 | …`. Corrélo en una ventana de terminal aparte. Lo mismo vale ahora para `jk create`, `jk push` y `jk assign` con `--apply`. Si no hay terminal, el comando no escribe nada, imprime la línea para copiar y sale con código 3.

Antes de cada escritura, `apply` vuelve a leer el issue: si alguien lo movió o reasignó después de planificar, lo saltea y lo informa. Reaplicar un plan es seguro (saltea lo ya hecho). Cada escritura queda en `~/.local/state/jk/writes.jsonl`.

La skill `jira-em-ops` (solo con `./install.sh --with-write`) prepara los planes; **nunca** corre `apply`.
```

Also update the line in the README that lists skills installed by default / with `--with-write` so that it names `jira-em-ops` among the `--with-write` ones (find it with `rg -n "with-write" README.md`).

- [ ] **Step 6: Spec results**

Append to `docs/superpowers/specs/2026-10-10-jira-em-fase-3-design.md` a section «Resultados de la fase 3» (Rioplatense Spanish) that lists: what shipped (modules `guard`, `state`, `plan`, `applier`, `plan_cli`; `Jira.transitions/transition_by_id/add_comment/snapshot`; `cli.main(confirm=)`; skill `jira-em-ops`), the English output tokens that replaced the Spanish ones in the spec (`applied`, `already there`, `changed`, `ambiguous`, `no path`, `required fields`), the ruling that `apply` and `plan` use no per-project journal (the global log is the record), the known limitation that `jk create --apply` asks for the approval before it can fail on a pending `--assign-open` decision, and the test count (run the suite and write the real number). Leave the line «Prueba real en el proyecto sandbox: pendiente» for Task 11.

- [ ] **Step 7: Run the tests and both suites**

Run both full suites. Expected: `OK` on both.

- [ ] **Step 8: Commit**

```bash
git add ops/SKILL.md install.sh README.md tests docs/superpowers/specs/2026-10-10-jira-em-fase-3-design.md
git commit -m "feat(skills): jira-em-ops plans team changes and hands apply to the person"
```

---

### Task 11: Real acceptance in a sandbox project (manual, by the user)

**This task is not executable by an agent.** It writes to a real Jira, so it needs the user, a sandbox project and a terminal window. The executor stops here and hands the checklist to the user.

**Preconditions the user provides:** a dedicated, deletable Jira project with 5 to 10 throwaway issues, a TEAM-like workflow (To Do, In Progress, Blocked, Done), and their account allowed to edit, transition, assign and comment there.

- [ ] **Step 1: Prepare** (user): `./install.sh --with-write`; `jk board setup SBX`; `jk team setup sandbox --boards SBX --people "<their name>"`.

- [ ] **Step 2: The guard refuses where it must** (user, record the output):
  - From Claude Code with `!`: `! jk apply <id>` → exit 3 and the line to run elsewhere, nothing written.
  - From the agent's Bash tool: the same.
  - `echo "APRUEBO 1" | jk apply <id>` in a terminal window → refused (stdin is not a terminal).

- [ ] **Step 3: One plan of each kind, applied from a terminal window** (user): `jk plan move sandbox KEY --to active` then `jk apply <id>`; the same for `assign` and `comment`. Compare the Jira issues with the plan and with `~/.local/state/jk/writes.jsonl`.

- [ ] **Step 4: The edge cases, for real** (user): change an issue's status in Jira between plan and apply → `changed`; apply twice → second run says `already applied` and writes nothing; `jk plan revert <id>` then `jk apply` of it → issues go back.

- [ ] **Step 5: Legacy guard** (user): `jk assign KEY "<name>" --apply` from `!` → exit 3; from a terminal window → asks `APRUEBO 1` and assigns.

- [ ] **Step 6: Record the result** (agent, from the user's output): fill the «Prueba real» line of «Resultados de la fase 3» with what was measured (dates, counts, any deviation), run both suites, and commit:

```bash
git add docs/superpowers/specs/2026-10-10-jira-em-fase-3-design.md
git commit -m "docs(spec): phase 3 real acceptance in the sandbox project"
```

---

## Self-review (done while writing)

- **Spec coverage:** guard (T1); plan files, hash, log (T2); transitions by id / comment / snapshot (T3); selection, the 8 rejection rules, move, describe (T4: rules 1-6; T5: 7-8 and assign/comment); apply semantics, idempotency, exit codes, log (T6); CLI, `confirm=`, `--max`, `--allow-close`, `--to-status`, filters (T7); revert (T8); legacy guard with `n` per command (T9); skill, install, README, spec results (T10); real acceptance and the `!`/Bash refusal check (T11). The hook `git-guardrails.sh` and `AGENTS.md` are phase 4, as the spec says.
- **Rulings recorded in the plan (carry to the ledger):** English output tokens instead of the spec's Spanish ones; `apply`/`plan` skip the per-project journal; `create --apply` asks before a pending `--assign-open` decision can fail; `team_cli._context` renamed `context` (public) because `plan_cli` consumes it.
- **Type consistency:** `plan.move/assign/comment/revert` return bodies without `id`/`hash`; `state.save_plan` adds them; `applier.run(jira, plan, confirm, command, now)`; `guard.confirm(n, summary, command, streams, open_tty)`; `confirm` injected into `cli.main` has the first three parameters.
