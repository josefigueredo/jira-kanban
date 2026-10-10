from __future__ import annotations

import unittest

import plan_fixtures as pf
import team_fixtures as fx
from helpers import FailingJira, FakeJira
from jkan import jira as jira_mod
from test_jira import Recorder, client

TRANSITIONS = {"transitions": [
    {"id": "21", "name": "Start", "to": {"id": "10115", "name": "PROCESANDO"}, "fields": {}},
    {"id": "31", "name": "Close", "to": {"id": "10116", "name": "Done"},
     "fields": {"resolution": {"required": True, "hasDefaultValue": False},
                "assignee": {"required": True, "hasDefaultValue": True},
                "comment": {"required": False, "hasDefaultValue": False}}}]}


class RealJiraTest(unittest.TestCase):
    def test_transitions_say_where_each_one_goes_and_what_it_requires(self):
        jira, rec = client({("GET", "/rest/api/3/issue/PLATE-1/transitions"): TRANSITIONS})
        found = jira.transitions("PLATE-1")
        self.assertEqual(found, [
            {"id": "21", "name": "Start", "to": {"id": "10115", "name": "PROCESANDO"}, "required": []},
            {"id": "31", "name": "Close", "to": {"id": "10116", "name": "Done"}, "required": ["resolution"]}])
        self.assertEqual(rec.calls[0][0], "GET")
        self.assertIn("expand=transitions.fields", rec.calls[0][1])

    def test_a_transition_is_posted_by_its_id_and_journaled(self):
        log = []
        rec = Recorder({("POST", "/rest/api/3/issue/PLATE-1/transitions"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        jira.transition_by_id("PLATE-1", "21")
        self.assertEqual(rec.calls[0], ("POST", "/rest/api/3/issue/PLATE-1/transitions", {"transition": {"id": "21"}}))
        self.assertEqual(log, [{"action": "transition", "key": "PLATE-1", "transition": "21"}])

    def test_a_comment_is_plain_text_on_the_v2_endpoint(self):
        log = []
        rec = Recorder({("POST", "/rest/api/2/issue/PLATE-1/comment"): {"id": "1"}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        jira.add_comment("PLATE-1", "hola")
        self.assertEqual(rec.calls[0], ("POST", "/rest/api/2/issue/PLATE-1/comment", {"body": "hola"}))
        self.assertEqual(log, [{"action": "comment", "key": "PLATE-1"}])

    def test_the_snapshot_is_only_the_status_id_and_the_owner(self):
        owned = {"fields": {"status": {"id": 10115, "name": "PROCESANDO"},
                            "assignee": {"accountId": "acc-ana", "displayName": "Ana Gómez"}}}
        free = {"fields": {"status": {"id": "10041", "name": "Backlog"}, "assignee": None}}
        jira, rec = client({("GET", "/rest/api/3/issue/PLATE-1"): owned, ("GET", "/rest/api/3/issue/PLATE-2"): free})
        self.assertEqual(jira.snapshot("PLATE-1"), {"status_id": "10115", "status": "PROCESANDO",
                                                    "assignee": {"id": "acc-ana", "name": "Ana Gómez"}})
        self.assertEqual(jira.snapshot("PLATE-2"), {"status_id": "10041", "status": "Backlog", "assignee": None})
        self.assertIn("fields=status,assignee", rec.calls[0][1])

    def test_assigning_nobody_unassigns(self):
        rec = Recorder({("PUT", "/rest/api/3/issue/PLATE-1/assignee"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec)
        jira.assign("PLATE-1", None)
        self.assertEqual(rec.calls[0][2], {"accountId": None})


class FakeJiraTest(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()
        pf.workflow(self.jira, required={"1>6": ["resolution"]})
        pf.put(self.jira, "TEAM-1", "todo")

    def test_it_lists_the_transitions_that_leave_the_current_status(self):
        found = {t["id"]: t for t in self.jira.transitions("TEAM-1")}
        self.assertEqual(sorted(found), ["1>2", "1>3", "1>4", "1>5", "1>6"])
        self.assertEqual(found["1>6"]["required"], ["resolution"])
        self.assertEqual(found["1>2"]["to"], {"id": "2", "name": "En curso"})

    def test_a_transition_moves_the_issue_and_is_recorded_as_a_write(self):
        self.jira.transition_by_id("TEAM-1", "1>2")
        self.assertEqual(self.jira.snapshot("TEAM-1")["status_id"], "2")
        self.assertEqual(self.jira.writes, [("transition_id", "TEAM-1", "1>2")])

    def test_a_transition_that_does_not_leave_the_current_status_is_refused(self):
        with self.assertRaises(FailingJira):
            self.jira.transition_by_id("TEAM-1", "2>3")
        self.assertEqual(self.jira.writes, [])

    def test_assign_and_comment_show_up_in_the_snapshot_and_the_writes(self):
        self.jira.assign("TEAM-1", "acc-ana")
        self.jira.add_comment("TEAM-1", "hola")
        self.assertEqual(self.jira.snapshot("TEAM-1")["assignee"], {"id": "acc-ana", "name": "Ana Gómez"})
        self.assertEqual(self.jira.writes, [("assign", "TEAM-1", "acc-ana"), ("comment", "TEAM-1", "hola")])
        self.jira.assign("TEAM-1", None)
        self.assertIsNone(self.jira.snapshot("TEAM-1")["assignee"])

    def test_an_issue_marked_to_fail_raises_on_every_kind_of_write(self):
        self.jira.fail_writes.add("TEAM-1")
        for call in (lambda: self.jira.transition_by_id("TEAM-1", "1>2"), lambda: self.jira.assign("TEAM-1", "acc-ana"),
                     lambda: self.jira.add_comment("TEAM-1", "x")):
            with self.assertRaises(FailingJira):
                call()
        self.assertEqual(self.jira.writes, [])

    def test_the_fixture_issue_looks_like_a_search_result(self):
        issue = pf.put(self.jira, "TEAM-2", "active", fx.ANA)
        self.assertEqual((issue["key"], issue["status_id"], issue["role"], issue["assignee"]),
                         ("TEAM-2", "2", "active", fx.ANA))


if __name__ == "__main__":
    unittest.main()
