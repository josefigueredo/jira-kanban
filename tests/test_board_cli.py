from __future__ import annotations

import contextlib
import io
import json
import unittest

import shapes
from helpers import FakeJira, config_dir, flat
from jkan import board_profile, cli


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["board"] + args, client=lambda project: jira)
    return code, out.getvalue(), err.getvalue()


def fake(**groups):
    jira = FakeJira()
    jira.status_groups = dict(groups)
    return jira


def status_named(project, name):
    return next(s for s in board_profile.load(project)["statuses"] if s["name"] == name)


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_setup_prints_what_it_understands_saves_it_and_exits_3_while_decisions_are_open(self):
        code, out, _ = run(["setup", "GDNC"], fake(GDNC=shapes.GDNC))
        self.assertEqual(code, 3)
        self.assertIn("## Perfil GDNC", out)
        self.assertIn("| Done | 22 | en curso | ¿delivered? | decidir |", flat(out))
        self.assertIn("| ON HOLD | 25 | en curso | ¿? | decidir |", flat(out))  # no guess to offer
        self.assertIn("**Faltan 2 decisiones.**", out)
        self.assertEqual(len(board_profile.open_statuses(board_profile.load("GDNC"))), 2)

    def test_a_board_with_nothing_to_decide_exits_0(self):
        code, out, _ = run(["setup", "PEHD", "--kind", "helpdesk"], fake(PEHD=shapes.PEHD))
        self.assertEqual(code, 0)
        self.assertIn("**Perfil completo.**", out)
        self.assertEqual(board_profile.load("PEHD")["kind"], "helpdesk")

    def test_setup_again_keeps_what_a_person_decided(self):
        jira = fake(GDNC=shapes.GDNC)
        run(["setup", "GDNC"], jira)
        run(["set", "GDNC", "delivered", "Done"], jira)
        code, _, _ = run(["setup", "GDNC"], jira)
        done = status_named("GDNC", "Done")
        self.assertEqual((done["role"], done["by"], code), ("delivered", "human", 3))  # ON HOLD is still open

    def test_statuses_that_disappeared_from_jira_are_reported(self):
        jira = fake(GDNC=shapes.GDNC)
        run(["setup", "GDNC"], jira)
        jira.status_groups["GDNC"] = [dict(shapes.GDNC[0], statuses=shapes.GDNC[0]["statuses"][:2])]
        _, out, _ = run(["setup", "GDNC"], jira)
        self.assertIn("Ya no existen en Jira: Done, Descartado, Bloqueado, ON HOLD.", out)

    def test_a_project_jira_does_not_know_exits_2_and_saves_nothing(self):
        code, _, err = run(["setup", "NOPE"], fake())
        self.assertEqual(code, 2)
        self.assertIn("jtk:", err)
        self.assertIsNone(board_profile.load("NOPE"))

    def test_a_jira_answer_with_no_statuses_is_not_saved_as_a_complete_profile(self):
        code, _, err = run(["setup", "EMPTY"], fake(EMPTY=[]))
        self.assertEqual(code, 1)
        self.assertIn("no statuses for EMPTY", err)
        self.assertIsNone(board_profile.load("EMPTY"))

    def test_setup_rebuilds_a_profile_it_cannot_read_and_says_so(self):
        (self.base / "profiles").mkdir()
        (self.base / "profiles" / "UA.json").write_text("{}", encoding="utf-8")
        code, out, _ = run(["setup", "UA"], fake(UA=shapes.UA))
        self.assertEqual(code, 3)  # ON HOLD and AWAITING APPROVAL still need a person
        self.assertIn("El perfil anterior no se podía leer", out)
        self.assertEqual(board_profile.load("UA")["project"], "UA")

    def test_setup_does_not_overwrite_a_profile_written_by_a_newer_jk(self):
        newer = board_profile.build("UA", shapes.UA, None)
        newer["version"] = board_profile.VERSION + 1
        board_profile.save(newer)
        code, _, err = run(["setup", "UA"], fake(UA=shapes.UA))
        self.assertEqual(code, 1)
        self.assertIn("newer jtk", err)
        raw = (self.base / "profiles" / "UA.json").read_text(encoding="utf-8")
        self.assertIn(f'"version": {board_profile.VERSION + 1}', raw)

    def test_a_key_that_is_not_a_project_key_is_refused(self):
        code, _, err = run(["setup", "ua"], fake())
        self.assertEqual(code, 1)
        self.assertIn("not a project key", err)


class SetTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        self.jira = fake(GDNC=shapes.GDNC)
        run(["setup", "GDNC"], self.jira)

    def test_set_exits_3_until_the_last_decision_and_then_0(self):
        code, _, _ = run(["set", "GDNC", "delivered", "Done"], self.jira)
        self.assertEqual(code, 3)
        code, out, _ = run(["set", "GDNC", "waiting", "ON HOLD"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("**Perfil completo.**", out)

    def test_one_bad_name_changes_nothing_and_exits_1(self):
        code, _, err = run(["set", "GDNC", "delivered", "Done", "Nope"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no status 'Nope' in GDNC", err)
        self.assertIsNone(status_named("GDNC", "Done")["role"])

    def test_set_without_a_profile_says_how_to_make_one(self):
        code, _, err = run(["set", "UA", "active", "Done"], fake())
        self.assertEqual(code, 1)
        self.assertIn("run jtk board setup UA", err)

    def test_a_role_that_does_not_exist_is_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["set", "GDNC", "hecho", "Done"], self.jira)


class ShowAndCheckTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_show_prints_the_saved_profile_with_the_same_exit_codes(self):
        jira = fake(PEHD=shapes.PEHD, GDNC=shapes.GDNC)
        run(["setup", "PEHD"], jira)
        run(["setup", "GDNC"], jira)
        self.assertEqual(run(["show", "PEHD"], jira)[0], 0)
        self.assertEqual(run(["show", "GDNC"], jira)[0], 3)

    def test_show_of_a_profile_from_a_newer_jk_exits_1(self):
        profile = board_profile.build("PEHD", shapes.PEHD, None)
        profile["version"] = board_profile.VERSION + 1
        board_profile.save(profile)
        code, _, err = run(["show", "PEHD"], fake())
        self.assertEqual(code, 1)
        self.assertIn("newer jtk", err)

    def test_show_of_a_profile_with_the_wrong_shape_exits_1_instead_of_a_traceback(self):
        (self.base / "profiles").mkdir()
        (self.base / "profiles" / "UA.json").write_text("{}", encoding="utf-8")
        code, _, err = run(["show", "UA"], fake())
        self.assertEqual(code, 1)
        self.assertIn("not a profile", err)

    def test_show_of_a_missing_profile_exits_1(self):
        self.assertEqual(run(["show", "UA"], fake())[0], 1)

    def test_show_of_a_corrupt_file_exits_1_instead_of_a_traceback(self):
        (self.base / "profiles").mkdir()
        (self.base / "profiles" / "UA.json").write_text("{not json", encoding="utf-8")
        code, _, err = run(["show", "UA"], fake())
        self.assertEqual(code, 1)
        self.assertIn("jtk:", err)

    def test_check_says_nothing_changed_or_what_did(self):
        jira = fake(UA=shapes.UA)
        run(["setup", "UA"], jira)
        code, out, _ = run(["check", "UA"], jira)
        self.assertEqual(code, 0)
        self.assertIn("sin cambios", out)
        grown = [dict(shapes.UA[0], statuses=shapes.UA[0]["statuses"] + [shapes.status(9, "QA", "in_progress")]),
                 shapes.UA[1]]
        jira.status_groups["UA"] = grown
        code, out, _ = run(["check", "UA"], jira)
        self.assertEqual(code, 1)
        self.assertIn("Nuevos: QA", out)
        self.assertIn("jtk board setup UA", out)


class SurveyTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        self.jira = fake(GDNC=shapes.GDNC, PEHD=shapes.PEHD, FDQ=shapes.FDQ)
        self.jira.project_list = [{"key": k, "name": "", "type": t, "style": ""} for k, t in
                                  (("GDNC", "software"), ("PEHD", "software"), ("FDQ", "service_desk"),
                                   ("SECRET", "software"))]

    def test_survey_counts_what_needs_a_decision_and_the_projects_it_could_not_read(self):
        code, out, _ = run(["survey", "--json"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"], {
            "projects_read": 3, "projects_denied": 1, "statuses": 14, "alta": 10, "decidir": 4,
            "projects_needing_decisions": 2, "mismatch_statuses": 1, "mismatch_projects": 1})

    def test_survey_text_ends_with_the_totals(self):
        _, out, _ = run(["survey"], self.jira)
        self.assertIn("3 proyectos leídos · 1 sin acceso · 14 estados · alta 10 (71%) · decidir 4 (29%)", out)

    def test_survey_can_be_limited_to_one_project_type(self):
        _, out, _ = run(["survey", "--json", "--type", "service_desk"], self.jira)
        self.assertEqual([p["project"] for p in json.loads(out)["projects"]], ["FDQ"])

    def test_survey_saves_nothing(self):
        run(["survey"], self.jira)
        self.assertFalse((self.base / "profiles").exists())


if __name__ == "__main__":
    unittest.main()
