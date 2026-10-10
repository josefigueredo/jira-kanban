from __future__ import annotations

import unittest

import team_fixtures as fx
from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import team, team_render

LINK = lambda key: f"[{key}]"  # noqa: E731
VIEW = fx.view()


class HeadTest(unittest.TestCase):
    def test_the_first_block_names_the_view_the_boards_the_team_the_window_and_the_profiles(self):
        text = team_render.head("Flujo", VIEW, fx.profiles(), fx.TODAY, ("2026-09-14", fx.TODAY))
        self.assertEqual(text, "## Flujo\n**View:** plataforma · **Boards:** TEAM, DESK · **Equipo:** grupo team · "
                               "**Ventana:** 2026-09-14 → 2026-10-08 · **Consultado:** 2026-10-08 · **Perfiles:** confirmados")

    def test_undecided_statuses_make_the_profiles_unconfirmed_and_say_where(self):
        profiles = {"TEAM": fx.profile("TEAM", decide_waiting=False), "DESK": fx.profile("DESK", kind="helpdesk")}
        self.assertIn("**Perfiles:** sin confirmar — TEAM (1 sin decidir)", team_render.head("x", VIEW, profiles, fx.TODAY))

    def test_the_team_is_described_whatever_its_form(self):
        self.assertEqual(team_render.team_label(None), "todos los asignados")
        self.assertEqual(team_render.team_label({"people": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}), "2 personas")


class TableTest(unittest.TestCase):
    ROWS = [[n, "x"] for n in range(25)]

    def test_more_than_20_rows_are_cut_and_the_note_says_how_many_were_left_out(self):
        text = team_render.table(["N", "T"], self.ROWS, False)
        self.assertEqual(text.count("\n| "), 20 + 1)  # the separator line plus 20 rows
        self.assertTrue(text.endswith("_… y 5 más (usá --all)._"))

    def test_all_lifts_the_cut(self):
        text = team_render.table(["N", "T"], self.ROWS, True)
        self.assertNotIn("más", text)
        self.assertIn("| 24 | x |", text)

    def test_exactly_20_rows_are_not_cut(self):
        self.assertNotIn("más", team_render.table(["N", "T"], self.ROWS[:20], False))

    def test_no_rows_says_nothing_instead_of_an_empty_table(self):
        self.assertEqual(team_render.table(["N"], [], False, "_Nada._"), "_Nada._")


class LimitsTest(unittest.TestCase):
    def test_every_report_ends_with_its_own_limits(self):
        for verb in ("status", "stalled", "blocked", "flow", "digest", "desk", "rollup"):
            text = team_render.limits(verb)
            self.assertTrue(text.startswith("### Límites\n- "), verb)

    def test_the_desk_report_says_there_is_no_sla_and_stalled_says_what_it_is_not(self):
        self.assertIn("Sin SLA", team_render.limits("desk"))
        self.assertIn("no es «sin progreso»", team_render.limits("stalled"))


class BodiesTest(unittest.TestCase):
    def test_status_shows_the_verdict_only_where_there_is_a_limit(self):
        open_ = [fx.at("TEAM-1", "active", assignee=fx.ANA), fx.at("TEAM-2", "blocked", assignee=fx.ANA),
                 fx.at("DESK-1", "active", assignee=fx.ANA)]
        text = team_render.render_status(team.status_report(open_, VIEW, fx.profiles(TEAM=2)), False)
        self.assertIn("| Ana Gómez | TEAM | 2 | 0 | 1 | 1 | 0 | 0 | 2 | 2 | sin espacio |", text)
        self.assertIn("| Ana Gómez | DESK | 1 | 0 | 1 | 0 | 0 | 0 | 1 | – | – |", text)
        self.assertIn("**3 abiertos**", text)

    def test_flow_flags_a_small_n_and_names_the_dropped_apart(self):
        report = team.flow_report([fx.at("TEAM-1", "delivered", created="2026-10-01", resolved="2026-10-06")],
                                  [fx.at("TEAM-2", "dropped", changed="2026-10-02")], [], fx.TODAY, 2)
        text = team_render.render_flow(report, False, LINK)
        self.assertIn("n=1 · mediana 5 d · p85 5 d · pocos casos, no concluyas nada", text)
        self.assertIn("**1 entregados** desde 2026-09-28; 1 descartados (no cuentan como entregas)", text)

    def test_stalled_names_the_two_day_counts(self):
        report = team.stalled_report([fx.at("TEAM-1", "active", changed="2026-09-20", updated="2026-10-07")], fx.TODAY, 7)
        text = team_render.render_stalled(report, False, LINK)
        self.assertIn("| [TEAM-1] | Summary of TEAM-1 | Yo | En curso | 18 | 1 |", text)
        self.assertIn("**1 de 1 en curso** llevan 7 días o más", text)

    def test_blocked_separates_the_waiting(self):
        report = team.blocked_report([fx.at("TEAM-1", "blocked"), fx.at("TEAM-2", "waiting")], {"blocked_statuses": []}, fx.TODAY)
        text = team_render.render_blocked(report, False, LINK)
        self.assertIn("### Bloqueados (1)", text)
        self.assertIn("### Esperando a un tercero (1)", text)

    def test_rollup_shows_a_view_that_could_not_be_computed_instead_of_dropping_it(self):
        good = {"view": "a", "open": 3, "blocked": 1, "stalled": 0, "delivered": 2, "lead": {"n": 4, "median": 3, "p85": 6}}
        text = team_render.render_rollup([good, {"view": "b", "error": "sin perfil: UA"}], False)
        self.assertIn("| a | 3 | 1 | 0 | 2 | 6 d (n=4) |", text)
        self.assertIn("| b | sin perfil: UA |", text)


if __name__ == "__main__":
    unittest.main()
