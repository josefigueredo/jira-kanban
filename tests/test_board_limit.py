"""jtk board limit, the WIP limit in a profile, and the atomic JSON write views and profiles share."""
from __future__ import annotations

import contextlib
import io
import json
import unittest

import shapes
from helpers import FakeJira, config_dir
from jkan import board_profile as bp
from jkan import cli


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["board"] + args, client=lambda project: FakeJira())
    return code, out.getvalue(), err.getvalue()


class LimitCommandTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        bp.save(bp.build("PEHD", shapes.PEHD, None))

    def test_a_limit_is_saved_and_none_removes_it(self):
        code, out, _ = run(["limit", "PEHD", "3"])
        self.assertEqual((code, bp.load("PEHD")["wip_limit"]), (0, 3))
        self.assertIn("límite de WIP 3", out)
        self.assertEqual(run(["limit", "PEHD", "none"])[0], 0)
        self.assertIsNone(bp.load("PEHD")["wip_limit"])

    def test_anything_that_is_not_a_positive_whole_number_is_refused_and_changes_nothing(self):
        run(["limit", "PEHD", "3"])
        for bad in ("0", "-2", "1.5", "muchos", ""):
            code, _, err = run(["limit", "PEHD", bad])
            self.assertEqual(code, 1, bad)
            self.assertTrue(err.strip(), bad)
        self.assertEqual(bp.load("PEHD")["wip_limit"], 3)

    def test_a_limit_needs_a_profile(self):
        code, _, err = run(["limit", "UA", "3"])
        self.assertEqual(code, 1)
        self.assertIn("run jtk board setup UA", err)

    def test_setup_again_keeps_the_limit(self):
        run(["limit", "PEHD", "4"])
        jira = FakeJira()
        jira.status_groups = {"PEHD": shapes.PEHD}
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main(["board", "setup", "PEHD"], client=lambda project: jira)
        self.assertEqual(bp.load("PEHD")["wip_limit"], 4)


class ProfileLimitTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_set_wip_limit_accepts_a_positive_whole_number_or_none(self):
        profile = bp.build("PEHD", shapes.PEHD, None)
        self.assertEqual(bp.set_wip_limit(profile, 2)["wip_limit"], 2)
        self.assertIsNone(bp.set_wip_limit(profile, None)["wip_limit"])
        for bad in (0, -1, True, 1.5, "3"):
            with self.assertRaises(bp.BadSelection, msg=repr(bad)):
                bp.set_wip_limit(profile, bad)

    def test_a_profile_file_with_a_nonsense_limit_is_not_a_profile(self):
        profile = bp.build("PEHD", shapes.PEHD, None)
        profile["wip_limit"] = "muchos"
        bp.save(profile)
        with self.assertRaisesRegex(bp.BadProfile, "wrong shape"):
            bp.load("PEHD")
        self.assertEqual(bp.load_all(), {})


class WriteJsonTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_a_failed_write_leaves_neither_the_new_file_nor_a_temporary_one(self):
        target = self.base / "x" / "a.json"
        bp.write_json(target, {"ok": 1})
        with self.assertRaises(TypeError):
            bp.write_json(target, {"bad": object()})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": 1})
        self.assertEqual([p.name for p in target.parent.iterdir()], ["a.json"])


if __name__ == "__main__":
    unittest.main()
