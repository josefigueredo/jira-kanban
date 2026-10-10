from __future__ import annotations

import contextlib
import io
import json
import unittest

import team_fixtures as fx
from helpers import FakeJira, config_dir, issue
from jkan import board_profile, cli, views
from jkan.jira import JiraError


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["team"] + args, client=lambda project: jira, today=lambda: fx.TODAY)
    return code, out.getvalue(), err.getvalue()


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        self.jira = FakeJira()

    def test_a_group_view_is_saved_after_checking_that_the_group_exists(self):
        code, out, _ = run(["setup", "nuevo", "--boards", "TEAM,DESK", "--group", "team"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("Grupo team: 7 miembros.", out)
        self.assertEqual(views.load("nuevo")["team"], {"group": "team"})
        self.assertIn("View guardado en", out)

    def test_it_says_which_boards_still_have_no_profile(self):
        board_profile.save(fx.profile("TEAM"))
        _, out, _ = run(["setup", "nuevo", "--boards", "TEAM,DESK"], self.jira)
        self.assertIn("Falta el perfil de: DESK. Corré `jk board setup KEY`", out)

    def test_a_group_that_does_not_exist_is_refused_and_nothing_is_saved(self):
        code, _, err = run(["setup", "nuevo", "--boards", "TEAM", "--group", "no-such-group"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("Jira has no group 'no-such-group'", err)
        self.assertEqual(views.names(), [])

    def test_people_are_resolved_to_account_ids(self):
        code, out, _ = run(["setup", "nuevo", "--boards", "TEAM", "--people", "Ana Gómez"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(views.load("nuevo")["team"], {"people": [{"id": "acc-ana", "name": "Ana Gómez"}]})
        self.assertIn("Personas: Ana Gómez.", out)

    def test_an_ambiguous_person_is_never_guessed(self):
        code, _, err = run(["setup", "nuevo", "--boards", "TEAM", "--people", "Martin"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)
        self.assertEqual(views.names(), [])

    def test_a_group_and_people_together_are_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["setup", "nuevo", "--boards", "TEAM", "--group", "g", "--people", "Ana"], self.jira)

    def test_bad_input_is_refused_before_anything_is_saved(self):
        for args in (["--boards", "TEAM,x y"], ["--boards", ""], ["--boards", "TEAM", "--stalled-days", "0"]):
            code, _, err = run(["setup", "nuevo"] + args, self.jira)
            self.assertEqual(code, 1, args)
            self.assertTrue(err.strip(), args)
        self.assertEqual(views.names(), [])


class ShowAndListTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        board_profile.save(fx.profile("TEAM"))
        views.save(fx.view())

    def test_show_prints_the_view_and_the_state_of_each_profile(self):
        code, out, _ = run(["show", "plataforma"], FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("**Boards:** TEAM, DESK", out)
        self.assertIn("| TEAM | confirmado |", out)
        self.assertIn("| DESK | sin perfil |", out)

    def test_list_names_the_views_and_an_empty_list_says_how_to_start(self):
        _, out, _ = run(["list"], FakeJira())
        self.assertIn("| plataforma | TEAM, DESK | grupo team |", out)
        config_dir()
        self.assertIn("Creá uno con `jk team setup`", run(["list"], FakeJira())[1])

    def test_an_unknown_view_says_how_to_create_it(self):
        code, _, err = run(["show", "nada"], FakeJira())
        self.assertEqual(code, 1)
        self.assertIn("jk team setup nada --boards", err)


class ReportsTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        for prof in fx.profiles(TEAM=2).values():
            board_profile.save(prof)
        views.save(fx.view())
        self.jira = FakeJira()

    def open_work(self):
        return [fx.at("TEAM-1", "active", assignee=fx.ANA, changed="2026-09-20"), fx.at("TEAM-2", "blocked", assignee=fx.ANA),
                fx.at("TEAM-3", "todo", assignee=None), fx.at("DESK-1", "waiting", assignee=fx.BETO)]

    def test_a_board_without_a_profile_is_refused_and_nothing_is_asked_of_jira(self):
        (self.base / "profiles" / "DESK.json").unlink()
        code, _, err = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no profile for DESK: run jk board setup DESK", err)
        self.assertEqual(self.jira.jqls, [])

    def test_a_profile_file_nobody_can_read_is_named_in_the_refusal(self):
        (self.base / "profiles" / "DESK.json").write_text("{}", encoding="utf-8")
        code, _, err = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("DESK.json is not a profile", err)

    def test_status_end_to_end_and_it_writes_nothing(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("## Estado del equipo\n**View:** plataforma · **Boards:** TEAM, DESK"))
        self.assertIn("**Perfiles:** confirmados", out)
        self.assertIn("**4 abiertos**", out)
        self.assertIn("| TEAM | 3 | 1 | 1 | 1 | 0 | 0 | 1 |", out)
        self.assertTrue(out.rstrip().endswith("sin límite, solo números."))
        self.assertEqual(self.jira.writes, [])

    def test_json_carries_the_same_facts_without_the_markdown(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["status", "plataforma", "--json"], self.jira)
        data = json.loads(out)
        self.assertEqual((code, data["view"], data["boards"], data["truncated"], data["notes"]),
                         (0, "plataforma", ["TEAM", "DESK"], False, []))
        self.assertEqual(data["report"]["n"], 4)

    def test_a_status_the_profile_never_saw_is_reported(self):
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "todo", status="Nuevo", status_id="99")])
        _, out, _ = run(["status", "plataforma"], self.jira)
        self.assertIn("> ⚠ Estado desconocido: Nuevo (TEAM).", out)

    def test_undecided_statuses_are_counted_as_without_role_and_announced(self):
        board_profile.save(fx.profile("TEAM", wip_limit=2, decide_waiting=False))
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "waiting")])
        _, out, _ = run(["status", "plataforma"], self.jira)
        self.assertIn("**Perfiles:** sin confirmar — TEAM (1 sin decidir)", out)
        self.assertIn("> ⚠ Perfil sin confirmar en TEAM: faltan decidir Esperando al cliente.", out)
        self.assertIn("| TEAM | 1 | 0 | 0 | 0 | 0 | 1 | 0 |", out)

    def test_a_search_that_hits_the_cap_says_so_instead_of_cutting_in_silence(self):
        self.jira.search_answer = fx.answers(open_=[fx.at(f"TEAM-{n}", "todo") for n in range(1001)])
        code, out, _ = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("> ⚠ La búsqueda llegó al tope de 1000 issues: faltan resultados.", out)
        self.assertTrue(json.loads(run(["status", "plataforma", "--json"], self.jira)[1])["truncated"])

    def test_tables_are_cut_at_20_rows_and_all_lifts_the_cut(self):
        crowd = [fx.at(f"TEAM-{n}", "active", assignee={"id": f"acc-{n}", "name": f"Persona {n:02d}"}) for n in range(25)]
        self.jira.search_answer = fx.answers(open_=crowd)
        _, cut, _ = run(["status", "plataforma"], self.jira)
        _, full, _ = run(["status", "plataforma", "--all"], self.jira)
        self.assertIn("_… y 5 más (usá --all)._", cut)
        self.assertNotIn("más (usá", full)
        self.assertIn("Persona 24", full)
        self.assertNotIn("Persona 24", cut)

    def test_stalled_uses_the_view_days_unless_asked_otherwise(self):
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "active", changed="2026-10-02"),
                                                    fx.at("TEAM-2", "active", changed="2026-09-01")])
        _, default, _ = run(["stalled", "plataforma"], self.jira)
        _, three, _ = run(["stalled", "plataforma", "--days", "3"], self.jira)
        self.assertIn("**1 de 2 en curso** llevan 7 días", default)
        self.assertIn("**2 de 2 en curso** llevan 3 días", three)
        code, _, err = run(["stalled", "plataforma", "--days", "0"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("--days must be", err)

    def test_blocked_end_to_end(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["blocked", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("### Bloqueados (1)", out)
        self.assertIn("### Esperando a un tercero (1)", out)
        self.assertIn("[TEAM-2](https://example.atlassian.net/browse/TEAM-2)", out)

    def test_flow_asks_for_open_delivered_and_dropped_and_checks_the_weeks(self):
        self.jira.search_answer = fx.answers(open_=self.open_work(),
                                             delivered=[fx.at("TEAM-9", "delivered", created="2026-10-01", resolved="2026-10-06")])
        code, out, _ = run(["flow", "plataforma", "--weeks", "2"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.jira.jqls), 3)
        self.assertIn("**Ventana:** 2026-09-28 → 2026-10-08", out)
        self.assertIn("**1 entregados** desde 2026-09-28", out)
        self.assertEqual(run(["flow", "plataforma", "--weeks", "0"], self.jira)[0], 1)

    def test_digest_needs_a_period_and_refuses_a_bad_one(self):
        self.jira.search_answer = fx.answers(open_=self.open_work(), created=[fx.at("TEAM-7", "todo", created="2026-10-02")])
        code, out, _ = run(["digest", "plataforma", "--since", "2026-10-01"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.jira.jqls), 4)
        self.assertIn("**Ventana:** 2026-10-01 → 2026-10-08", out)
        self.assertIn("**0 entregados · 0 descartados · 1 nuevos**", out)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["digest", "plataforma"], self.jira)
        self.assertEqual(run(["digest", "plataforma", "--since", "ayer"], self.jira)[0], 1)
        self.assertEqual(run(["digest", "plataforma", "--since", "2026-10-09"], self.jira)[0], 1)

    def test_desk_reports_the_help_desk_boards_and_refuses_a_view_without_one(self):
        self.jira.search_answer = fx.answers(open_=[fx.at("DESK-1", "todo", created="2026-10-07"),
                                                    fx.at("DESK-2", "waiting", created="2026-08-01")])
        code, out, _ = run(["desk", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("| DESK | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 |", out)
        self.assertIn("Sin SLA", out)
        views.save(fx.view(boards=("TEAM",), name="solo"))
        code, _, err = run(["desk", "solo"], FakeJira())
        self.assertEqual(code, 1)
        self.assertIn("no help desk board", err)

    def test_rollup_gives_a_row_per_view_and_keeps_a_view_that_cannot_be_computed(self):
        views.save(fx.view(boards=("UA",), name="otro"))
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["rollup", "plataforma", "otro"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("| plataforma | 4 | 1 | 1 | 0 | – |", out)
        self.assertIn("| otro | sin perfil: UA |", out)
        data = json.loads(run(["rollup", "plataforma", "--json"], self.jira)[1])
        self.assertEqual(data["rows"][0]["open"], 4)

    def test_rollup_keeps_the_other_rows_when_one_view_fails_inside_jira(self):
        views.save(fx.view(boards=("DESK",), team={"group": "gone-group"}, name="otro"))
        views.save(fx.view(boards=("TEAM",), name="solo"))
        good = fx.answers(open_=self.open_work())

        def answer(jql):
            if "gone-group" in jql:
                raise JiraError("POST /rest/api/3/search/jql: HTTP 400 group does not exist")
            return good(jql)

        self.jira.search_answer = answer
        code, out, _ = run(["rollup", "solo", "otro"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("| solo |", out)
        self.assertIn("| otro | POST /rest/api/3/search/jql: HTTP 400", out)

    def test_rollup_keeps_the_other_rows_when_a_profile_holds_data_that_cannot_be_queried(self):
        path = self.base / "profiles" / "DESK.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for status in data["statuses"]:
            if status["id"] == "15":
                status["id"] = "abc"
        path.write_text(json.dumps(data), encoding="utf-8")
        views.save(fx.view(boards=("DESK",), name="otro"))
        views.save(fx.view(boards=("TEAM",), name="solo"))
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["rollup", "solo", "otro"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("| solo |", out)
        self.assertIn("| otro | not status ids", out)

    def test_an_unreadable_profile_is_named_in_rollup_and_show_not_called_missing(self):
        (self.base / "profiles" / "DESK.json").write_text("{not json", encoding="utf-8")
        views.save(fx.view(boards=("DESK",), name="otro"))
        _, out, _ = run(["rollup", "otro"], self.jira)
        self.assertIn("DESK.json", out)
        _, shown, _ = run(["show", "otro"], self.jira)
        self.assertIn("DESK.json", shown)

    def test_a_profile_from_a_newer_jk_says_to_update_jk_not_to_run_setup(self):
        path = self.base / "profiles" / "DESK.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = 99
        path.write_text(json.dumps(data), encoding="utf-8")
        _, _, err = run(["status", "plataforma"], self.jira)
        self.assertIn("update jk", err)
        self.assertNotIn("run jk board setup", err)

    def test_flow_marks_as_stalled_with_the_days_of_the_view_like_stalled_does(self):
        views.save(fx.view(name="lento", stalled_days=14))
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "active", changed="2026-09-28")])  # 10 days
        _, stalled, _ = run(["stalled", "lento"], self.jira)
        _, flow, _ = run(["flow", "lento"], self.jira)
        self.assertIn("**0 de 1 en curso**", stalled)
        self.assertNotIn("estancado", flow)

    def test_no_report_writes_anything_to_jira(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        for args in (["status", "plataforma"], ["stalled", "plataforma"], ["blocked", "plataforma"],
                     ["flow", "plataforma"], ["digest", "plataforma", "--since", "2026-10-01"], ["desk", "plataforma"],
                     ["rollup", "plataforma"]):
            run(args, self.jira)
        self.assertEqual(self.jira.writes, [])


if __name__ == "__main__":
    unittest.main()
