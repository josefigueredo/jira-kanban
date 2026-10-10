from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from helpers import state_dir
from jkan import state

BODY = {"version": 1, "kind": "move", "view": "plataforma", "created": "2026-10-10T12:00:00Z",
        "options": {"to_role": "active"}, "items": [{"key": "TEAM-1"}], "skipped": []}


class PlanFileTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()

    def test_saving_adds_a_hash_and_a_12_hex_id_that_is_its_prefix(self):
        plan = state.save_plan(BODY)
        self.assertRegex(plan["id"], r"^[0-9a-f]{12}$")
        self.assertEqual(plan["hash"][:12], plan["id"])
        self.assertEqual(plan["hash"], state.digest(BODY))
        self.assertTrue((self.base / "plans" / f"{plan['id']}.json").is_file())

    def test_the_same_content_is_the_same_plan_and_other_content_is_another(self):
        self.assertEqual(state.save_plan(BODY)["id"], state.save_plan(dict(BODY))["id"])
        self.assertNotEqual(state.save_plan(BODY)["id"], state.save_plan(dict(BODY, view="otro"))["id"])

    def test_load_gives_back_what_was_saved(self):
        saved = state.save_plan(BODY)
        self.assertEqual(state.load_plan(saved["id"]), saved)

    def test_a_plan_edited_after_planning_is_refused(self):
        saved = state.save_plan(BODY)
        path = state.plan_path(saved["id"])
        edited = json.loads(path.read_text(encoding="utf-8"))
        edited["items"].append({"key": "TEAM-99"})
        path.write_text(json.dumps(edited), encoding="utf-8")
        with self.assertRaisesRegex(state.BadPlan, "changed after it was planned"):
            state.load_plan(saved["id"])

    def test_a_plan_renamed_to_another_id_is_refused(self):
        saved = state.save_plan(BODY)
        other = "0" * 12
        state.plan_path(saved["id"]).rename(self.base / "plans" / f"{other}.json")
        with self.assertRaisesRegex(state.BadPlan, "changed after it was planned"):
            state.load_plan(other)

    def test_an_id_that_could_walk_out_of_the_folder_is_refused(self):
        for bad in ("../x", "..", "abc", "ABCDEF123456", "abcdef12345g", "abcdef123456\n", "abcdef1234567", ""):
            with self.assertRaisesRegex(state.BadPlan, "not a plan id", msg=repr(bad)):
                state.plan_path(bad)

    def test_a_missing_or_unreadable_plan_says_so(self):
        with self.assertRaisesRegex(state.BadPlan, "no plan"):
            state.load_plan("a" * 12)
        path = state.plan_path("b" * 12)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(state.BadPlan, "cannot be read"):
            state.load_plan("b" * 12)
        path.write_text("[1]", encoding="utf-8")
        with self.assertRaisesRegex(state.BadPlan, "is not a plan"):
            state.load_plan("b" * 12)

    def test_a_state_folder_that_cannot_be_written_raises_an_oserror(self):
        blocker = self.base / "plans"
        blocker.write_text("a file where the folder should be", encoding="utf-8")
        with self.assertRaises(OSError):
            state.save_plan(BODY)


class LogTest(unittest.TestCase):
    def setUp(self):
        self.base = state_dir()

    def test_every_write_is_one_json_line_with_a_timestamp(self):
        self.assertTrue(state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"}, now=lambda: "T1"))
        self.assertTrue(state.log_write({"plan": "p1", "key": "TEAM-2", "result": "error: boom"}, now=lambda: "T2"))
        lines = (self.base / "writes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[0]), {"ts": "T1", "tool": "jk", "plan": "p1", "key": "TEAM-1", "result": "ok"})
        self.assertEqual(len(lines), 2)
        self.assertRegex(state.utc_now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_applied_are_only_the_ok_entries_of_that_plan(self):
        state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"})
        state.log_write({"plan": "p1", "key": "TEAM-2", "result": "error: boom"})
        state.log_write({"plan": "p2", "key": "TEAM-3", "result": "ok"})
        self.assertEqual(state.applied("p1"), {"TEAM-1"})
        self.assertEqual(state.applied("nada"), set())

    def test_garbage_lines_are_ignored(self):
        state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"})
        with (self.base / "writes.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("not json\n[1]\n\n")
        self.assertEqual([e["key"] for e in state.entries("p1")], ["TEAM-1"])

    def test_a_log_that_cannot_be_written_says_so_instead_of_raising(self):
        with mock.patch.object(state, "state_dir", return_value=self.base / "writes.jsonl"):
            (self.base / "writes.jsonl").write_text("file", encoding="utf-8")
            self.assertFalse(state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"}))

    def test_the_default_location_is_under_the_home_when_the_variable_is_missing(self):
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("JK_STATE_DIR", None)
            self.assertTrue(re.search(r"\.local/state/jk$", str(state.state_dir())))


if __name__ == "__main__":
    unittest.main()
