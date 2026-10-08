from __future__ import annotations

import unittest

from helpers import FakeJira
from jkan import people


def ids(result):
    return [c["id"] for c in result["candidates"]]


class FoldTest(unittest.TestCase):
    def test_fold_drops_accents_and_case(self):
        self.assertEqual(people.fold("Matías ANDRÉS"), "matias andres")


class FindTest(unittest.TestCase):
    def test_a_name_without_accents_finds_the_person_with_accents(self):
        result = people.find(FakeJira(), "Matias Andres Fernandez", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-matias"])

    def test_a_typo_still_finds_the_person_even_though_jira_search_finds_nobody(self):
        jira = FakeJira()
        self.assertEqual(jira.search_users("Matiaz"), [])  # why searching the whole name is not enough
        result = people.find(jira, "Matiaz Andres Fernandez", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-matias"])

    def test_it_searches_each_word_not_only_the_whole_name(self):
        jira = FakeJira()
        people.find(jira, "Matiaz Andres Fernandez", "PLATE")
        self.assertIn("andres", [q.lower() for q in jira.searches])
        self.assertIn("fernandez", [q.lower() for q in jira.searches])

    def test_two_people_with_every_word_are_ambiguous_and_both_are_listed(self):
        result = people.find(FakeJira(), "Martin Fernandez", "PLATE")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(set(ids(result)), {"acc-martin-d", "acc-martin-l"})

    def test_a_surname_alone_is_ambiguous_and_lists_everyone_with_it(self):
        result = people.find(FakeJira(), "Fernandez", "PLATE")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(set(ids(result)), {"acc-matias", "acc-martin-d", "acc-martin-l", "acc-maria"})

    def test_the_exact_full_name_wins_over_a_longer_name_that_contains_it(self):
        result = people.find(FakeJira(), "Martin Daniel Fernandez", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-martin-d"])

    def test_nobody_resembling_the_name_is_none(self):
        result = people.find(FakeJira(), "Zzzz Qqqq", "PLATE")
        self.assertEqual(result["status"], "none")
        self.assertEqual(result["candidates"], [])

    def test_an_email_finds_that_person(self):
        result = people.find(FakeJira(), "ana.gomez@example.com", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-ana"])

    def test_an_account_id_finds_that_person_without_searching_by_name(self):
        jira = FakeJira()
        result = people.find(jira, "acc-ana", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-ana"])
        self.assertEqual(jira.searches, [])

    def test_candidates_carry_name_and_email_so_a_person_can_tell_them_apart(self):
        result = people.find(FakeJira(), "Martin Fernandez", "PLATE")
        self.assertTrue(all(c["name"] and c["email"] for c in result["candidates"]))


class ExactnessTest(unittest.TestCase):
    """A one-letter slip is forgiven, so a fuzzy match must never look as certain as an exact one."""

    MARIO = [{"id": "acc-mario", "name": "Mario Fernandez", "email": "mario@example.com"}]

    def test_every_word_spelled_right_is_exact(self):
        result = people.find(FakeJira(), "Matias Andres Fernandez", "PLATE")
        self.assertTrue(result["candidates"][0]["exact"])

    def test_a_forgiven_typo_is_a_unique_match_but_not_exact(self):
        result = people.find(FakeJira(), "Matiaz Andres Fernandez", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertFalse(result["candidates"][0]["exact"])

    def test_maria_does_not_become_mario_without_saying_it_is_approximate(self):
        result = people.find(FakeJira(users=self.MARIO), "Maria Fernandez", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-mario"])
        self.assertFalse(result["candidates"][0]["exact"])

    def test_the_exactly_spelled_person_beats_a_near_miss(self):
        everyone = self.MARIO + [{"id": "acc-maria", "name": "María Fernández", "email": "maria@example.com"}]
        result = people.find(FakeJira(users=everyone), "Maria Fernandez", "PLATE")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(ids(result), ["acc-maria"])
        self.assertTrue(result["candidates"][0]["exact"])

    def test_two_exact_people_stay_ambiguous_even_with_a_near_miss_around(self):
        everyone = FakeJira().users + self.MARIO
        result = people.find(FakeJira(users=everyone), "Martin Fernandez", "PLATE")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(set(ids(result)), {"acc-martin-d", "acc-martin-l"})

    def test_an_email_or_account_id_is_exact(self):
        self.assertTrue(people.find(FakeJira(), "ana.gomez@example.com", "PLATE")["candidates"][0]["exact"])
        self.assertTrue(people.find(FakeJira(), "acc-ana", "PLATE")["candidates"][0]["exact"])

    def test_resolve_keeps_the_flag_on_the_person(self):
        self.assertFalse(people.resolve(FakeJira(users=self.MARIO), "Maria Fernandez", "PLATE")["exact"])


class ResolveTest(unittest.TestCase):
    def test_a_unique_match_returns_the_person(self):
        person = people.resolve(FakeJira(), "Matias Andres Fernandez", "PLATE")
        self.assertEqual(person["id"], "acc-matias")
        self.assertEqual(person["name"], "Matías Andrés Fernandez")

    def test_an_ambiguous_name_raises_listing_names_and_emails_and_never_guesses(self):
        with self.assertRaises(people.NotResolved) as raised:
            people.resolve(FakeJira(), "Martin Fernandez", "PLATE")
        message = str(raised.exception)
        self.assertIn("Martin Daniel Fernandez", message)
        self.assertIn("martin.lopez@example.com", message)
        self.assertIn("email", message)

    def test_an_unknown_name_raises_saying_nobody_matched(self):
        with self.assertRaises(people.NotResolved) as raised:
            people.resolve(FakeJira(), "Zzzz Qqqq", "PLATE")
        self.assertIn("Zzzz Qqqq", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
