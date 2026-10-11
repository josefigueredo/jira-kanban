"""`jtk create --check`: the three things the skill used to ask the agent to look up by hand before drafting a spec
(a WayOfWork plan, the Jira project, an epic that already covers the work), measured in one offline call."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import unittest

from helpers import FakeJira, make_project
from jkan import check, cli
from test_cli import assert_aligned, run


def write(project, name, text):
    path = project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rows(result):
    return {name: (verdict, detail) for name, verdict, detail in result}


class PreflightTest(unittest.TestCase):
    def test_a_project_without_a_wow_plan_says_so(self):
        verdict, _ = rows(check.preflight(make_project(), {}, branch=""))["wow plan"]
        self.assertEqual(verdict, "no")

    def test_a_wow_plan_means_product_brain_creates_the_epics(self):
        project = make_project()
        write(project, "wow/plan/manifest.json", "{}")
        verdict, detail = rows(check.preflight(project, {}, branch=""))["wow plan"]
        self.assertEqual(verdict, "yes")
        self.assertIn("Product Brain", detail)

    def test_the_jira_project_comes_from_the_flag_or_the_project_conventions(self):
        project = make_project()
        self.assertEqual(rows(check.preflight(project, {"project": "PLATE"}, branch="", flag="PLATE"))["jira project"],
                         ("PLATE", "--jira-project"))
        write(project, ".jira-kanban/conventions.json", '{"project": "IRIS"}')
        self.assertEqual(rows(check.preflight(project, {"project": "IRIS"}, branch=""))["jira project"],
                         ("IRIS", ".jira-kanban/conventions.json"))

    def test_without_a_jira_project_it_says_to_ask_the_person(self):
        verdict, detail = rows(check.preflight(make_project(), {}, branch=""))["jira project"]
        self.assertEqual(verdict, "none")
        self.assertIn("--jira-project KEY", detail)

    def test_an_epic_declared_in_a_spec_is_found_in_either_form_the_sync_writes(self):
        project = make_project()
        write(project, "specs/001-curation/spec.md", "# Spec\n**Jira Epic:** [IRIS-40](https://x/browse/IRIS-40)\n")
        write(project, "specs/002-board/spec.md", "**Jira Epic:** PLATE-491\n")
        write(project, "specs/003-none/spec.md", "# nothing here\n")
        result = check.preflight(project, {}, branch="")
        verdict, detail = rows(result)["existing epic"]
        self.assertEqual(verdict, "IRIS-40, PLATE-491")
        self.assertIn("specs/001-curation/spec.md", detail)
        self.assertIn("specs/002-board/spec.md", detail)

    def test_the_same_epic_in_two_places_is_listed_once(self):
        project = make_project()
        write(project, "specs/001-a/spec.md", "**Jira Epic:** PLATE-491\n")
        write(project, "specs/002-b/spec.md", "**Jira Epic:** PLATE-491\n")
        verdict, _ = rows(check.preflight(project, {}, branch="feat/plate-491-x"))["existing epic"]
        self.assertEqual(verdict, "PLATE-491")

    def test_a_spec_that_names_its_epic_twice_is_listed_once(self):
        # Spec-Kit's sync writes the key in the header and again under «Source Documentation».
        project = make_project()
        write(project, "specs/001-checkout/spec.md",
              "**Jira Epic:** [ECOM-456](https://x/browse/ECOM-456)\n\n### Source Documentation\n- **Jira Epic:** ECOM-456\n")
        _, detail = rows(check.preflight(project, {}, branch=""))["existing epic"]
        self.assertEqual(detail.count("specs/001-checkout/spec.md"), 1)

    def test_a_key_in_the_branch_counts_whatever_its_case(self):
        verdict, detail = rows(check.preflight(make_project(), {}, branch="feat/plate-504-tablero"))["existing epic"]
        self.assertEqual(verdict, "PLATE-504")
        self.assertIn("branch feat/plate-504-tablero", detail)

    def test_no_epic_anywhere_says_none_and_that_the_conversation_is_still_unchecked(self):
        verdict, detail = rows(check.preflight(make_project(), {}, branch="main"))["existing epic"]
        self.assertEqual(verdict, "none")
        self.assertIn("conversation", detail)

    def test_the_branch_is_read_from_git_when_not_given(self):
        project = make_project()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/fix/PLATE-77-x"], cwd=project, check=True)
        self.assertEqual(rows(check.preflight(project, {}))["existing epic"][0], "PLATE-77")

    def test_outside_a_git_repo_there_is_simply_no_branch(self):
        self.assertEqual(rows(check.preflight(make_project(), {}))["existing epic"][0], "none")


class CheckCliTest(unittest.TestCase):
    def test_check_needs_no_spec_and_never_touches_jira(self):
        project = make_project()
        write(project, ".jira-kanban/conventions.json", '{"project": "PLATE"}')
        jira = FakeJira()
        code, out, err = run(["create", "--check", "--project", str(project)], jira)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(jira.writes, [])
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["Check", "Result", "Detail"])
        assert_aligned(self, lines)
        self.assertIn("PLATE", out)

    def test_check_works_without_jira_credentials(self):
        def no_credentials(project):
            raise AssertionError("--check must not build a Jira client")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["create", "--check", "--project", str(make_project())], client=no_credentials)
        self.assertEqual(code, 0)

    def test_the_jira_project_flag_is_reported(self):
        code, out, _ = run(["create", "--check", "--project", str(make_project()), "--jira-project", "IRIS"], FakeJira())
        self.assertIn("IRIS", out)
        self.assertIn("--jira-project", out)

    def test_create_still_needs_a_spec_unless_checking(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            run(["create", "--project", str(make_project())], FakeJira())
        self.assertEqual(raised.exception.code, 2)

    def test_check_and_spec_together_are_refused(self):
        project = make_project()
        write(project, "spec.json", json.dumps({}))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            run(["create", "--check", "--spec", str(project / "spec.json"), "--project", str(project)], FakeJira())
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
