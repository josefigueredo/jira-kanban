"""What `jk push` prints is what the user approves before --apply: it has to show the change itself.

In the PLATE-539 run, a description edited at its end printed the same first 60 characters on both sides of the
arrow, a description that started with a line break was cut at it, and --apply ended without saying what happened.
"""
from __future__ import annotations

import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import cli
from test_cli import run

HEAD = "Por qué: al exportar una épica a Jira, Product Brain manda los story points a otro campo.\n\nQué: elegir por nombre.\n\n"


class ExcerptTest(unittest.TestCase):
    def test_a_change_at_the_end_shows_the_end(self):
        before, after = cli.excerpt(HEAD + "Hecho cuando: el PR está mergeado.", HEAD + "Hecho cuando: el PR está abierto.")
        self.assertIn("mergeado", before)
        self.assertIn("abierto", after)
        self.assertNotEqual(before, after)
        self.assertTrue(before.startswith("…") and after.startswith("…"))

    def test_line_breaks_print_as_spaces_on_one_line(self):
        before, after = cli.excerpt("PR #49 https://x/pull/49\ndiscover tomaba el primero", "Por qué: elige por nombre")
        self.assertNotIn("\n", before + after)
        self.assertEqual(before, "PR #49 https://x/pull/49 discover tomaba el primero")

    def test_short_values_print_whole(self):
        self.assertEqual(cli.excerpt("Backlog", "Done"), ("Backlog", "Done"))
        self.assertEqual(cli.excerpt("", "Por qué: x"), ("", "Por qué: x"))

    def test_an_excerpt_never_exceeds_the_width(self):
        before, after = cli.excerpt("a" * 300 + "X" + "b" * 300, "a" * 300 + "Y" + "b" * 300, width=60)
        self.assertLessEqual(len(before), 62)  # the width plus the two ellipses
        self.assertIn("X", before)
        self.assertIn("Y", after)


class PushOutputTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        run(["pull", self.key, "--project", str(self.project)], self.jira)
        self.task = self.project / ".jira-kanban" / self.key / "tasks/PLATE-603/task.md"

    def edit(self, old, new):
        self.task.write_text(self.task.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_the_dry_run_shows_where_a_description_changed(self):
        self.jira.issues["PLATE-603"]["description"] = HEAD + "Hecho cuando: el PR está mergeado."
        run(["pull", self.key, "--project", str(self.project)], self.jira)
        self.edit("el PR está mergeado.", "el PR está abierto.")
        _, out, _ = run(["push", self.key, "--project", str(self.project)], self.jira)
        line = next(ln for ln in out.splitlines() if ln.startswith("PLATE-603 description:"))
        self.assertIn("el PR está mergeado. -> ", line)
        self.assertTrue(line.endswith("el PR está abierto."))

    def test_apply_ends_with_a_summary(self):
        self.edit("status: Backlog", "status: Done")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "pushed: 1 written, 0 rejected, 0 created, 0 conflicts")

    def test_apply_counts_rejected_writes(self):
        self.jira.refuse_moves["PLATE-603"] = "none"
        self.edit("status: Backlog", "status: Done")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[-1], "pushed: 0 written, 1 rejected, 0 created, 0 conflicts")


if __name__ == "__main__":
    unittest.main()
