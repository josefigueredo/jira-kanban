from __future__ import annotations

import contextlib
import io
import json
import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import cli
from test_spec import GOOD


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args, client=lambda project: jira)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_create_previews_by_default_and_applies_on_request(self):
        jira, project = FakeJira(), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps(GOOD), encoding="utf-8")
        code, out, _ = run(["create", "--spec", str(path), "--project", str(project)], jira)
        self.assertEqual(code, 0)
        self.assertIn("[FE] Ver el tablero", out)
        self.assertIn("dry run", out)
        self.assertEqual(jira.writes, [])
        code, _, err = run(["create", "--spec", str(path), "--project", str(project), "--apply"], jira)
        self.assertEqual(code, 1)
        self.assertIn("--assign-open", err)
        self.assertEqual(jira.writes, [])
        code, out, _ = run(["create", "--spec", str(path), "--project", str(project), "--apply", "--assign-open"], jira)
        self.assertEqual(code, 0)
        self.assertIn("PLATE-600", out)
        self.assertTrue((project / ".jira-kanban/PLATE-600/epic.md").is_file())

    def test_invalid_spec_exits_1_with_findings(self):
        jira, project = FakeJira(), make_project()
        path = project / "spec.json"
        path.write_text(json.dumps({"epic": {}, "items": []}), encoding="utf-8")
        code, _, err = run(["create", "--spec", str(path), "--project", str(project)], jira)
        self.assertEqual(code, 1)
        self.assertIn("epic: summary is required", err)

    def test_pull_show_and_push_round_trip(self):
        jira, project = FakeJira(), make_project()
        key = epic_with_children(jira)
        self.assertEqual(run(["pull", key, "--project", str(project)], jira)[0], 0)
        code, out, _ = run(["show", key, "--project", str(project)], jira)
        self.assertIn("PLATE-602", out)
        task = project / ".jira-kanban" / key / "tasks/PLATE-603/task.md"
        task.write_text(task.read_text(encoding="utf-8").replace("status: Backlog", "status: Done"), encoding="utf-8")
        code, out, _ = run(["push", key, "--project", str(project)], jira)
        self.assertIn("PLATE-603 status: Backlog -> Done", out)
        self.assertEqual(jira.writes, [])
        self.assertEqual(run(["push", key, "--project", str(project), "--apply"], jira)[0], 0)
        self.assertEqual(jira.issues["PLATE-603"]["status"], "Done")


if __name__ == "__main__":
    unittest.main()
