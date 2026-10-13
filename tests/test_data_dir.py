"""The data folder is ./.jira-team-kit/; a project that still has ./.jira-kanban/ keeps everything in it.

The old name predates the jk -> jtk rename. A folder left under the old name is moved to the new one the first time any
command looks for the data, with its epics, baselines and write log untouched.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_project
from jkan import config, home, journal, kanban, sync


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DataDirTest(unittest.TestCase):
    def setUp(self):
        self.project = make_project()
        self.new = self.project / ".jira-team-kit"
        self.old = self.project / ".jira-kanban"

    def test_a_project_with_no_data_uses_the_new_name_and_creates_nothing(self):
        self.assertEqual(home.data_dir(self.project), self.new)
        self.assertFalse(self.new.exists())
        self.assertFalse(self.old.exists())

    def test_an_old_folder_is_moved_whole_to_the_new_name(self):
        write(self.old / "PLATE-600" / "epic.md", "# Epic\n")
        write(self.old / "PLATE-600" / ".sync.json", '{"at": "T0"}')
        write(self.old / "jira-writes.jsonl", '{"ts": "T1"}\n')
        write(self.old / "conventions.json", '{"project": "IRIS"}')
        self.assertEqual(home.data_dir(self.project), self.new)
        self.assertFalse(self.old.exists())
        self.assertEqual((self.new / "PLATE-600" / "epic.md").read_text(encoding="utf-8"), "# Epic\n")
        self.assertEqual((self.new / "PLATE-600" / ".sync.json").read_text(encoding="utf-8"), '{"at": "T0"}')
        self.assertEqual((self.new / "jira-writes.jsonl").read_text(encoding="utf-8"), '{"ts": "T1"}\n')
        self.assertEqual((self.new / "conventions.json").read_text(encoding="utf-8"), '{"project": "IRIS"}')

    def test_when_both_exist_the_new_one_wins_and_the_old_one_is_left_alone(self):
        write(self.new / "conventions.json", '{"project": "NEW"}')
        write(self.old / "conventions.json", '{"project": "OLD"}')
        self.assertEqual(home.data_dir(self.project), self.new)
        self.assertEqual((self.old / "conventions.json").read_text(encoding="utf-8"), '{"project": "OLD"}')
        self.assertEqual(config.load_conventions(self.project)["project"], "NEW")

    def test_an_old_name_that_is_a_file_is_not_a_folder_to_migrate(self):
        write(self.old, "not a directory")
        self.assertEqual(home.data_dir(self.project), self.new)
        self.assertTrue(self.old.is_file())

    def test_if_the_move_fails_the_old_folder_keeps_working(self):
        write(self.old / "conventions.json", '{"project": "IRIS"}')
        with mock.patch.object(Path, "rename", side_effect=OSError("read-only")):
            self.assertEqual(home.data_dir(self.project), self.old)
            self.assertEqual(config.load_conventions(self.project)["project"], "IRIS")
        self.assertTrue((self.old / "conventions.json").is_file())

    def test_the_project_override_is_read_from_an_old_folder(self):
        write(self.old / "conventions.json", '{"project": "IRIS"}')
        self.assertEqual(config.load_conventions(self.project)["project"], "IRIS")
        self.assertTrue((self.new / "conventions.json").is_file())

    def test_epics_are_found_where_they_were_after_the_move(self):
        write(self.old / "PLATE-600" / "epic.md", "# Epic\n")
        self.assertEqual(kanban.epic_dir(self.project, "PLATE-600"), self.new / "PLATE-600")
        self.assertTrue((self.new / "PLATE-600" / "epic.md").is_file())

    def test_the_write_log_goes_on_in_the_migrated_file(self):
        write(self.old / "jira-writes.jsonl", '{"ts": "T0", "command": "create"}\n')
        journal.journal(self.project, "push", now=lambda: "T1")({"action": "update", "issue": "PLATE-600"})
        lines = (self.new / "jira-writes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["ts"] for line in lines], ["T0", "T1"])
        self.assertFalse(self.old.exists())

    def test_a_create_in_flight_under_the_old_name_is_found_under_the_new_one(self):
        write(self.old / ".create-progress-abc.json", "{}")
        path = sync._progress_path(self.project, {"summary": "x"}, {"project": "PLATE"})
        self.assertEqual(path.parent, self.new)
        self.assertTrue((self.new / ".create-progress-abc.json").is_file())


if __name__ == "__main__":
    unittest.main()
