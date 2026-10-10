from __future__ import annotations

import json
import unittest

import shapes
from helpers import FakeJira, config_dir, issue
from jkan import board_profile
from test_report_cli import run


def save_profile(project, groups, decisions):
    profile = board_profile.build(project, groups, None)
    for role, names in decisions.items():
        board_profile.assign(profile, role, names)
    board_profile.save(profile)


def closed(key):  # the «Done» GDNC files under in progress
    return issue(key, status="Done", status_id="22", category="in_progress", changed="2026-10-07")


def dropped(key):
    return issue(key, status="Descartado", status_id="23", category="done", changed="2026-10-07")


def active(key):
    return issue(key, status="En análisis", status_id="21", category="in_progress", changed="2026-09-01")


def holding(key):
    return issue(key, status="ON HOLD", status_id="25", category="in_progress", changed="2026-09-01")


def blocked(key):
    return issue(key, status="Bloqueado", status_id="24", category="in_progress", changed="2026-09-01")


class RoleReportsTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        save_profile("GDNC", shapes.GDNC, {"delivered": ["Done"], "waiting": ["ON HOLD"]})

    def answer(self, *issues):
        jira = FakeJira()
        jira.search_answer = lambda jql: list(issues)
        return jira

    def test_done_counts_a_done_filed_under_in_progress_as_closed_and_keeps_dropped_apart(self):
        jira = self.answer(closed("GDNC-1"), dropped("GDNC-2"), active("GDNC-3"))
        code, out, _ = run(["done", "--since", "2026-10-01", "--until", "2026-10-07"], jira)
        self.assertEqual(code, 0)
        self.assertIn("**1 cerradas · 1 en curso** · 1 descartadas", out)
        self.assertNotIn("⚠", out)

    def test_next_offers_neither_a_done_nor_work_that_is_waiting_on_someone(self):
        jira = self.answer(closed("GDNC-1"), active("GDNC-3"), holding("GDNC-4"))
        _, out, _ = run(["next"], jira)
        self.assertIn("GDNC-3", out)
        self.assertNotIn("GDNC-1", out)
        self.assertNotIn("GDNC-4", out)

    def test_blocked_comes_from_the_role_not_from_the_conventions_list(self):
        jira = self.answer(blocked("GDNC-5"), closed("GDNC-1"), holding("GDNC-4"))
        _, out, _ = run(["blocked"], jira)
        self.assertIn("Estado Bloqueado, sin link", out)  # conventions.json only lists «Blocked»
        self.assertNotIn("GDNC-1", out)
        self.assertNotIn("GDNC-4", out)

    def test_stats_counts_the_done_as_delivered_and_not_as_work_in_progress(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [] if "statusCategory = Done" in jql else [closed("GDNC-1"), active("GDNC-3")]
        _, out, _ = run(["stats"], jira)
        self.assertIn("| 2026-10-05 | 1 (en curso) |", out)
        self.assertIn("GDNC-3", out)
        self.assertNotIn("GDNC-1", out)

    def test_a_project_without_a_profile_says_so_and_still_reports_by_category(self):
        jira = self.answer(issue("PLATE-9", status="Done", category="done", changed="2026-10-07"))
        _, out, _ = run(["done", "--since", "2026-10-01"], jira)
        self.assertIn("> ⚠ Sin perfil: PLATE.", out)
        self.assertIn("**1 cerradas · 0 en curso**", out)

    def test_an_undecided_status_is_reported_and_never_counted_as_closed(self):
        save_profile("OYP", shapes.GDNC, {})
        jira = self.answer(issue("OYP-1", status="Done", status_id="22", category="in_progress", changed="2026-10-07"))
        _, out, _ = run(["done", "--since", "2026-10-01"], jira)
        self.assertIn("**0 cerradas · 0 en curso**", out)
        self.assertIn("> ⚠ Perfil sin confirmar en OYP: faltan decidir Done.", out)

    def test_a_status_the_profile_never_saw_is_reported_and_does_not_crash(self):
        jira = self.answer(issue("GDNC-7", status="Nuevo", status_id="99", category="todo"))
        code, out, _ = run(["next"], jira)
        self.assertEqual(code, 0)
        self.assertIn("> ⚠ Estado desconocido: Nuevo (GDNC).", out)

    def test_a_profile_file_nobody_can_read_does_not_crash_the_reports_and_is_named(self):
        (self.base / "profiles" / "UA.json").write_text('{"version": "2"}', encoding="utf-8")
        newer = board_profile.build("PEHD", shapes.PEHD, None)
        newer["version"] = board_profile.VERSION + 1
        board_profile.save(newer)
        jira = self.answer(issue("UA-1", status="To Do", status_id="1"), issue("PEHD-1", status="To Do", status_id="50"))
        code, out, _ = run(["next"], jira)
        self.assertEqual(code, 0)
        self.assertIn("> ⚠ Perfil de UA ilegible", out)
        self.assertIn("actualizá jtk", out)
        self.assertNotIn("Sin perfil: PEHD", out)

    def test_json_carries_the_notes_instead_of_a_banner(self):
        _, clean, _ = run(["done", "--since", "2026-10-01", "--json"], self.answer(closed("GDNC-1")))
        self.assertEqual(json.loads(clean)["profile_notes"], [])
        _, noisy, _ = run(["done", "--since", "2026-10-01", "--json"], self.answer(issue("PLATE-9", category="done")))
        self.assertEqual(len(json.loads(noisy)["profile_notes"]), 1)


if __name__ == "__main__":
    unittest.main()
