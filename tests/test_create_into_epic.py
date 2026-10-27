"""`jtk create --epic KEY`: the spec's items go under an epic that already exists. The epic is read, never written: it
is not created, moved or reassigned, and every view names it by its real key while new issues stay NUEVO-n."""
from __future__ import annotations

import json
import re
import unittest

from helpers import CONVENTIONS, FakeJira, make_project
from jkan import sync
from test_cli import run as run_cli
from test_legacy_guard import Asked, run as run_guarded


def described_items(items):
    for item in items:
        item.setdefault("why", f"Hace falta «{item['summary']}».")
        item.setdefault("what", "Lo que dice el título.")
        item.setdefault("done_when", "Se ve hecho.")
    return {"items": items}


SPEC = described_items([
    {"type": "task", "summary": "Hecha", "done": True, "evidence": ["https://example.com/pr/5"]},
    {"type": "task", "summary": "Pendiente"}])


def jira_with_epic(key="PLATE-1044", issuetype="Epic", status="Done"):
    jira = FakeJira(start=2000)
    jira.issues[key] = {"key": key, "summary": "Relevamientos reproducibles", "description": "", "issuetype": issuetype,
                        "status": status, "parent": None, "priority": None, "labels": [], "assignee": "acc-me",
                        "category": "done", "flagged": False}
    return jira


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.project = make_project()

    def create(self, jira, spec=SPEC, epic="PLATE-1044", apply=True):
        return sync.create(jira, self.project, json.loads(json.dumps(spec)), dict(CONVENTIONS), apply=apply,
                           assign_open=False, epic_key=epic)

    def test_items_are_created_under_the_existing_epic_and_the_epic_is_not_written(self):
        jira = jira_with_epic()
        result = self.create(jira)
        created = [w for w in jira.writes if w[0] == "create"]
        self.assertEqual([w[2]["parent"]["key"] for w in created], ["PLATE-1044", "PLATE-1044"])
        self.assertEqual([w[2]["issuetype"]["name"] for w in created], ["Tarea", "Tarea"])
        self.assertFalse([w for w in jira.writes if w[1] == "PLATE-1044"])  # no move, no assign, no update
        self.assertEqual(result["epic"], "PLATE-1044")
        self.assertEqual(jira.issues[result["keys"]["items[0]"]]["status"], "Done")

    def test_the_local_kanban_mirrors_the_epic_with_its_new_items(self):
        result = self.create(jira_with_epic())
        tasks = self.project / ".jira-team-kit" / "PLATE-1044" / "tasks"
        self.assertEqual(sorted(p.name for p in tasks.iterdir()), sorted(result["keys"][r] for r in ("items[0]", "items[1]")))

    def test_the_dry_run_reads_the_epic_and_writes_nothing(self):
        jira = jira_with_epic()
        ops = self.create(jira, apply=False)["ops"]
        self.assertEqual(jira.writes, [])
        self.assertEqual((ops[0]["existing"], ops[0]["summary"], ops[0]["current_status"]),
                         ("PLATE-1044", "Relevamientos reproducibles", "Done"))

    def test_an_epic_that_does_not_exist_is_refused_before_any_write(self):
        jira = FakeJira()
        with self.assertRaisesRegex(ValueError, "PLATE-1044"):
            self.create(jira, apply=False)
        self.assertEqual(jira.writes, [])

    def test_an_issue_that_is_not_an_epic_is_refused(self):
        with self.assertRaisesRegex(ValueError, "is a Tarea, not an Epic"):
            self.create(jira_with_epic(issuetype="Tarea"), apply=False)

    def test_an_epic_of_another_project_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not in PLATE"):
            self.create(jira_with_epic(key="OTHER-7"), epic="OTHER-7", apply=False)

    def test_a_spec_with_its_own_epic_and_an_existing_epic_is_refused(self):
        spec = {**SPEC, "epic": {"summary": "Otra", "why": "x", "what": "y", "done_when": "z"}}
        with self.assertRaisesRegex(ValueError, "--epic"):
            self.create(jira_with_epic(), spec=spec, apply=False)

    def test_the_same_command_resumes_without_duplicating(self):
        jira = jira_with_epic()
        jira.fail_on_create = 2
        with self.assertRaises(sync.PartialCreate):
            self.create(jira)
        jira.fail_on_create = None
        self.create(jira)
        self.assertEqual(sum(1 for w in jira.writes if w[0] == "create"), 2)


class ViewsTest(unittest.TestCase):
    """Console, --html and the approval window name the epic by its key and number only what they create."""

    def setUp(self):
        self.project = make_project()
        path = self.project / "spec.json"
        path.write_text(json.dumps(SPEC), encoding="utf-8")
        self.base = ["create", "--spec", str(path), "--project", str(self.project), "--epic", "PLATE-1044"]

    def test_console_shows_the_existing_epic_then_the_new_issues(self):
        code, out, err = run_cli(self.base, jira_with_epic())
        self.assertEqual(code, 0, err)
        rows = [re.split(r"\s{2,}", ln.strip()) for ln in out.splitlines() if re.match(r"^\s*(PLATE-1044|NUEVO-\d+)\s", ln)]
        self.assertEqual([r[0] for r in rows], ["PLATE-1044", "NUEVO-1", "NUEVO-2"])
        self.assertEqual(rows[0][2:4], ["Done", "Sin cambios"])
        self.assertIn("--apply creates 2 issues in PLATE under PLATE-1044", out)

    def test_the_project_comes_from_the_epic_key(self):
        code, out, err = run_cli(self.base, jira_with_epic())  # no --jira-project
        self.assertEqual(code, 0, err)

    def test_html_numbers_only_new_issues_and_links_the_epic_by_key(self):
        html = self.project / "v.html"
        run_cli(self.base + ["--html", str(html)], jira_with_epic())
        page = html.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'<section class="issue[^"]*" id="([^"]+)">', page), ["PLATE-1044", "NUEVO-1", "NUEVO-2"])
        self.assertIn("crea estos 2 issues", page)
        self.assertIn("Ya existe en Jira", page)

    def test_the_window_lists_only_what_is_created_and_names_the_epic(self):
        asked = Asked()
        run_guarded(self.base + ["--apply", "--no-assign-open"], jira_with_epic(), asked)
        n, summary, _ = asked.calls[0]
        self.assertEqual(n, 2)
        self.assertEqual([r[1] for r in summary.rows], ["Hecha", "Pendiente"])
        self.assertIn("create 2 issue(s) in PLATE under PLATE-1044", summary)

    def test_after_apply_it_says_where_the_issues_went(self):
        code, out, err = run_guarded(self.base + ["--apply", "--no-assign-open"], jira_with_epic(), Asked(approve=True))
        self.assertEqual(code, 0, err)
        self.assertIn("added 2 issue(s) to PLATE-1044; local kanban in .jira-team-kit/PLATE-1044/", out)


if __name__ == "__main__":
    unittest.main()
