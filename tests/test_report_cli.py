from __future__ import annotations

import contextlib
import io
import json
import unittest
from datetime import date

from helpers import FakeJira, issue, make_project, flat
from jkan import cli

TODAY = date(2026, 10, 8)


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args + ["--project", str(make_project())], client=lambda project: jira, today=lambda: TODAY)
    return code, out.getvalue(), err.getvalue()


class ReportCliTest(unittest.TestCase):
    def test_done_prints_the_window_the_totals_and_the_tree_and_writes_nothing(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-5", category="done", status="Done", changed="2026-10-07")]
        code, out, _ = run(["done", "--since", "2026-10-01", "--until", "2026-10-07"], jira)
        self.assertEqual(code, 0)
        self.assertIn("## Hecho", out)
        self.assertIn("**Ventana:** 2026-10-01 → 2026-10-07", out)
        self.assertIn("**1 cerradas · 0 en curso**", out)
        self.assertIn("PLATE-5", out)
        self.assertIn('assignee = currentUser()', jira.jqls[0])
        self.assertIn('statusCategoryChangedDate < "2026-10-08"', jira.jqls[0])
        self.assertEqual(jira.writes, [])

    def test_done_without_until_stops_at_today(self):
        jira = FakeJira()
        run(["done", "--since", "2026-10-06"], jira)
        self.assertIn('statusCategoryChangedDate < "2026-10-09"', jira.jqls[0])

    def test_when_names_the_window_so_the_agent_computes_no_dates(self):
        jira = FakeJira()
        code, out, _ = run(["done", "--when", "last-week"], jira)  # TODAY is Thursday 2026-10-08
        self.assertEqual(code, 0)
        self.assertIn("**Ventana:** 2026-09-28 → 2026-10-04", out)
        self.assertIn('statusCategoryChangedDate < "2026-10-05"', jira.jqls[0])
        code, out, _ = run(["next", "--when", "next-week"], FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("**Ventana:** 2026-10-08 → 2026-10-18", out)

    def test_when_mixed_with_dates_or_missing_is_refused_before_asking_jira(self):
        for args in (["done", "--when", "yesterday", "--since", "2026-10-01"], ["done"], ["done", "--when", "ayer"],
                     ["next", "--when", "next-week", "--until", "2026-10-12"], ["next", "--when", "last-week"]):
            jira = FakeJira()
            code, _, err = run(args, jira)
            self.assertEqual(code, 1, args)
            self.assertTrue(err.strip(), args)
            self.assertEqual(jira.jqls, [], args)

    def test_every_json_output_is_one_line(self):
        code, out, _ = run(["done", "--when", "last-week", "--json"], FakeJira())
        self.assertEqual((code, out.count("\n")), (0, 1))
        self.assertIn("tree", json.loads(out))

    def test_a_bad_window_is_refused_before_asking_jira(self):
        for args in (["done", "--since", "ayer"], ["done", "--since", "2026-10-09"], ["next", "--until", "2026-10-01"],
                     ["stats", "--weeks", "0"], ["load", "--weeks", "99"]):
            jira = FakeJira()
            code, _, err = run(args, jira)
            self.assertEqual(code, 1, args)
            self.assertTrue(err.strip(), args)
            self.assertEqual(jira.jqls, [], args)

    def test_a_bad_window_with_a_person_asks_jira_nothing_at_all(self):
        for args in (["done", "--since", "ayer"], ["next", "--until", "2026-10-01"], ["stats", "--weeks", "0"]):
            jira = FakeJira()
            code, _, _ = run(args + ["--person", "Ana Gómez"], jira)
            self.assertEqual(code, 1, args)
            self.assertEqual((jira.jqls, jira.searches), ([], []), args)

    def test_a_unique_person_is_queried_by_account_id(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", assignee={"id": "acc-ana", "name": "Ana Gómez"})]
        code, out, _ = run(["next", "--person", "Ana Gómez"], jira)
        self.assertEqual(code, 0)
        self.assertIn('assignee = "acc-ana"', jira.jqls[0])
        self.assertIn("**Quién:** Ana Gómez", out)

    def test_an_ambiguous_person_is_never_guessed(self):
        jira = FakeJira()
        code, _, err = run(["blocked", "--person", "Martin Fernandez"], jira)
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)
        self.assertEqual(jira.jqls, [])

    def test_next_blocked_and_json(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", flagged=True), issue("PLATE-2", priority="High")]
        code, out, _ = run(["blocked", "--json"], jira)
        self.assertEqual(code, 0)
        self.assertEqual([r["issue"]["key"] for r in json.loads(out)["rows"]], ["PLATE-1"])
        code, out, _ = run(["next"], jira)
        self.assertIn("| [PLATE-2](https://example.atlassian.net/browse/PLATE-2) |", flat(out))

    def test_load_with_a_person_compares_with_me(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-1", category="in_progress")]
        code, out, _ = run(["load", "--person", "Ana Gómez", "--weeks", "2"], jira)
        self.assertEqual(code, 0)
        self.assertIn("| Métrica | Ana Gómez | vos |", flat(out))
        self.assertEqual(len(jira.jqls), 4)  # closed + open for her, closed + open for me
        self.assertTrue(any("currentUser()" in j for j in jira.jqls) and any("acc-ana" in j for j in jira.jqls))

    def test_stats_runs_on_an_empty_account(self):
        code, out, _ = run(["stats"], FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("Sin cierres en el período", out)

    def test_stats_by_label_adds_one_table_and_says_how_a_multi_label_issue_counts(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: ([issue("PLATE-1", category="todo", labels=["ai"])] if "!= Done" in jql
                                          else [issue("PLATE-2", category="done", status="Done", changed="2026-10-07", labels=["ai", "be"])])
        code, out, _ = run(["stats", "--by", "label"], jira)
        self.assertEqual(code, 0)
        self.assertIn("### Por etiqueta", out)
        self.assertRegex(out, r"\| ai\s+\| 1\s+\| 1\s+\|")
        self.assertRegex(out, r"\| be\s+\| 1\s+\| 0\s+\|")
        self.assertIn("cuenta en cada una", out)

    def test_done_json_does_not_carry_the_label_and_component_fields_only_stats_asks_for(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("PLATE-5", category="done", status="Done", changed="2026-10-07", labels=["x"], components=["C"])]
        out = run(["done", "--since", "2026-10-01", "--until", "2026-10-07", "--json"], jira)[1]
        self.assertNotIn('"labels"', out)
        self.assertNotIn('"components"', out)

    def test_stats_by_component_has_its_own_heading(self):
        code, out, _ = run(["stats", "--by", "component"], FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("### Por componente", out)

    def test_stats_without_by_prints_no_grouping_and_json_carries_it_only_when_asked(self):
        _, out, _ = run(["stats"], FakeJira())
        self.assertNotIn("Por etiqueta", out)
        self.assertNotIn("tags", json.loads(run(["stats", "--json"], FakeJira())[1]))
        self.assertEqual(json.loads(run(["stats", "--by", "label", "--json"], FakeJira())[1])["tags"], {"by": "label", "rows": []})

    def test_by_is_only_for_stats_and_only_label_or_component(self):
        for args in (["stats", "--by", "priority"], ["load", "--by", "label"], ["done", "--by", "label"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit, msg=args):
                run(args, FakeJira())


if __name__ == "__main__":
    unittest.main()
