from __future__ import annotations

import contextlib
import functools
import io
import json
import sys
import types
import unittest
from pathlib import Path

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
        self.assertTrue(command.startswith("jtk assign PLATE-600 "))
        self.assertIn("--tree --apply", command)
        self.assertIn("assigned 4 issue", out)

    def test_the_window_gets_a_row_per_issue_that_would_change(self):
        asked = Asked()
        run(self.args(self.epic, "--tree", "--apply"), self.jira, asked)
        rows = asked.calls[0][1].rows
        self.assertEqual([r[0] for r in rows], ["PLATE-600", "PLATE-601", "PLATE-602", "PLATE-603"])
        self.assertTrue(all(r[2] == "-> Matías Andrés Fernandez" for r in rows))
        self.assertIn("Matías Andrés Fernandez", asked.calls[0][1].heading)

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
        self.assertIn("jtk assign PLATE-601", err)


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

    def test_the_window_gets_a_row_per_issue_to_create(self):
        asked = Asked()
        run(self.args("--apply", "--assign-open"), self.jira, asked)
        summary = asked.calls[0][1]
        self.assertEqual(len(summary.rows), asked.calls[0][0])
        self.assertTrue(all(r[1] for r in summary.rows))

    def test_each_row_says_the_type_the_action_and_who_gets_it_never_a_spec_path(self):
        self.jira.users.append({"id": "acc-me", "name": "Ana Gómez", "email": "ana@x.com"})
        asked = Asked()
        run(self.args("--apply", "--assign-open"), self.jira, asked)
        rows = asked.calls[0][1].rows
        self.assertEqual(rows[0][0], "Epic")
        for key, _name, change in rows:
            self.assertNotIn("items[", key)  # a spec path means nothing to the person approving
            self.assertEqual(change, "Acción: Crear\nAsignado a: Ana Gómez")  # the person's name, not «vos»

    def test_what_nobody_gets_says_sin_asignar(self):
        asked = Asked()
        run(self.args("--apply", "--no-assign-open"), self.jira, asked)
        changes = {r[2] for r in asked.calls[0][1].rows}
        self.assertEqual(changes, {"Acción: Crear\nAsignado a: Sin asignar"})

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
        with contextlib.redirect_stdout(io.StringIO()):
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

    def test_the_window_shows_what_changes_in_each_issue(self):
        self.edit()
        asked = Asked()
        run(self.args("--apply"), self.jira, asked)
        [row] = asked.calls[0][1].rows
        self.assertEqual(row[0], "PLATE-603")
        self.assertIn("Backlog -> Done", row[2])

    def test_a_push_that_creates_issues_reaches_the_real_window_with_text_rows(self):
        from jkan import approval
        seen = []

        def runner(argv):
            seen.append(Path(argv[4]).read_text(encoding="utf-8"))
            return types.SimpleNamespace(returncode=0, stdout="approved")

        new = self.project / ".jira-kanban" / self.key / "tasks" / "_new-docs" / "task.md"
        new.parent.mkdir(parents=True)
        new.write_text("# [FE] Docs & más\n\nPor qué: no hay guía.\n\nQué: un README.\n\nHecho cuando: se publica.\n",
                       encoding="utf-8")

        class NoTty:
            def isatty(self):
                return False

        # available() also checks that the osascript file is executable; /usr/bin/osascript exists only on macOS and
        # the runner is fake, so point it at any executable that exists everywhere (CI runs on Linux)
        window = approval.DialogApprover(runner=runner, platform="darwin", osascript=sys.executable)
        confirm = functools.partial(guard.confirm, streams=(NoTty(),) * 3, dialog=window)
        code, _, _ = run(self.args("--apply", "--assign-open"), self.jira, confirm)
        self.assertEqual(code, 0)
        self.assertIn("Docs &amp; más", seen[0])
        self.assertTrue([w for w in self.jira.writes if w[0] == "create"])

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
