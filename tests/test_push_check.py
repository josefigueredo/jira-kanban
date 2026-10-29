"""A description edited in the local kanban goes back to Jira only if it still follows templates/description.md.

Only what changed is checked: a card mirrored from Jira with free text can still move or be renamed.
"""
from __future__ import annotations

import unittest

from helpers import FakeJira, epic_with_children, make_project
from jkan import description, sync
from test_cli import run

GOOD = description.render({"why": "Nada corre los tests.", "what": "CI con gate.", "done_when": "Un PR rojo no entra."})


class PushCheckTest(unittest.TestCase):
    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        sync.pull(self.jira, self.project, self.key)
        self.epic = self.project / ".jira-team-kit" / self.key
        self.task = self.epic / "tasks/PLATE-603/task.md"

    def set_description(self, path, text):
        head = path.read_text(encoding="utf-8").split("\n# ", 1)
        title = head[1].split("\n", 1)[0]
        path.write_text(f"{head[0]}\n# {title}\n\n{text}\n", encoding="utf-8")

    def test_an_edited_description_that_breaks_the_template_is_not_sent(self):
        self.set_description(self.task, "Por qué: x\n\nQué: y")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("invalid PLATE-603 description: missing: Hecho cuando (see templates/description.md)", out)
        self.assertEqual(self.jira.issues["PLATE-603"]["description"], "CI")

    def test_an_edited_description_that_follows_it_is_sent(self):
        self.set_description(self.task, GOOD)
        code, _, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(self.jira.issues["PLATE-603"]["description"], GOOD)

    def test_a_free_text_card_can_still_change_status_and_title(self):
        text = self.task.read_text(encoding="utf-8")
        self.task.write_text(text.replace("status: Backlog", "status: Done").replace("# [DEVOPS] Pipeline", "# [DEVOPS] CI"),
                             encoding="utf-8")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply"], self.jira)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.jira.issues["PLATE-603"]["summary"], "[DEVOPS] CI")

    def test_a_new_subtask_with_a_placeholder_left_is_not_created(self):
        new = self.epic / "tasks/PLATE-603/subtasks/_new-gate/subtask.md"
        new.parent.mkdir(parents=True)
        new.write_text("# Gate de cobertura\n\nPor qué: {{why}}\n\nQué: un gate.\n\nHecho cuando: falla bajo 80%.\n",
                       encoding="utf-8")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply", "--assign-open"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("invalid _new-gate description: not filled in: Por qué (see templates/description.md)", out)
        self.assertFalse(any(w[0] == "create" and w[2]["summary"] == "Gate de cobertura" for w in self.jira.writes))
        self.assertTrue(new.is_file())

    def test_a_new_subtask_that_follows_the_template_is_created(self):
        new = self.epic / "tasks/PLATE-603/subtasks/_new-gate/subtask.md"
        new.parent.mkdir(parents=True)
        new.write_text(f"# Gate de cobertura\n\n{GOOD}\n", encoding="utf-8")
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply", "--assign-open"], self.jira)
        self.assertEqual(code, 0, out)
        self.assertTrue(any(w[0] == "create" and w[2]["description"] == GOOD for w in self.jira.writes))


    def new_task_with_subtasks(self, task_text=None):
        task = self.epic / "tasks/_new-after/task.md"
        task.parent.mkdir(parents=True)
        task.write_text(task_text or f"# [DBA] Después del corte\n\n{GOOD}\n", encoding="utf-8")
        subs = []
        for slug, title in (("_new-t1", "[DBA] 55. T+1"), ("_new-t7", "[DBA] 56. T+7")):
            sub = task.parent / "subtasks" / slug / "subtask.md"
            sub.parent.mkdir(parents=True)
            sub.write_text(f"# {title}\n\n{GOOD}\n", encoding="utf-8")
            subs.append(sub)
        return task, subs

    def test_a_new_task_and_its_new_subtasks_go_up_in_one_push_under_the_new_key(self):
        task, subs = self.new_task_with_subtasks()
        dry = sync.push(self.jira, self.project, self.key, apply=False, assign_open=False)
        self.assertEqual(dry["conflicts"], [])
        self.assertEqual([n["summary"] for n in dry["new"]], ["[DBA] Después del corte", "[DBA] 55. T+1", "[DBA] 56. T+7"])
        code, out, _ = run(["push", self.key, "--project", str(self.project), "--apply", "--no-assign-open"], self.jira)
        self.assertEqual(code, 0, out)
        created = {w[2]["summary"]: w[1] for w in self.jira.writes if w[0] == "create"}
        task_key = created["[DBA] Después del corte"]
        self.assertEqual(self.jira.issues[task_key]["parent"], self.key)
        for title in ("[DBA] 55. T+1", "[DBA] 56. T+7"):
            self.assertEqual(self.jira.issues[created[title]]["parent"], task_key)
        self.assertFalse(task.parent.exists())
        self.assertTrue((self.epic / "tasks" / task_key / "subtasks" / created["[DBA] 55. T+1"] / "subtask.md").is_file())

    def test_subtasks_of_a_new_task_that_is_not_valid_wait_for_it(self):
        task, subs = self.new_task_with_subtasks(task_text="# [DBA] Después del corte\n\nPor qué: {{why}}\n")
        result = sync.push(self.jira, self.project, self.key, apply=False, assign_open=False)
        self.assertEqual({i["key"] for i in result["invalid"]}, {"_new-after"})
        self.assertEqual(sorted(c["key"] for c in result["conflicts"]), ["_new-t1", "_new-t7"])
        self.assertEqual(result["new"], [])
        self.assertTrue(all(s.is_file() for s in subs))


    def test_a_retry_after_a_failed_subtask_creates_the_rest_under_the_task_already_created(self):
        self.new_task_with_subtasks()
        self.jira.fail_on_create = 2  # the task goes up, the first subtask is rejected
        with self.assertRaises(Exception):
            sync.push(self.jira, self.project, self.key, apply=True, assign_open=False)
        self.jira.fail_on_create = None
        result = sync.push(self.jira, self.project, self.key, apply=True, assign_open=False)
        self.assertEqual(result["conflicts"], [])
        tasks = [k for k, i in self.jira.issues.items() if i["summary"] == "[DBA] Después del corte"]
        self.assertEqual(len(tasks), 1)
        subs = [i for i in self.jira.issues.values() if i["summary"] in ("[DBA] 55. T+1", "[DBA] 56. T+7")]
        self.assertEqual(sorted(i["parent"] for i in subs), [tasks[0], tasks[0]])
        self.assertFalse((self.epic / "tasks/_new-after").exists())


if __name__ == "__main__":
    unittest.main()
