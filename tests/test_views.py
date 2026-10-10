from __future__ import annotations

import unittest

from helpers import config_dir
from jkan import views


class BuildTest(unittest.TestCase):
    def test_a_view_keeps_what_it_was_given(self):
        view = views.build("plataforma", ["PLATE", "UA"], {"group": "team"}, 5)
        self.assertEqual(view, {"version": 1, "name": "plataforma", "boards": ["PLATE", "UA"],
                                "team": {"group": "team"}, "stalled_days": 5})
        self.assertIsNone(views.build("solo", ["UA"])["team"])

    def test_a_name_is_lower_case_letters_digits_dash_and_underscore(self):
        for bad in ("", "Plat", "a b", "../x", "a\n", "x" * 41, "-x"):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build(bad, ["UA"])
        views.build("equipo-2_a", ["UA"])

    def test_boards_are_a_list_of_distinct_project_keys(self):
        for bad in ([], "PLATE", ["plate"], ["UA", "UA"], ["UA\n"], [1]):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build("v", bad)

    def test_the_team_is_a_group_or_a_list_of_people_and_nothing_that_can_alter_a_query(self):
        views.build("v", ["UA"], {"people": [{"id": "acc-1", "name": "Ana"}]})
        for bad in ({"group": 'x") OR 1=1 --'}, {"group": ""}, {"people": []}, {"people": [{"id": "a b", "name": "x"}]},
                    {"people": [{"id": 'a"b', "name": "x"}]}, {"group": "g", "people": [{"id": "a", "name": "x"}]},
                    {"other": 1}, "platform", {}):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build("v", ["UA"], bad)

    def test_stalled_days_is_a_whole_number_from_1_to_365(self):
        for bad in (0, 366, True, "7", 1.5, None):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build("v", ["UA"], None, bad)
        views.build("v", ["UA"], None, 1)
        views.build("v", ["UA"], None, 365)


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def write(self, name, text):
        (self.base / "views").mkdir(exist_ok=True)
        (self.base / "views" / f"{name}.json").write_text(text, encoding="utf-8")

    def test_save_then_load_gives_back_the_same_view(self):
        view = views.build("plataforma", ["PLATE", "UA"], {"group": "team"})
        path = views.save(view)
        self.assertEqual(path, self.base / "views" / "plataforma.json")
        self.assertEqual(views.load("plataforma"), view)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["plataforma.json"])

    def test_a_view_that_does_not_exist_says_how_to_make_it(self):
        with self.assertRaisesRegex(views.BadView, "jk team setup nada --boards"):
            views.load("nada")

    def test_a_file_that_is_not_a_view_is_refused_with_its_name(self):
        wrong = ["{not json", "[1]", "{}", '{"version": "1"}', '{"version": 1, "name": "otro", "boards": ["UA"]}',
                 '{"version": 1, "name": "v", "boards": "UA", "team": null, "stalled_days": 7}',
                 '{"version": 1, "name": "v", "boards": ["UA"], "team": null}',
                 '{"version": 1, "name": "v", "boards": ["UA"], "team": {"group": "x\\") OR 1=1"}, "stalled_days": 7}']
        for text in wrong:
            self.write("v", text)
            with self.assertRaisesRegex(views.BadView, "v.json"):
                views.load("v")

    def test_a_view_from_a_newer_jk_is_refused(self):
        self.write("v", '{"version": 2, "name": "v"}')
        with self.assertRaisesRegex(views.BadView, "newer jk"):
            views.load("v")

    def test_names_lists_the_saved_views_in_order_and_ignores_anything_else(self):
        for name in ("zeta", "alfa"):
            views.save(views.build(name, ["UA"]))
        self.write("Bad Name", "{}")
        self.assertEqual(views.names(), ["alfa", "zeta"])

    def test_names_of_a_missing_folder_is_empty(self):
        self.assertEqual(views.names(), [])


if __name__ == "__main__":
    unittest.main()
