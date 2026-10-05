from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import FakeJira, epic_with_children, make_project
from jkan import kanban, sync


class QuietPullTest(unittest.TestCase):
    def test_a_pull_with_nothing_new_leaves_every_md_untouched(self):
        jira, project = FakeJira(), make_project()
        epic = epic_with_children(jira)
        sync.pull(jira, project, epic)
        root = kanban.epic_dir(project, epic)
        before = {p: p.read_bytes() for p in root.rglob("*.md")}
        with mock.patch.object(sync, "_now", lambda: "2099-01-01T00:00:00Z"):  # a later clock stays out of the .md
            sync.pull(jira, project, epic)
        self.assertEqual({p: p.read_bytes() for p in root.rglob("*.md")}, before)
        baseline = json.loads((root / ".sync.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["synced"], "2099-01-01T00:00:00Z")
        self.assertEqual(sorted(baseline["issues"]), ["PLATE-600", "PLATE-601", "PLATE-602", "PLATE-603"])

    def test_push_still_reads_a_flat_baseline_from_before(self):
        jira, project = FakeJira(), make_project()
        epic = epic_with_children(jira)
        sync.pull(jira, project, epic)
        root = kanban.epic_dir(project, epic)
        nested = json.loads((root / ".sync.json").read_text(encoding="utf-8"))
        (root / ".sync.json").write_text(json.dumps(nested["issues"]), encoding="utf-8")
        story = root / "stories/PLATE-601/story.md"
        story.write_text(story.read_text(encoding="utf-8").replace("status: Backlog", "status: PROCESANDO"),
                         encoding="utf-8")
        result = sync.push(jira, project, epic, apply=False)
        self.assertEqual([(c["key"], c["to"]) for c in result["changes"]], [("PLATE-601", "PROCESANDO")])


if __name__ == "__main__":
    unittest.main()
