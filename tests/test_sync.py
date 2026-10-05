from __future__ import annotations

import json
import unittest

from helpers import CONVENTIONS, FailingJira, FakeJira, epic_with_children, make_project
from jkan import kanban, sync
from test_spec import GOOD


class CreateTest(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        jira, project = FakeJira(), make_project()
        result = sync.create(jira, project, GOOD, CONVENTIONS, apply=False)
        self.assertEqual(jira.writes, [])
        self.assertEqual(len(result["ops"]), 4)
        self.assertFalse((project / ".jira-kanban").exists())

    def test_apply_creates_parents_first_assigns_me_and_writes_the_kanban(self):
        jira, project = FakeJira(), make_project()
        result = sync.create(jira, project, GOOD, CONVENTIONS, apply=True, assign_open=True)
        self.assertEqual(result["epic"], "PLATE-600")
        created = [(w[1], w[2]["issuetype"]["name"], (w[2].get("parent") or {}).get("key")) for w in jira.writes]
        self.assertEqual(created, [("PLATE-600", "Epic", None), ("PLATE-601", "Story (migrated)", "PLATE-600"),
                                   ("PLATE-602", "Subtarea", "PLATE-601"), ("PLATE-603", "Tarea", "PLATE-600")])
        self.assertTrue(all(w[2]["assignee"] == {"accountId": "acc-me"} for w in jira.writes))
        self.assertTrue(all(w[2]["project"] == {"key": "PLATE"} for w in jira.writes))
        epic = kanban.epic_dir(project, "PLATE-600")
        self.assertTrue((epic / "epic.md").is_file())
        self.assertTrue((epic / "stories/PLATE-601/subtasks/PLATE-602/subtask.md").is_file())
        self.assertTrue((epic / "tasks/PLATE-603/task.md").is_file())

    def test_open_items_need_a_decision_before_any_write(self):
        jira = FakeJira()
        with self.assertRaises(sync.NeedsDecision) as caught:
            sync.create(jira, make_project(), GOOD, CONVENTIONS, apply=True)
        self.assertEqual(jira.writes, [])
        self.assertIn("4", str(caught.exception))  # epic, story, its subtask and the task are all open

    def test_done_items_are_assigned_to_me_and_open_ones_follow_the_decision(self):
        done = {"epic": {"summary": "e"}, "items": [
            {"type": "task", "summary": "Hecha", "done": True, "evidence": ["https://example.com/pr/1"], "subtasks": [{"summary": "hereda"}]},
            {"type": "task", "summary": "Abierta", "subtasks": [{"summary": "abierta", "done": False}]}]}
        jira = FakeJira()
        sync.create(jira, make_project(), done, CONVENTIONS, apply=True, assign_open=False)
        assigned = {w[2]["summary"]: w[2].get("assignee") for w in jira.writes if w[0] == "create"}
        self.assertEqual(assigned, {"e": None, "Hecha": {"accountId": "acc-me"}, "hereda": {"accountId": "acc-me"},
                                    "Abierta": None, "abierta": None})

    def test_all_done_assigns_everything_without_asking(self):
        done = {"epic": {"summary": "e"}, "items": [{"type": "task", "summary": "t", "done": True, "evidence": ["https://example.com/pr/1"]}]}
        jira = FakeJira()
        sync.create(jira, make_project(), done, CONVENTIONS, apply=True)
        self.assertTrue(all(w[2]["assignee"] == {"accountId": "acc-me"} for w in jira.writes if w[0] == "create"))

    def test_dry_run_marks_what_still_needs_a_decision(self):
        result = sync.create(FakeJira(), make_project(), GOOD, CONVENTIONS, apply=False)
        self.assertEqual({op["assignee"] for op in result["ops"]}, {"ask"})

    def test_a_failure_halfway_keeps_what_was_created_and_a_rerun_resumes_without_duplicates(self):
        project = make_project()
        broken = FakeJira(fail_on_create=3)  # epic and story go through, the story's subtask is rejected
        with self.assertRaises(sync.PartialCreate) as caught:
            sync.create(broken, project, GOOD, CONVENTIONS, apply=True, assign_open=True)
        self.assertIn("PLATE-600", str(caught.exception))
        self.assertIn("PLATE-601", str(caught.exception))
        self.assertTrue((kanban.epic_dir(project, "PLATE-600") / "epic.md").is_file())
        # Rerun against the same Jira: only the two missing issues are created.
        broken.fail_on_create = None
        result = sync.create(broken, project, GOOD, CONVENTIONS, apply=True, assign_open=True)
        summaries = [w[2]["summary"] for w in broken.writes if w[0] == "create"]
        self.assertEqual(len(summaries), len(set(summaries)))
        self.assertEqual(result["epic"], "PLATE-600")
        self.assertEqual(len([w for w in broken.writes if w[0] == "create"]), 4)
        self.assertEqual(list((project / ".jira-kanban").glob(".create-progress-*.json")), [])

    def test_done_items_are_moved_to_done_children_before_parents(self):
        done = {"epic": {"summary": "e"}, "items": [
            {"type": "story", "summary": "Hecha", "user_story": "Como dev quiero x para y", "done": True, "evidence": ["https://example.com/pr/1"],
             "acceptance": ["AC1: Dado a Cuando b Entonces c"], "subtasks": [{"summary": "hereda"}]},
            {"type": "task", "summary": "Abierta"}]}
        jira = FakeJira()
        result = sync.create(jira, make_project(), done, CONVENTIONS, apply=True, assign_open=False)
        moved = [w[1] for w in jira.writes if w[0] == "transition"]
        story, subtask = result["keys"]["items[0]"], result["keys"]["items[0].subtasks[0]"]
        self.assertEqual(moved, [subtask, story])
        self.assertEqual(jira.issues[story]["status"], "Done")

    def test_create_needs_a_jira_project_and_never_assumes_one(self):
        conv = {k: v for k, v in CONVENTIONS.items() if k != "project"}
        jira = FakeJira()
        with self.assertRaises(ValueError) as caught:
            sync.create(jira, make_project(), GOOD, conv, apply=False)
        self.assertIn("--jira-project", str(caught.exception))
        self.assertEqual(jira.writes, [])

    def test_invalid_spec_is_refused_before_any_write(self):
        jira = FakeJira()
        with self.assertRaises(ValueError):
            sync.create(jira, make_project(), {"epic": {}, "items": []}, CONVENTIONS, apply=True)
        self.assertEqual(jira.writes, [])


class PullTest(unittest.TestCase):
    def test_pull_mirrors_jira_and_records_a_baseline(self):
        jira, project = FakeJira(), make_project()
        key = epic_with_children(jira)
        sync.pull(jira, project, key)
        epic = kanban.epic_dir(project, key)
        story = kanban.parse((epic / "stories/PLATE-601/story.md").read_text(encoding="utf-8"))
        self.assertEqual((story["summary"], story["status"], story["parent"]), ("[FE] Ver el tablero", "Backlog", key))
        self.assertTrue((epic / "stories/PLATE-601/subtasks/PLATE-602/subtask.md").is_file())
        self.assertTrue((epic / "tasks/PLATE-603/task.md").is_file())
        baseline = json.loads((epic / ".sync.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(baseline["issues"]), ["PLATE-600", "PLATE-601", "PLATE-602", "PLATE-603"])

    def test_pull_removes_folders_of_issues_no_longer_under_the_epic(self):
        jira, project = FakeJira(), make_project()
        key = epic_with_children(jira)
        sync.pull(jira, project, key)
        jira.issues["PLATE-603"]["parent"] = "PLATE-999"
        sync.pull(jira, project, key)
        self.assertFalse((kanban.epic_dir(project, key) / "tasks/PLATE-603").exists())


class PushTest(unittest.TestCase):
    def test_push_takes_the_project_from_the_epic_key_when_none_is_configured(self):
        conv = {k: v for k, v in CONVENTIONS.items() if k != "project"}
        jira, project = FakeJira(project="ACME"), make_project()
        key = epic_with_children(jira)
        sync.pull(jira, project, key, conv)
        new = kanban.epic_dir(project, key) / "tasks" / "_new-docs" / "task.md"
        new.parent.mkdir(parents=True)
        new.write_text("# [FE] Docs\n", encoding="utf-8")
        sync.push(jira, project, key, apply=True, conv=conv, assign_open=False)
        [created] = [w for w in jira.writes if w[0] == "create"]
        self.assertEqual(created[2]["project"], {"key": "ACME"})

    def setUp(self):
        self.jira, self.project = FakeJira(), make_project()
        self.key = epic_with_children(self.jira)
        sync.pull(self.jira, self.project, self.key)
        self.epic = kanban.epic_dir(self.project, self.key)

    def edit(self, rel, old, new):
        path = self.epic / rel
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_local_status_and_title_changes_go_to_jira(self):
        self.edit("tasks/PLATE-603/task.md", "status: Backlog", "status: Done")
        self.edit("stories/PLATE-601/story.md", "# [FE] Ver el tablero", "# [FE] Ver el tablero kanban")
        plan = sync.push(self.jira, self.project, self.key, apply=False)
        self.assertEqual(self.jira.writes, [])
        self.assertEqual(sorted((c["key"], c["field"]) for c in plan["changes"]),
                         [("PLATE-601", "summary"), ("PLATE-603", "status")])
        sync.push(self.jira, self.project, self.key, apply=True)
        self.assertEqual(self.jira.issues["PLATE-603"]["status"], "Done")
        self.assertEqual(self.jira.issues["PLATE-601"]["summary"], "[FE] Ver el tablero kanban")

    def test_a_field_changed_on_both_sides_is_a_conflict_and_is_not_written(self):
        self.edit("tasks/PLATE-603/task.md", "# [DEVOPS] Pipeline", "# [DEVOPS] Pipeline local")
        self.jira.issues["PLATE-603"]["summary"] = "[DEVOPS] Pipeline remoto"
        plan = sync.push(self.jira, self.project, self.key, apply=True)
        self.assertEqual([(c["key"], c["field"]) for c in plan["conflicts"]], [("PLATE-603", "summary")])
        self.assertEqual(self.jira.issues["PLATE-603"]["summary"], "[DEVOPS] Pipeline remoto")

    def test_new_local_item_is_created_under_its_folder_parent(self):
        new = self.epic / "stories/PLATE-601/subtasks/_new-tests/subtask.md"
        new.parent.mkdir(parents=True)
        new.write_text("---\nkind: subtask\n---\n# Escribir los tests\n\nCubrir el tablero\n", encoding="utf-8")
        plan = sync.push(self.jira, self.project, self.key, apply=False)
        self.assertEqual([(n["kind"], n["parent"], n["summary"]) for n in plan["new"]],
                         [("subtask", "PLATE-601", "Escribir los tests")])
        with self.assertRaises(sync.NeedsDecision):
            sync.push(self.jira, self.project, self.key, apply=True)
        sync.push(self.jira, self.project, self.key, apply=True, assign_open=False)
        self.assertEqual(self.jira.issues["PLATE-604"]["parent"], "PLATE-601")
        self.assertIsNone(self.jira.issues["PLATE-604"]["assignee"])
        self.assertFalse(new.exists())
        self.assertTrue((self.epic / "stories/PLATE-601/subtasks/PLATE-604/subtask.md").is_file())


if __name__ == "__main__":
    unittest.main()
