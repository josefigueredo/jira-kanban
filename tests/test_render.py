from __future__ import annotations

import unittest
from datetime import date

from helpers import CONVENTIONS, issue
from jkan import render, stats, standup

TODAY = date(2026, 10, 8)
plain = lambda key: key  # noqa: E731
HEAD = render.head("Hecho", "vos", TODAY, (date(2026, 10, 1), date(2026, 10, 7)), "PLATE")


class TableTest(unittest.TestCase):
    def test_table_escapes_pipes_and_marks_missing_cells(self):
        self.assertEqual(render.table(["Key", "Título"], [["A", "b|c"], ["B", None]]),
                         "| Key | Título |\n| --- | --- |\n| A | b\\|c |\n| B | – |")

    def test_empty_table_says_so(self):
        self.assertEqual(render.table(["Key"], [], empty="_Nada bloqueado._"), "_Nada bloqueado._")

    def test_head_names_who_the_window_and_when(self):
        self.assertEqual(HEAD, "## Hecho\n**Quién:** vos · **Ventana:** 2026-10-01 → 2026-10-07 · **Proyecto:** PLATE · "
                               "**Consultado:** 2026-10-08")


class DoneTest(unittest.TestCase):
    def test_tree_uses_box_characters_and_marks_context(self):
        epic = {"key": "PLATE-100", "summary": "Épica", "issuetype": "Epic"}
        story = issue("PLATE-101", category="done", status="Done", changed="2026-10-07", parent=epic)
        sub = issue("PLATE-103", issuetype="Subtarea", category="done", status="Done", changed="2026-10-06")
        tree = standup.done_tree([story, sub], {}, "Epic")
        text = render.render_tree(tree)
        self.assertEqual(text.splitlines(), [
            "Issue         Estado  Fecha       Título",
            "PLATE-100" + " " * 25 + "Épica (contexto)",
            "└─ PLATE-101  Done    2026-10-07  Summary of PLATE-101",
            "Sin épica",
            "└─ PLATE-103  Done    2026-10-06  Summary of PLATE-103"])

    def test_tree_columns_line_up_whatever_the_depth_the_status_or_the_title(self):
        node = lambda key, title, status, children=(): {  # noqa: E731
            "issue": {"key": key, "summary": title, "status": status, "changed": "2026-10-02"},
            "context": False, "children": list(children)}
        leaf = node("PLATE-495", "[QA] Fijar los commits de referencia con un título larguísimo " * 2, "Done")
        mid = node("PLATE-492", "[QA] Auditar", "PROCESANDO", [leaf])
        top = node("PLATE-491", "Línea base", "Done", [mid, node("PLATE-493", "Corto", "Blocked")])
        lines = render.render_tree([top]).splitlines()
        self.assertEqual(len(lines), 5)
        statuses = [line.index(word) for line, word in zip(lines[1:], ("Done", "PROCESANDO", "Done", "Blocked"))]
        dates = [line.index("2026-10-02") for line in lines[1:]]
        titles = [line.index(title) for line, title in zip(lines[1:], ("Línea base", "[QA] Auditar", "[QA] Fijar", "Corto"))]
        self.assertEqual(len(set(statuses)), 1)
        self.assertEqual(len(set(dates)), 1)
        self.assertEqual(len(set(titles)), 1)
        self.assertEqual(lines[0].index("Estado"), statuses[0])
        self.assertEqual(lines[0].index("Fecha"), dates[0])
        self.assertEqual(lines[0].index("Título"), titles[0])

    def test_render_done_has_totals_and_a_fenced_tree_or_an_empty_message(self):
        busy = render.render_done(HEAD, {"done": 7, "in_progress": 3, "tree": standup.done_tree([issue("PLATE-5")], {}, "Epic")})
        self.assertIn("**7 cerradas · 3 en curso**", busy)
        self.assertIn("```text", busy)
        self.assertIn("último cambio", busy)
        self.assertIn("_Nada en esta ventana._", render.render_done(HEAD, {"done": 0, "in_progress": 0, "tree": []}))


class NextAndBlockedTest(unittest.TestCase):
    def test_render_next_has_three_tables(self):
        tables = standup.next_tables(
            [issue("PLATE-1", priority="High", duedate="2026-10-05"), issue("PLATE-2", status="Blocked", flagged=True, duedate="2026-10-09")],
            [issue("PLATE-7", assignee=None, parent={"key": "PLATE-100", "summary": "", "issuetype": "Epic"})],
            TODAY, date(2026, 10, 10), CONVENTIONS)
        text = render.render_next(HEAD, tables, date(2026, 10, 10), plain)
        self.assertIn("### Para hacer ya", text)
        self.assertIn("| PLATE-1 | Summary of PLATE-1 | High | 2026-10-05 | Backlog |", text)
        self.assertIn("### Vence hasta 2026-10-10", text)
        self.assertIn("| PLATE-1 | Summary of PLATE-1 | High | vencido 2026-10-05 | Backlog |", text)
        self.assertIn("Blocked (bloqueado)", text)
        self.assertIn("### Sin dueño en sus épicas (para tomar)", text)
        self.assertIn("| PLATE-7 | Summary of PLATE-7 | PLATE-100 | Medium |", text)

    def test_render_blocked_links_the_blocker_or_names_the_flag(self):
        rows = standup.blocked_rows([
            issue("PLATE-1", blocked_by=[{"key": "PLATE-8", "summary": "Okta", "status": "En curso", "category": "in_progress", "assignee": "Ana"}]),
            issue("PLATE-2", flagged=True)], CONVENTIONS)
        text = render.render_blocked(HEAD, rows, lambda k: f"<{k}>")
        self.assertIn("| Key | Título | Prioridad | Vence | Estado | Bloqueado por | Estado del bloqueador | Dueño del bloqueador |", text)
        self.assertIn("| <PLATE-1> | Summary of PLATE-1 | Medium | – | Backlog | <PLATE-8> Okta | En curso | Ana |", text)
        self.assertIn("| <PLATE-2> | Summary of PLATE-2 | Medium | – | Backlog | Flagged, sin link | – | – |", text)
        self.assertIn("_Nada bloqueado._", render.render_blocked(HEAD, [], plain))


class LoadAndStatsTest(unittest.TestCase):
    def numbers(self, **conv):
        return stats.load_numbers([issue("X", changed="2026-10-06")], [issue("A", category="in_progress")], TODAY, 2,
                                  dict(CONVENTIONS, **conv))

    def test_load_without_a_limit_gives_numbers_and_no_verdict(self):
        text = render.render_load(HEAD, "Ana Gómez", self.numbers())
        self.assertIn("| Métrica | Ana Gómez |", text)
        self.assertIn("| En curso (WIP) | 1 |", text)
        self.assertIn("| Cerrados por semana (viejo → nuevo; * = semana en curso) | 0 · 1* |", text)
        self.assertIn("Sin veredicto", text)

    def test_load_compares_side_by_side_and_gives_a_verdict_when_there_is_a_limit(self):
        text = render.render_load(HEAD, "Ana Gómez", self.numbers(wip_limit=3), "vos", self.numbers())
        self.assertIn("| Métrica | Ana Gómez | vos |", text)
        self.assertIn("| En curso (WIP) | 1 | 1 |", text)
        self.assertIn("**Ana Gómez:** WIP 1/3 → tiene espacio para 2 más", text)
        self.assertIn("sin espacio", render.render_load(HEAD, "Ana", self.numbers(wip_limit=1)))

    def test_render_stats_reports_n_and_warns_when_it_is_small(self):
        done = [issue("A", created="2026-10-01", resolved="2026-10-04", duedate="2026-10-05", changed="2026-10-04", summary="[BE] x")]
        s = stats.compute(done, [issue("B", category="in_progress", changed="2026-09-20", created="2026-08-01")], TODAY, 2, CONVENTIONS)
        text = render.render_stats(HEAD, s, plain)
        self.assertIn("n=1 · mediana 3 d · p85 3 d · pocos casos", text)
        self.assertIn("1/1 a tiempo (100%)", text)
        self.assertIn("estancado", text)
        self.assertIn("| BE | 1 |", text)

    def test_render_stats_with_nothing_says_so(self):
        text = render.render_stats(HEAD, stats.compute([], [], TODAY, 2, CONVENTIONS), plain)
        self.assertIn("Sin cierres en el período", text)
        self.assertIn("Ninguno de lo cerrado tenía fecha de vencimiento", text)
        self.assertIn("_Nada en curso._", text)


if __name__ == "__main__":
    unittest.main()
