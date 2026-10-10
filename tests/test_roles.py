from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import roles


def status(name, category, ident="1"):
    return {"id": ident, "name": name, "category": category}


PROFILES = {"GDNC": {"statuses": [{"id": "22", "name": "Done", "role": "delivered"},
                                  {"id": "25", "name": "ON HOLD", "role": None}]}}


class NormalizeTest(unittest.TestCase):
    def test_accents_case_and_punctuation_do_not_matter(self):
        self.assertEqual(roles.normalize("  Pend. Finalización "), "pend finalizacion")
        self.assertEqual(roles.normalize("NOT-APPROVED"), "not approved")
        self.assertEqual(roles.normalize(None), "")


class ProposeTest(unittest.TestCase):
    def test_a_known_name_in_the_category_it_belongs_to_is_proposed_with_confidence(self):
        cases = [("Done", "done", "delivered"), ("FINALIZADO", "done", "delivered"),
                 ("Completado", "done", "delivered"), ("Resuelto", "done", "delivered"),
                 ("RELEASED", "done", "delivered"), ("Cancelado", "done", "dropped"),
                 ("NOT APPROVED", "done", "dropped"), ("No aplica", "done", "dropped"),
                 ("Blocked", "in_progress", "blocked"), ("Backlog", "todo", "todo"),
                 ("PROCESANDO", "in_progress", "active"), ("Verificación solicitante", "in_progress", "active")]
        for name, category, role in cases:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"], p["mismatch"]), (role, "alta", False), name)

    def test_a_known_name_in_the_wrong_category_needs_a_person(self):
        cases = [("Done", "in_progress", "delivered"), ("Finalizado", "todo", "delivered"),
                 ("Resuelto", "in_progress", "delivered"), ("Blocked", "done", "blocked")]
        for name, category, guess in cases:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"], p["suggest"], p["mismatch"]),
                             (None, "decidir", guess, True), name)

    def test_a_name_with_extra_words_is_never_decided_by_the_dictionary(self):
        for name, category in [("Finalizado con error", "done"), ("Finalizado sin completar", "done"),
                               ("FINALIZADO POR TIEMPO EXCEDIDO", "done"), ("Listo para entrega", "in_progress")]:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"], p["mismatch"]), (None, "decidir", False), name)

    def test_waiting_and_unknown_done_names_need_a_person(self):
        for name, category in [("ON HOLD", "in_progress"), ("Esperando por el cliente", "in_progress"),
                               ("AWAITING APPROVAL", "in_progress"), ("Pend. de firma", "in_progress"),
                               ("Ready to deploy", "done"), ("PRODUCCION", "done"), ("Implementado", "done")]:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"]), (None, "decidir"), name)

    def test_every_proposal_says_why(self):
        for name, category in [("Done", "done"), ("ON HOLD", "in_progress"), ("Backlog", "todo"), ("?", "weird")]:
            self.assertTrue(roles.propose(status(name, category))["why"], name)


class AnnotateTest(unittest.TestCase):
    def test_without_a_profile_the_category_decides(self):
        issues = roles.annotate([{"key": "PLATE-1", "category": "done"}, {"key": "PLATE-2", "category": "in_progress"},
                                 {"key": "PLATE-3", "category": "todo"}], {})
        self.assertEqual([(i["role"], i["role_source"]) for i in issues],
                         [("delivered", "category"), ("active", "category"), ("todo", "category")])

    def test_with_a_profile_the_status_id_decides_whatever_the_category_says(self):
        issue = {"key": "GDNC-1", "status": "Done", "status_id": "22", "category": "in_progress"}
        roles.annotate([issue], PROFILES)
        self.assertEqual((issue["role"], issue["role_source"]), ("delivered", "profile"))

    def test_an_undecided_or_unknown_status_has_no_role(self):
        undecided = {"key": "GDNC-2", "status_id": "25", "category": "in_progress"}
        unknown = {"key": "GDNC-3", "status_id": "99", "category": "done"}
        roles.annotate([undecided, unknown], PROFILES)
        self.assertEqual((undecided["role"], unknown["role"]), (None, None))

    def test_an_issue_without_a_status_id_is_unknown_to_the_profile_and_does_not_crash(self):
        issue = {"key": "GDNC-4", "status": "Nuevo", "category": "todo"}
        roles.annotate([issue], PROFILES)
        self.assertIsNone(issue["role"])
        self.assertEqual(roles.notes([issue], PROFILES),
                         ["Estado desconocido: Nuevo (GDNC). El workflow cambió; corré `jtk board check GDNC`."])

    def test_role_of_falls_back_to_the_category_for_an_issue_nobody_annotated(self):
        self.assertEqual(roles.role_of({"category": "done"}), "delivered")
        self.assertIsNone(roles.role_of({"category": ""}))
        self.assertEqual(roles.source_of({}), "category")

    def test_the_project_is_what_comes_before_the_number(self):
        self.assertEqual(roles.project_of("PLATE-12"), "PLATE")
        self.assertEqual(roles.project_of("AE_X-3"), "AE_X")


class NotesTest(unittest.TestCase):
    def test_a_clean_report_has_no_notes(self):
        self.assertEqual(roles.notes([{"key": "GDNC-1", "status_id": "22", "status": "Done"}], PROFILES), [])

    def test_projects_without_a_profile_are_named_once(self):
        issues = [{"key": "PLATE-1"}, {"key": "PLATE-2"}, {"key": "UA-1"}]
        self.assertEqual(roles.notes(issues, {}),
                         ["Sin perfil: PLATE, UA. Se usa la categoría de Jira; corré `jtk board setup KEY`."])

    def test_undecided_statuses_are_listed_by_project(self):
        notes = roles.notes([{"key": "GDNC-2", "status_id": "25", "status": "ON HOLD"}], PROFILES)
        self.assertEqual(notes, ["Perfil sin confirmar en GDNC: faltan decidir ON HOLD."])

    def test_a_profile_file_that_could_not_be_read_is_named_instead_of_reported_as_missing(self):
        issues = [{"key": "UA-1", "status_id": "1", "status": "To Do"}, {"key": "PEHD-1", "status_id": "1", "status": "x"}]
        problems = {"UA": ("bad", "UA.json is not a profile (wrong shape)"),
                    "PEHD": ("newer", "PEHD.json was written by a newer jtk (profile version 2); update jtk")}
        self.assertEqual(roles.notes(issues, {}, problems), [
            "Perfil de PEHD ilegible (PEHD.json was written by a newer jtk (profile version 2); update jtk): "
            "se usa la categoría de Jira; actualizá jtk.",
            "Perfil de UA ilegible (UA.json is not a profile (wrong shape)): se usa la categoría de Jira; "
            "corré `jtk board setup UA` para rehacerlo."])

    def test_a_status_the_profile_never_saw_is_reported_as_unknown(self):
        notes = roles.notes([{"key": "GDNC-3", "status_id": "99", "status": "Nuevo"}], PROFILES)
        self.assertEqual(notes, ["Estado desconocido: Nuevo (GDNC). El workflow cambió; corré `jtk board check GDNC`."])


if __name__ == "__main__":
    unittest.main()
