# jira-em fase 4: cierre, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the jira-em work: a second mechanical layer (hook) against an agent applying plans, current agent instructions, one common log of everything `jk` wrote, two small fixes to `apply`/`revert`, verified citations, docs, and the repo rename.

**Architecture:** Code changes are small and local: `journal.journal` gets an `also` tee that `cli._client` points at `state.log_write`; `plan_cli.run_apply` re-checks profiles; `plan.revert` learns `allow_close`. The hook is a shell file outside the repo, so the repo ships a check script (`tools/check-guardrails.sh`) and a patch the person applies. `AGENTS.md` and the root `README.md` live in `~/CurrentCode/SPECKIT/`, which is **not** a git repository: they are edited in place with a backup copy and a shown diff, never committed.

**Tech Stack:** Python 3 stdlib (3.9 compatible), `unittest`, bash + `jq` for the hook check.

**Spec:** `docs/superpowers/specs/2026-10-10-jira-em-fase-4-design.md` (binding). Also `2026-10-10-jira-em-fase-3-design.md` («Límite honesto», «Resultados de la fase 3»).

## Global Constraints

- Tests: `python3 -m unittest discover -s tests` green on `python3` **and** `/usr/bin/python3` (3.9) after every code task. Baseline today: 599 tests.
- The suite never touches the network, the real `~/.config/jk`, the real `~/.local/state/jk` or real Jira (`tests/helpers.py` isolates both directories).
- Code, skills, CLI messages and shell comments of the hook **may follow the file they live in** (the hook is in Spanish); documentation for people in Rioplatense Spanish (AGENTS.md).
- Commits (repo `jira-kanban`): conventional commits, **no** Co-Authored-By or AI attribution (the user's global rule overrides any harness reminder). No push, no merge to `main` without being asked.
- **Never write to `~/.claude/hooks/` or `~/.claude/settings.json`.** The agent prepares a patch; the person applies it. Work on a copy under the scratchpad directory.
- `~/CurrentCode/SPECKIT/` (root) is not a git repo: before editing `AGENTS.md` or `README.md` there, copy each to the scratchpad as `<name>.orig` and show `diff -u` at the end.
- Never print, log or commit Jira credentials (`IC_JIRA_*`). Nothing here writes to a real Jira.
- A cited URL, repo or line must exist: do not write the new repo name anywhere before the person renamed it on GitHub (Task 8).

## Review Focus

Failure modes the spec implies but a straight reading would not exercise; each has a test or a measured check in the task named.

1. **A plan whose board lost its profile (or left the view) before `apply`** must be refused with a message, not crash with `KeyError`. → Task 2.
2. **The common log failing** (unwritable folder, a tee function that raises) must never break or fail the legacy write that already happened. → Task 1.
3. **A legacy-write line in the common log must never count as an applied plan** (`state.applied` keys on `plan`). → Task 1.
4. **Hook false negatives and false positives:** `jk apply` behind `rtk`, `python3 …/jk.py`, an absolute path, `&&`; and no block on a commit message, `echo`, `rg`, `jk applyx`, `jk plan …`. → Task 4.
5. **Revert that closes issues without saying so:** reopening then reverting must demand `--allow-close`; reverting a non-closing plan must not. → Task 3.

---

### Task 1: One common log

**Files:**
- Modify: `jkan/journal.py` (the `journal` function)
- Modify: `jkan/cli.py` (`_client`, import `state`)
- Create: `tests/test_common_log.py`

**Interfaces:**
- Consumes: `state.log_write(entry: dict, now=None) -> bool` (never raises on `OSError`).
- Produces: `journal.journal(project: Path, command: str, now=None, also: Optional[Callable[[dict], None]] = None) -> Callable[[dict], None]`. Each write goes to the project log exactly as before and, if `also` is given, to `also({"command": command, **entry, "result": "ok"})`; an exception in `also` is swallowed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_common_log.py`:

```python
from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import make_project, state_dir
from jkan import cli, journal, state


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TeeTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.project = make_project()

    def test_a_write_goes_to_the_project_log_as_before_and_to_the_common_one(self):
        write = journal.journal(self.project, "create", now=lambda: "T1", also=state.log_write)
        write({"action": "update", "key": "PLATE-1", "fields": {"summary": "x"}})
        self.assertEqual(lines(self.project / ".jira-kanban" / "jira-writes.jsonl"),
                         [{"ts": "T1", "tool": "jira-kanban", "command": "create", "action": "update",
                           "key": "PLATE-1", "fields": {"summary": "x"}}])
        [common] = lines(self.base / "writes.jsonl")
        self.assertEqual((common["tool"], common["command"], common["action"], common["key"], common["result"]),
                         ("jk", "create", "update", "PLATE-1", "ok"))
        self.assertIn("ts", common)

    def test_the_common_line_has_no_plan_so_it_never_counts_as_an_applied_plan(self):
        journal.journal(self.project, "push", also=state.log_write)({"action": "update", "key": "PLATE-1", "fields": {}})
        [common] = lines(self.base / "writes.jsonl")
        self.assertNotIn("plan", common)
        self.assertEqual(state.applied("abcdef123456"), set())
        self.assertEqual(state.applied(""), set())

    def test_without_a_tee_nothing_goes_to_the_common_log(self):
        journal.journal(self.project, "push")({"action": "update", "key": "PLATE-1", "fields": {}})
        self.assertFalse((self.base / "writes.jsonl").exists())

    def test_a_tee_that_raises_never_breaks_the_write(self):
        def broken(entry):
            raise RuntimeError("boom")

        journal.journal(self.project, "push", also=broken)({"action": "update", "key": "PLATE-1", "fields": {}})
        self.assertEqual(len(lines(self.project / ".jira-kanban" / "jira-writes.jsonl")), 1)

    def test_a_state_folder_that_cannot_be_written_never_breaks_the_write(self):
        (self.base / "writes.jsonl").mkdir()  # a directory where the file should be
        journal.journal(self.project, "push", also=state.log_write)({"action": "update", "key": "PLATE-1", "fields": {}})
        self.assertEqual(len(lines(self.project / ".jira-kanban" / "jira-writes.jsonl")), 1)


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()
        self.project = make_project()

    def journal_of(self, command):
        with mock.patch.object(cli.config, "credentials", return_value=("https://x.atlassian.net", "e@x", "t")), \
                mock.patch.object(cli, "Jira") as jira:
            cli._client(self.project, command)
        return jira.call_args.kwargs["journal"]

    def test_the_legacy_commands_write_to_both_logs(self):
        self.journal_of("assign")({"action": "assign", "key": "PLATE-2", "accountId": "acc-ana"})
        self.assertEqual(len(lines(self.project / ".jira-kanban" / "jira-writes.jsonl")), 1)
        [common] = lines(self.base / "writes.jsonl")
        self.assertEqual((common["command"], common["key"], common["accountId"]), ("assign", "PLATE-2", "acc-ana"))

    def test_plan_and_apply_pass_no_journal_so_their_lines_are_not_written_twice(self):
        self.assertIsNone(self.journal_of(None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m unittest discover -s tests -p "test_common_log.py" 2>&1 | tail -6`
Expected: `TypeError: journal() got an unexpected keyword argument 'also'` (and `ClientTest` fails on the missing common line); `test_without_a_tee…` and `test_plan_and_apply…` may already pass: they are regression guards.

- [ ] **Step 3: Implement the tee in `jkan/journal.py`**

Replace the docstring of the module's second paragraph and the `journal` function so the file reads (keep `_utc_now` and imports as they are):

```python
def journal(project: Path, command: str, now: Optional[Callable[[], str]] = None,
            also: Optional[Callable[[dict], None]] = None) -> Callable[[dict], None]:
    """A writer for Jira(journal=...). It never raises: a log that cannot be written must not undo the write.

    `also` gets the same write as `{"command", **entry, "result": "ok"}`: jk passes state.log_write so the common log
    (~/.local/state/jk/writes.jsonl) holds everything jk wrote. That line carries no `plan`, so it is never an applied plan."""
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
```

- [ ] **Step 4: Point `cli._client` at it**

In `jkan/cli.py`: add `state` to the `from . import (…)` block (alphabetical: between `standup` and `stats`, because `state` < `stats`), and change the return of `_client` to:

```python
    return Jira(*creds, journal=journal.journal(project, command, also=state.log_write) if command else None)
```

- [ ] **Step 5: Run the tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_common_log.py" 2>&1 | tail -4` → `Ran 7 tests … OK`.
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` and `/usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3`. Expected: both `OK` (606 tests; `test_journal.py` is unchanged and still passes).

- [ ] **Step 6: Commit**

```bash
git add jkan/journal.py jkan/cli.py tests/test_common_log.py
git commit -m "feat(journal): create, push and assign also write to the common log"
```

---

### Task 2: `apply` re-checks the profiles

**Files:**
- Modify: `jkan/plan_cli.py` (`run_apply`, imports)
- Modify: `tests/test_plan_cli.py` (new tests in `ApplyTest`)

**Interfaces:**
- Consumes: `team_cli.context(name) -> (view, profiles)` (profiles = every saved profile); `plan.check_profiles(selection, profiles)` (uses `i["key"]`, raises `plan.Refused`); `roles.project_of(key)`.
- Produces: `run_apply` exits 1 before `applier.run` (so before any approval prompt or write) when a board of the plan has no profile or has undecided statuses.

- [ ] **Step 1: Write the failing tests**

Add to `class ApplyTest(Base)` in `tests/test_plan_cli.py` (before `test_a_read_only_command_never_needs_the_guard`):

```python
    def test_a_profile_that_lost_its_roles_after_planning_is_refused_before_asking(self):
        pid = self.planned()
        board_profile.save(fx.profile("TEAM", decide_waiting=False))
        asked = []
        code, _, err = run(["apply", pid], self.jira, confirm=lambda n, s, c: asked.append(n))
        self.assertEqual((code, asked, self.jira.writes), (1, [], []))
        self.assertIn("without a role", err)

    def test_a_plan_whose_board_has_no_profile_any_more_is_refused_not_a_crash(self):
        pid = self.planned()  # TEAM-1
        views.save(fx.view(boards=("DESK",)))
        (self.config / "profiles" / "TEAM.json").unlink()
        asked = []
        code, _, err = run(["apply", pid], self.jira, confirm=lambda n, s, c: asked.append(n))
        self.assertEqual((code, asked, self.jira.writes), (1, [], []))
        self.assertIn("no profile for TEAM", err)
```

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_plan_cli.py" 2>&1 | tail -12`
Expected: the first test fails (code 0, a write happened); the second fails with `KeyError`-free success or a traceback because nothing checks the board.

- [ ] **Step 3: Implement in `jkan/plan_cli.py`**

Change the import to include `roles`: `from . import applier, guard, people, plan, roles, state, team, team_cli`. In `run_apply`, replace the line `team_cli.context(saved["view"])` with:

```python
        _, profiles = team_cli.context(saved["view"])
        lacking = sorted({roles.project_of(i["key"]) for i in saved["items"]} - set(profiles))
        if lacking:
            raise plan.Refused(f"no profile for {', '.join(lacking)}: run jk board setup {lacking[0]}, then plan again")
        plan.check_profiles(saved["items"], profiles)
```

- [ ] **Step 4: Run the tests and both suites**

Run: `python3 -m unittest discover -s tests -p "test_plan_cli.py" 2>&1 | tail -4` → `OK`. Then both full suites. Expected: `OK` (608 tests).

- [ ] **Step 5: Commit**

```bash
git add jkan/plan_cli.py tests/test_plan_cli.py
git commit -m "fix(apply): refuse a plan whose board lost its profile or its roles before asking for approval"
```

---

### Task 3: `revert` and the closing flag

**Files:**
- Modify: `jkan/plan.py` (`revert`)
- Modify: `jkan/plan_cli.py` (parser and the `revert` branch of `_plan`)
- Modify: `tests/test_plan.py`, `tests/test_plan_cli.py`

**Interfaces:**
- Consumes: Task 8 of phase 3: `plan.revert(jira, original, profiles, now=None)`; `plan.CLOSING`.
- Produces: `plan.revert(jira, original, profiles, now=None, allow_close=False)`; raises `Refused("reverting closes issues: add --allow-close")` when an inverse item lands on a `delivered`/`dropped` status and `allow_close` is false. CLI: `jk plan revert ID [--allow-close]`.

- [ ] **Step 1: Write the failing tests**

Add to `class RevertTest(Base)` in `tests/test_plan.py`:

```python
    def test_reverting_a_reopen_closes_again_and_needs_allow_close(self):
        from jkan import applier
        selection = [self.put("TEAM-1", "delivered")]
        saved = state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jk apply x", now=NOW)
        with self.assertRaisesRegex(plan.Refused, "reverting closes issues: add --allow-close"):
            plan.revert(self.jira, saved, self.profiles, now=NOW)
        body = plan.revert(self.jira, saved, self.profiles, now=NOW, allow_close=True)
        self.assertEqual(body["items"][0]["to"]["role"], "delivered")
        self.assertEqual(body["options"], {"revert_of": saved["id"]})
        self.assertIn("closes 1", plan.describe(dict(body, id="abcdef123456")))

    def test_reverting_something_that_does_not_close_never_asks_for_the_flag(self):
        saved = self.applied_move(("TEAM-1",))
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual(body["items"][0]["to"]["role"], "todo")
```

Add a class to `tests/test_plan_cli.py` before the `if __name__` block:

```python
class RevertClosingCliTest(Base):
    def test_a_revert_that_closes_needs_the_flag_on_the_command_line(self):
        self.put("TEAM-1", "delivered")
        self.serve()
        _, out, _ = run(["plan", "move", "plataforma", "TEAM-1", "--to", "active"], self.jira)
        first = plan_id(out)
        run(["apply", first], self.jira)
        code, _, err = run(["plan", "revert", first], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("add --allow-close", err)
        code, out, _ = run(["plan", "revert", first, "--allow-close"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("TEAM-1: En curso -> Done", out)
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "5>2")])  # only the first apply wrote; planning the revert did not
```

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m unittest discover -s tests -p "test_plan*.py" 2>&1 | tail -10`
Expected: `TypeError … unexpected keyword argument 'allow_close'` and `error: unrecognized arguments: --allow-close`.

- [ ] **Step 3: Implement**

In `jkan/plan.py` change the signature to `def revert(jira, original: dict, profiles: Dict[str, dict], now: Optional[Callable[[], str]] = None, allow_close: bool = False) -> dict:` and, right before `options = {"revert_of": original["id"]}`, add:

```python
    if not allow_close and any(i.get("to") and i["to"].get("role") in CLOSING for i in items):
        raise Refused("reverting closes issues: add --allow-close")
```

(An `assign` inverse has `to` as a person without `role`, so it never triggers.)

In `jkan/plan_cli.py` add `undo.add_argument("--allow-close", action="store_true", help="needed when the inverse closes issues")` after `undo.add_argument("id")`, and call `plan.revert(jira(), original, profiles, allow_close=args.allow_close)` in the `revert` branch.

- [ ] **Step 4: Run the tests and both suites**

Run `python3 -m unittest discover -s tests -p "test_plan*.py" 2>&1 | tail -4` → `OK`, then both full suites → `OK` (611 tests).

- [ ] **Step 5: Commit**

```bash
git add jkan/plan.py jkan/plan_cli.py tests/test_plan.py tests/test_plan_cli.py
git commit -m "fix(plan): reverting a reopen needs --allow-close like any plan that closes"
```

---

### Task 4: The hook's second layer: check script and patch

**Files:**
- Create: `tools/check-guardrails.sh` (executable)
- Create: `tools/git-guardrails-jk-apply.patch`
- Scratchpad only (not committed): `git-guardrails.new.sh`
- **Not touched:** `~/.claude/hooks/git-guardrails.sh`

**Interfaces:**
- Consumes: the hook protocol: JSON on stdin `{"tool_input":{"command":"…"}}`, exit 2 = blocked, exit 0 = allowed; the hook's `coincide`, `bloquear`, `INICIO` and `JK` variables.
- Produces: `tools/check-guardrails.sh [HOOK]` (exit 0 all cases right, 1 some wrong, 2 cannot run); a unified diff that adds rule R1 (`jk apply`) and R2 (`jk apply` together with a pseudo-terminal tool).

- [ ] **Step 1: Write the check script**

Create `tools/check-guardrails.sh` and `chmod +x` it:

```bash
#!/usr/bin/env bash
# Runs a list of commands through a git-guardrails hook and compares the exit code (2 = blocked, 0 = allowed).
#   tools/check-guardrails.sh [HOOK]    HOOK defaults to ~/.claude/hooks/git-guardrails.sh
# Exit: 0 every case behaved, 1 some case did not, 2 it could not run. Not part of `unittest discover`: the hook is the
# user's file and may not be updated yet.
set -uo pipefail

HOOK="${1:-$HOME/.claude/hooks/git-guardrails.sh}"
[ -x "$HOOK" ] || { echo "no executable hook at $HOOK" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

total=0
wrong=0
check() {  # check <expected exit code> <command line>
  local want="$1" cmd="$2" got
  got=$(jq -n --arg c "$cmd" '{tool_input: {command: $c}}' | "$HOOK" >/dev/null 2>&1; echo $?)
  total=$((total + 1))
  if [ "$got" != "$want" ]; then
    wrong=$((wrong + 1))
    echo "WRONG want=$want got=$got :: $cmd"
  fi
}

# blocked: the writers that already existed
check 2 'git push origin main'
check 2 'jk push PLATE-1 --apply'
check 2 'jk create --spec s.json --apply'
check 2 'jk assign PLATE-1 Ana --apply'
# blocked: applying a plan, behind every prefix the hook accepts
check 2 'jk apply abc123def456'
check 2 'rtk jk apply abc123def456'
check 2 'python3 /Users/x/jira-kanban/jk.py apply abc123def456'
check 2 'cd /tmp && jk apply abc123def456'
check 2 '/Users/x/.local/bin/jk apply abc123def456'
# blocked: a pseudo-terminal typing the approval for it
check 2 "tmux send-keys 'jk apply abc123def456' Enter"
check 2 "expect -c 'spawn jk apply abc123def456'"
check 2 'script -q /dev/null jk apply abc123def456'
check 2 "python3 -c 'import pty; pty.spawn(\"jk apply abc123def456\".split())'"
# allowed
check 0 'jk plan move plataforma TEAM-1 --to active'
check 0 'jk plan revert abc123def456'
check 0 'jk team status plataforma --list'
check 0 'jk push PLATE-1'
check 0 'jk assign PLATE-1 Ana'
check 0 'jk applyx'
check 0 'git status'
check 0 'git commit -m "docs: jk apply"'
check 0 'echo jk apply'
check 0 'rg -n "jk apply" docs'

echo "$((total - wrong))/$total cases behaved as expected"
[ "$wrong" -eq 0 ]
```

- [ ] **Step 2: Run it on the real hook to see the new cases fail (red)**

Run: `tools/check-guardrails.sh; echo "exit=$?"`
Expected: `WRONG want=2 got=0` for exactly the nine `jk apply` / pseudo-terminal cases, the other 14 right, `exit=1`. If any *other* case is wrong, stop and read the hook before going on: the check or the hook is not what this plan assumes.

- [ ] **Step 3: Build the patched copy in the scratchpad**

```bash
SCRATCH=/private/tmp/claude-504/-Users-josefigueredo-CurrentCode-SPECKIT/7e3c6941-571f-4c6f-b047-496874b2ab53/scratchpad
cp ~/.claude/hooks/git-guardrails.sh "$SCRATCH/git-guardrails.new.sh"
python3 - "$SCRATCH/git-guardrails.new.sh" <<'EOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
anchor = '  && bloquear "jk create / jk push / jk assign con --apply escriben en Jira"\n'
assert text.count(anchor) == 1
new = anchor + '''
# jk apply escribe en Jira lo que dice un plan guardado (jk plan solo lee y pasa). Lo corre el usuario en una ventana de
# terminal aparte, donde escribe APRUEBO <n>: bajo `!` tampoco funciona porque no hay terminal interactiva.
bloquear_terminal() {
  cat >&2 <<EOF
BLOQUEADO — $1.

No tenés autoridad para ejecutarlo. Pasale al usuario el comando: lo corre él en una ventana de terminal aparte, donde escribe APRUEBO <n>.
(Bajo \\`!\\` tampoco funciona: no hay terminal interactiva.)
EOF
  exit 2
}
coincide "${JK}apply([[:space:]]|$)" && bloquear_terminal "jk apply escribe en Jira lo que dice un plan guardado"

# Rodeo que la guarda APRUEBO no ve: un pseudo-terminal que escribe la aprobación (tmux send-keys, expect, script, pty...).
# Va aunque `jk apply` no esté al inicio del comando. Falso positivo asumido: un mensaje que nombre las dos cosas a la vez.
APLICA='jk(\\.py)?[[:space:]]+apply([[:space:]]|$)'
PTY='(tmux[[:space:]]+send-keys|(^|[^[:alnum:]_])(expect|unbuffer|socat)([[:space:]]|$)|script[[:space:]]+-|pty\\.)'
if coincide "$APLICA" && coincide "$PTY"; then
  bloquear_terminal "jk apply a través de un pseudo-terminal salta la aprobación de una persona"
fi
'''
open(path, "w", encoding="utf-8").write(text.replace(anchor, new, 1))
EOF
bash -n "$SCRATCH/git-guardrails.new.sh" && echo "syntax ok"
```

Expected: `syntax ok`. (The inner heredoc terminator `EOF` inside the Python string is part of the patched bash file, not of this outer heredoc, because the outer one is `<<'EOF'` closed by the last `EOF` line: if your shell cuts it short, write the python script to `$SCRATCH/patch_hook.py` with the Write tool and run it.)

- [ ] **Step 4: Run the check on the patched copy (green)**

Run: `chmod +x "$SCRATCH/git-guardrails.new.sh" && tools/check-guardrails.sh "$SCRATCH/git-guardrails.new.sh"; echo "exit=$?"`
Expected: `23/23 cases behaved as expected`, `exit=0`. If a *blocked* case still passes or an *allowed* case is blocked, fix the inserted regex (not the case) until all 23 are right; the cases are the spec.

- [ ] **Step 5: Produce the patch and prove it applies**

```bash
diff -u --label a/git-guardrails.sh --label b/git-guardrails.sh ~/.claude/hooks/git-guardrails.sh "$SCRATCH/git-guardrails.new.sh" > tools/git-guardrails-jk-apply.patch
cp ~/.claude/hooks/git-guardrails.sh "$SCRATCH/trial.sh" && patch --dry-run "$SCRATCH/trial.sh" < tools/git-guardrails-jk-apply.patch && patch "$SCRATCH/trial.sh" < tools/git-guardrails-jk-apply.patch && cmp "$SCRATCH/trial.sh" "$SCRATCH/git-guardrails.new.sh" && echo "patch reproduces the tested file"
```

Expected: `patch reproduces the tested file`. (`diff` exits 1 when files differ: that is normal.)

- [ ] **Step 6: Commit (the hook itself stays for the person)**

```bash
git add tools/check-guardrails.sh tools/git-guardrails-jk-apply.patch
git commit -m "feat(tools): guardrails check and the hook patch that blocks jk apply and pseudo-terminal rodeos"
```

- [ ] **Step 7: Hand over (agent says, person does)**

Tell the person, in their terminal (`!` is fine: it needs no TTY):

```
! cp ~/.claude/hooks/git-guardrails.sh ~/.claude/hooks/git-guardrails.sh.bak-2026-10-10 && patch ~/.claude/hooks/git-guardrails.sh < ~/CurrentCode/SPECKIT/Harness/jira-kanban/tools/git-guardrails-jk-apply.patch && ~/CurrentCode/SPECKIT/Harness/jira-kanban/tools/check-guardrails.sh
```

Expected from them: `23/23 cases behaved as expected`. Record that output for Task 7. Do **not** run it for them.

---

### Task 5: `AGENTS.md` and the root `README.md`

**Files:**
- Modify (in place, not a git repo): `/Users/josefigueredo/CurrentCode/SPECKIT/AGENTS.md`, `/Users/josefigueredo/CurrentCode/SPECKIT/README.md`
- Backups: `$SCRATCH/AGENTS.md.orig`, `$SCRATCH/README.md.orig`

**Interfaces:**
- Consumes: nothing from earlier tasks (text only); Task 4's rules are what the new text describes.
- Produces: a shown `diff -u` of both files.

- [ ] **Step 1: Back up and edit**

```bash
SCRATCH=/private/tmp/claude-504/-Users-josefigueredo-CurrentCode-SPECKIT/7e3c6941-571f-4c6f-b047-496874b2ab53/scratchpad
ROOT=/Users/josefigueredo/CurrentCode/SPECKIT
cp "$ROOT/AGENTS.md" "$SCRATCH/AGENTS.md.orig" && cp "$ROOT/README.md" "$SCRATCH/README.md.orig"
python3 - "$ROOT" <<'EOF'
import sys
root = sys.argv[1]

def edit(path, old, new):
    text = open(path, encoding="utf-8").read()
    assert text.count(old) == 1, (path, old[:60])
    open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))

edit(root + "/AGENTS.md",
     "- **El usuario publica.** El push, los PR, los merges, `wow close --apply`, `wow jira fix-fields --apply`, `jk create|push --apply`\n"
     "  y `/spec-kit.sync-status` (los cuatro escriben en Jira) los hace él. Vos dejás el commit o el comando listo; él lo corre con `!`. En Claude Code, el hook\n"
     "  `~/.claude/hooks/git-guardrails.sh` bloquea esos comandos (sin `--apply`, los de `wow` son simulación y pasan).",
     "- **El usuario publica.** El push, los PR, los merges, `wow close --apply`, `wow jira fix-fields --apply`, `jk create|push|assign --apply`,\n"
     "  `jk apply <id>` y `/spec-kit.sync-status` (los cinco escriben en Jira) los hace él. Vos dejás el commit o el comando listo; él lo corre con `!`,\n"
     "  salvo `jk apply` y los `jk … --apply`: exigen una terminal interactiva y se niegan bajo `!` (no hay TTY), así que se corren en una ventana de\n"
     "  terminal aparte. `jk plan …` solo lee Jira y guarda un archivo: ese sí lo corrés vos. En Claude Code, el hook\n"
     "  `~/.claude/hooks/git-guardrails.sh` bloquea esos comandos, también cuando se los intenta pasar por un pseudo-terminal (`tmux send-keys`, `expect`,\n"
     "  `script`); sin `--apply`, los de `wow` son simulación y pasan, y `jk plan` pasa.")

edit(root + "/README.md",
     "| `Harness/jira-kanban/` | Skill `jira-kanban` para Claude Code, Codex y Cursor: crea una épica de Jira desde la conversación y la espeja como kanban local (`jk`). Para trabajo fuera de un flujo WoW |",
     "| `Harness/jira-kanban/` | CLI `jk` y 4 skills (`jira-standup`, `jira-em`, `jira-em-ops`, `jira-kanban`) para Claude Code, Codex y Cursor: reportes de uno mismo y del equipo, cambios de varios issues con plan y aprobación en una terminal, y épicas de Jira espejadas como kanban local. Para trabajo fuera de un flujo WoW |")
EOF
diff -u "$SCRATCH/AGENTS.md.orig" "$ROOT/AGENTS.md"; diff -u "$SCRATCH/README.md.orig" "$ROOT/README.md"
```

Expected: both diffs show only the changed lines above (the repo-name cell of the README row is unchanged until Task 8). If the `assert` fails, the file was edited since this plan: re-read the bullet and adapt the `old` text, keeping the new text.

- [ ] **Step 2: No commit**

The root is not a git repository (`git -C ~/CurrentCode/SPECKIT rev-parse` fails). Show both diffs in the final message and say they are applied in place; the originals are in the scratchpad.

---

### Task 6: Re-verify every cited line

**Files:**
- Modify: `docs/superpowers/specs/2026-10-08-jira-standup-design.md`, `2026-10-09-jira-em-design.md`, `2026-10-10-jira-em-fase-3-design.md` (only the numbers or phrases found stale)
- Scratchpad: `cites.py`, `cites.txt`

**Interfaces:**
- Consumes: the final code of Tasks 1-3 (line numbers move when they are committed: run this after them).
- Produces: a table «cita → vigente / corregida» for the final message and the phase-4 spec results.

- [ ] **Step 1: List the citations with their context**

```bash
SCRATCH=/private/tmp/claude-504/-Users-josefigueredo-CurrentCode-SPECKIT/7e3c6941-571f-4c6f-b047-496874b2ab53/scratchpad
cat > "$SCRATCH/cites.py" <<'EOF'
import re, pathlib
root = pathlib.Path(".")
for spec in sorted(root.glob("docs/superpowers/specs/*.md")):
    for n, line in enumerate(spec.read_text(encoding="utf-8").splitlines(), 1):
        for mod, ln in re.findall(r"([a-z_]+\.py):(\d+)", line):
            src = next(root.glob(f"**/{mod}"), None)
            target = src.read_text(encoding="utf-8").splitlines() if src else []
            at = int(ln)
            print(f"== {spec.name}:{n} cites {mod}:{ln}\n   spec says: {line.strip()[:200]}")
            for i in range(max(1, at - 1), min(len(target), at + 1) + 1):
                print(f"   {mod}:{i}: {target[i-1][:150]}")
EOF
python3 "$SCRATCH/cites.py" > "$SCRATCH/cites.txt"; wc -l "$SCRATCH/cites.txt"; rg -c '^== ' "$SCRATCH/cites.txt"
```

Expected: 14 `== …` entries (the count measured when the spec was written; if it differs, use the real number).

- [ ] **Step 2: Judge each citation**

Read `$SCRATCH/cites.txt` in full. For each entry decide with the evidence on the page: does the cited line (and the one around it) say what the spec sentence claims? Outcomes: **vigente** (nothing to do), **corregida** (the code moved: find the right line with `rg -n "<fragment>" jkan/<module>.py` and change the number in the spec), or **frase mal** (the line exists but says something else: fix the sentence, not just the number). Apply the edits with `Edit`. Do not "fix" a citation you cannot explain.

- [ ] **Step 3: Record and commit**

Write the table (one line per citation: `spec:línea → módulo:línea → vigente|corregida|frase corregida`) into the phase-4 spec under the «Resultados de la fase 4» heading that Task 7 creates; if Task 7 has not run yet, keep it in the scratchpad and paste it there.

```bash
git add docs/superpowers/specs
git commit -m "docs(spec): re-verify the cited lines against the code"
```

(If nothing was stale, skip the commit and say so: that is a result.)

---

### Task 7: Docs and results

**Files:**
- Modify: `README.md` (this repo)
- Modify: `docs/superpowers/specs/2026-10-09-jira-em-design.md` (the «Escritura que ya existe sin guardia» risk)
- Modify: `docs/superpowers/specs/2026-10-10-jira-em-fase-4-design.md` (append «Resultados de la fase 4»)

**Interfaces:**
- Consumes: Task 4 Step 7's output (the person's `23/23 …` line, if already run), Task 6's table, the final test count.

- [ ] **Step 1: README: the hook and the common log**

In `README.md`, in the section «Cambiar varios issues a la vez (con guarda)» change the sentence that starts «Cada escritura queda en `~/.local/state/jk/writes.jsonl`.» to:

```markdown
Cada escritura queda en `~/.local/state/jk/writes.jsonl`, también las de `jk create|push|assign --apply` (el registro de cada proyecto, `.jira-kanban/jira-writes.jsonl`, sigue como antes). Las líneas de un plan llevan `plan`; las de los comandos viejos, no.
```

and add, directly after that section's last paragraph (the one about `jira-em-ops`), a new subsection:

```markdown
### Segunda capa: el hook de Claude Code

La guarda `APRUEBO` frena lo accidental y lo inducido desde el chat, `!` o la herramienta Bash, pero **no a un agente que abra un pseudo-terminal y escriba la aprobación**. Para eso, `~/.claude/hooks/git-guardrails.sh` bloquea `jk apply` y cualquier comando que lo combine con `tmux send-keys`, `expect`, `unbuffer`, `socat`, `script -` o `pty.`. `jk plan …` pasa. Se verifica con `tools/check-guardrails.sh` (23 casos); el parche está en `tools/git-guardrails-jk-apply.patch` y lo aplica la persona. El hook solo cubre a Claude Code: en Codex y Cursor quedan la guarda y las reglas de `AGENTS.md`.
```

- [ ] **Step 2: Master spec: close the open decision**

In `docs/superpowers/specs/2026-10-09-jira-em-design.md`, replace the sentence ending the risk «Escritura que ya existe sin guardia»:

```
Decisión pendiente: aplicar el mismo guardia a esos tres comandos, o dejarlos
  fuera de la instalación por defecto.
```

with:

```
Resuelto: la guarda de la fase 3 cubre esos tres comandos y el hook de la fase 4 bloquea
  `jk apply` y su rodeo por pseudo-terminal.
```

(Use `Edit`; if the two-line text differs by whitespace, read the lines first and match them.)

- [ ] **Step 3: Phase-4 spec: results**

Append to the phase-4 spec a section `## Resultados de la fase 4` in Rioplatense Spanish with: what shipped (tee de `journal`, `apply` revalida perfiles, `revert --allow-close`, `tools/check-guardrails.sh` y el parche, `AGENTS.md` y README raíz editados en el lugar —no es un repo—, citas re-verificadas con la tabla de la Tarea 6, README), the real test count (run both suites and write the number), the output of the person's `check-guardrails.sh` if available or the line `Hook aplicado por la persona y verificado: pendiente`, and the pending items: prueba real en el sandbox (Tarea 11 de la fase 3), `Renombre del repo: pendiente` (Task 8), los dos menores de la fase 3 que quedaron afuera, los menores de la fase 1 y `jk done|stats` por categoría.

- [ ] **Step 4: Run both suites and commit**

Run both full suites. Expected: `OK` on both.

```bash
git add README.md docs/superpowers/specs
git commit -m "docs: phase 4 results, the hook layer and the common log"
```

---

### Task 8: Rename the repo (person first, then agent)

**This task starts with an action only the person can do.** The executor stops after Step 1 and waits for the new name.

- [ ] **Step 1: Ask for the name and hand over the GitHub step**

Ask the person for the new repository name (nothing is renamed or written with a guessed name). Tell them to rename it in GitHub (`Settings → General → Repository name`, organization `josefigueredo`); GitHub redirects the old name. Wait for their answer.

- [ ] **Step 2: Verify the new remote exists before writing it anywhere**

With `NEW` the name they gave:

```bash
git ls-remote git@github.com:josefigueredo/NEW.git HEAD
```

Expected: one line with a commit hash. If it errors, stop: the rename has not happened or the name is wrong.

- [ ] **Step 3: Update every mention**

```bash
rg -n "skill-kanban-jira" . ~/CurrentCode/SPECKIT/README.md ~/CurrentCode/SPECKIT/AGENTS.md
```

Replace each hit in this repo with the new name (`README.md`'s `git clone` and `cd` lines, any doc), and the root `README.md` cell for `Harness/jira-kanban/` (backup to the scratchpad first, as in Task 5). Then `git remote set-url origin git@github.com:josefigueredo/NEW.git` and `git remote -v`. Do not rename the local folder `Harness/jira-kanban` (other tools and `install.sh` links point at it) unless the person asks.

- [ ] **Step 4: Run both suites, commit, update results**

Run both full suites → `OK`. Change the phase-4 spec line `Renombre del repo: pendiente` to the real result (old name → new name, date, `git ls-remote` output hash prefix).

```bash
git add -A README.md docs
git commit -m "docs: the repository is now called NEW"
```

(Replace `NEW` in the message with the real name.) The push is the person's.

---

## Self-review (done while writing)

- **Spec coverage:** hook R1/R2, patch, check script with 23 cases, handover (Task 4); `AGENTS.md` + root README row (Task 5); common log incl. no-`plan` line, tee failure, no double logging for `plan`/`apply` (Task 1); `apply` profile revalidation (Task 2) and `revert --allow-close` (Task 3); citations (Task 6); README, master-spec risk, results (Task 7); rename with the «no URL before it exists» rule (Task 8). The two phase-3 minors left out (legacy `n`, re-apply summary) and the phase-1 minors are listed as pending in Task 7, as the spec says.
- **Case count:** 4 existing writers + 5 apply prefixes + 4 pseudo-terminal = 13 blocked; 10 allowed; total 23. Red run on the real hook: the 9 new blocked cases fail, 14 pass.
- **Type consistency:** `journal.journal(project, command, now=None, also=None)`; `state.log_write(entry, now=None)` is called with one argument by the tee; `plan.revert(jira, original, profiles, now=None, allow_close=False)`; `plan_cli` parser flag `--allow-close` on `revert` only.
- **Known risk to watch while executing:** Task 3's CLI test asserts the last write is the first apply's `5>2` (planning writes nothing); Task 4 Step 3 embeds a bash heredoc inside a Python heredoc — use the Write-tool fallback named there if the shell mangles it.
