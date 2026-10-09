from __future__ import annotations

import json
import unittest

import shapes
from helpers import config_dir
from jkan import board_profile as bp
from jkan import roles


class BuildTest(unittest.TestCase):
    def test_every_status_gets_a_proposal_and_the_hard_ones_stay_open(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        self.assertEqual({s["name"]: s["role"] for s in profile["statuses"]},
                         {"Abierto": "todo", "En análisis": "active", "Done": None, "Descartado": "dropped",
                          "Bloqueado": "blocked", "ON HOLD": None})
        self.assertEqual([s["name"] for s in bp.open_statuses(profile)], ["Done", "ON HOLD"])
        self.assertEqual(profile["kind"], "flow")

    def test_a_status_shared_by_several_issue_types_appears_once(self):
        profile = bp.build("UA", shapes.UA, None)
        self.assertEqual(sorted(s["id"] for s in profile["statuses"]), ["1", "2", "3", "4", "5", "6", "7", "8"])
        self.assertEqual([w["types"] for w in profile["workflows"]], [["Historia", "Error", "Epic", "Subtask"], ["Tarea"]])

    def test_a_status_that_exists_for_one_issue_type_only_still_gets_its_role(self):
        profile = bp.build("UA", shapes.UA, None)
        issue = {"key": "UA-9", "status": "RELEASED", "status_id": "7", "category": "done"}  # only Tarea has it
        roles.annotate([issue], {"UA": profile})
        self.assertEqual(issue["role"], "delivered")

    def test_a_clean_board_needs_no_decision(self):
        profile = bp.build("PEHD", shapes.PEHD, "helpdesk")
        self.assertEqual((bp.open_statuses(profile), profile["kind"]), ([], "helpdesk"))

    def test_a_kind_that_does_not_exist_is_refused(self):
        with self.assertRaises(ValueError):
            bp.build("PEHD", shapes.PEHD, "kanban")

    def test_the_fingerprint_follows_the_set_of_status_ids(self):
        first = bp.build("UA", shapes.UA, None)["fingerprint"]
        reversed_groups = [dict(g, statuses=list(reversed(g["statuses"]))) for g in shapes.UA]
        self.assertEqual(bp.build("UA", reversed_groups, None)["fingerprint"], first)
        self.assertNotEqual(bp.build("PEHD", shapes.PEHD, None)["fingerprint"], first)


class RebuildTest(unittest.TestCase):
    def test_a_decision_survives_a_new_setup_and_a_rename(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        bp.assign(profile, "delivered", ["Done"])
        renamed = [dict(g, statuses=[dict(s, name="Hecho") if s["id"] == "22" else s for s in g["statuses"]])
                   for g in shapes.GDNC]
        again = bp.build("GDNC", renamed, None, profile)
        done = next(s for s in again["statuses"] if s["id"] == "22")
        self.assertEqual((done["name"], done["role"], done["by"]), ("Hecho", "delivered", "human"))

    def test_statuses_jira_no_longer_has_are_dropped_and_kind_and_wip_limit_are_kept(self):
        profile = bp.build("GDNC", shapes.GDNC, "scrum")
        profile["wip_limit"] = 6
        smaller = [dict(shapes.GDNC[0], statuses=shapes.GDNC[0]["statuses"][:2])]
        again = bp.build("GDNC", smaller, None, profile)
        self.assertEqual(([s["id"] for s in again["statuses"]], again["kind"], again["wip_limit"]),
                         (["20", "21"], "scrum", 6))


class AssignTest(unittest.TestCase):
    def setUp(self):
        self.profile = bp.build("BDBDESK", shapes.BDBDESK, None)

    def roles_by_id(self):
        return {s["id"]: (s["role"], s["by"]) for s in self.profile["statuses"]}

    def test_names_match_whatever_the_case_or_the_accents(self):
        bp.assign(self.profile, "delivered", ["FINALIZADO", "resuelto"])
        self.assertEqual(self.roles_by_id()["32"], ("delivered", "human"))
        self.assertEqual(self.roles_by_id()["33"], ("delivered", "human"))

    def test_two_statuses_with_the_same_name_need_an_id(self):
        profile = bp.build("SAME", shapes.SAME_NAME, None)
        with self.assertRaisesRegex(bp.BadSelection, r"id:61, id:62"):
            bp.assign(profile, "active", ["en ejecucion"])
        bp.assign(profile, "active", ["id:61", "id:62"])
        self.assertEqual([s["role"] for s in profile["statuses"] if s["id"] in ("61", "62")], ["active", "active"])

    def test_one_bad_token_changes_nothing(self):
        before = json.dumps(self.profile, sort_keys=True)
        with self.assertRaisesRegex(bp.BadSelection, "no status 'No existe' in BDBDESK"):
            bp.assign(self.profile, "delivered", ["Finalizado", "No existe"])
        self.assertEqual(json.dumps(self.profile, sort_keys=True), before)

    def test_naming_a_status_twice_in_one_call_is_harmless(self):
        bp.assign(self.profile, "delivered", ["Finalizado", "finalizado", "id:32"])
        self.assertEqual(self.roles_by_id()["32"], ("delivered", "human"))

    def test_a_role_that_does_not_exist_is_refused(self):
        with self.assertRaisesRegex(bp.BadSelection, "unknown role 'hecho'"):
            bp.assign(self.profile, "hecho", ["Finalizado"])


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_save_then_load_gives_back_the_same_profile_and_leaves_no_temporary_file(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        path = bp.save(profile)
        self.assertEqual(path, self.base / "profiles" / "GDNC.json")
        self.assertEqual(bp.load("GDNC"), profile)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["GDNC.json"])

    def test_a_missing_profile_is_none(self):
        self.assertIsNone(bp.load("NOPE"))

    def test_a_project_key_cannot_point_outside_the_folder(self):
        for bad in ("../x", "a/b", "lower", ""):
            with self.assertRaises(ValueError, msg=bad):
                bp.path_of(bad)

    def test_load_all_skips_a_file_it_cannot_read(self):
        bp.save(bp.build("GDNC", shapes.GDNC, None))
        (self.base / "profiles" / "BAD.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(list(bp.load_all()), ["GDNC"])

    def test_a_profile_from_a_newer_jk_is_refused_by_load_and_skipped_by_load_all(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        profile["version"] = bp.VERSION + 1
        bp.save(profile)
        with self.assertRaisesRegex(ValueError, "newer jk"):
            bp.load("GDNC")
        self.assertEqual(bp.load_all(), {})

    def test_a_json_file_that_is_not_an_object_is_not_a_profile(self):
        (self.base / "profiles").mkdir()
        (self.base / "profiles" / "UA.json").write_text("[1, 2]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not a profile"):
            bp.load("UA")

    def test_the_config_directory_follows_the_environment(self):
        self.assertEqual(bp.config_dir(), self.base)


if __name__ == "__main__":
    unittest.main()
