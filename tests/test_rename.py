from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, state_dir
from jkan import board_profile, state


class RenameTest(unittest.TestCase):
    def test_the_entry_point_is_jtk_py_and_jk_py_is_gone(self):
        self.assertTrue((ROOT / "jtk.py").is_file())
        self.assertFalse((ROOT / "jk.py").exists())

    def test_the_installed_entry_point_starts_and_says_jtk(self):
        done = subprocess.run([sys.executable, str(ROOT / "jtk.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertRegex(done.stdout, r"^usage: jtk\b")

    def test_no_parser_still_calls_itself_jk(self):
        for path in (ROOT / "jkan").glob("*.py"):
            self.assertIsNone(re.search(r'prog="jk\b', path.read_text(encoding="utf-8")), path.name)

    def test_the_default_folders_are_the_new_names(self):
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            for name in ("JTK_CONFIG_DIR", "JTK_STATE_DIR", "JK_CONFIG_DIR", "JK_STATE_DIR"):
                env.pop(name, None)
            self.assertRegex(str(board_profile.config_dir()), r"\.config/jtk$")
            self.assertRegex(str(state.state_dir()), r"\.local/state/jtk$")

    def test_the_old_variables_are_not_read(self):
        other = tempfile.mkdtemp(prefix="jtk-old-")
        with mock.patch.dict("os.environ", {"JK_CONFIG_DIR": other, "JK_STATE_DIR": other}, clear=False) as env:
            env.pop("JTK_CONFIG_DIR", None)
            env.pop("JTK_STATE_DIR", None)
            self.assertNotEqual(str(board_profile.config_dir()), other)
            self.assertNotEqual(str(state.state_dir()), other)

    def test_new_log_lines_say_jtk(self):
        base = state_dir()
        state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"})
        line = json.loads((base / "writes.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(line["tool"], "jtk")

    def test_lines_written_before_the_rename_still_count_as_applied(self):
        base = state_dir()
        (base / "writes.jsonl").write_text(
            json.dumps({"ts": "T0", "tool": "jk", "plan": "p1", "key": "TEAM-1", "result": "ok"}) + "\n",
            encoding="utf-8")
        self.assertEqual(state.applied("p1"), {"TEAM-1"})


if __name__ == "__main__":
    unittest.main()
