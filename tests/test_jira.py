from __future__ import annotations

import io
import json
import unittest
import urllib.error

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import jira as jira_mod


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """An opener that answers by (method, path) and records every request."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, request, timeout=None):
        path = request.full_url.split("example.atlassian.net", 1)[1]
        body = json.loads(request.data.decode()) if request.data else None
        self.calls.append((request.get_method(), path, body))
        answer = self.answers[(request.get_method(), path.split("?", 1)[0])]
        return FakeResponse(json.dumps(answer(body) if callable(answer) else answer).encode())


def client(answers):
    rec = Recorder(answers)
    return jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec), rec


ISSUE_V2 = {"key": "PLATE-1", "fields": {"summary": "S", "description": "D", "issuetype": {"name": "Tarea"},
                                         "status": {"name": "Backlog", "statusCategory": {"key": "new"}},
                                         "parent": {"key": "PLATE-0"}, "customfield_10023": [{"value": "Impediment"}]}}
FIELDS = [{"id": "customfield_10023", "name": "Flagged"}, {"id": "summary", "name": "Summary"}]


class JiraTest(unittest.TestCase):
    def test_get_normalizes_a_v2_issue_with_category_and_flag(self):
        jira, _ = client({("GET", "/rest/api/2/issue/PLATE-1"): ISSUE_V2, ("GET", "/rest/api/3/field"): FIELDS})
        self.assertEqual(jira.get("PLATE-1"), {"key": "PLATE-1", "summary": "S", "description": "D",
                                               "issuetype": "Tarea", "status": "Backlog", "parent": "PLATE-0",
                                               "category": "todo", "flagged": True})

    def test_create_posts_v2_fields_and_returns_the_key(self):
        jira, rec = client({("POST", "/rest/api/2/issue"): {"key": "PLATE-7"}})
        self.assertEqual(jira.create({"summary": "x"}), "PLATE-7")
        self.assertEqual(rec.calls[0][2], {"fields": {"summary": "x"}})

    def test_children_follow_the_search_pages(self):
        pages = [{"issues": [{"key": "PLATE-2"}], "nextPageToken": "n1"}, {"issues": [{"key": "PLATE-3"}]}]
        jira, rec = client({("POST", "/rest/api/3/search/jql"): lambda body: pages.pop(0),
                            ("GET", "/rest/api/3/field"): FIELDS,
                            ("GET", "/rest/api/2/issue/PLATE-2"): dict(ISSUE_V2, key="PLATE-2"),
                            ("GET", "/rest/api/2/issue/PLATE-3"): dict(ISSUE_V2, key="PLATE-3")})
        self.assertEqual([c["key"] for c in jira.children("PLATE-0")], ["PLATE-2", "PLATE-3"])
        self.assertEqual(rec.calls[0][2]["jql"], "parent = PLATE-0 ORDER BY key")
        self.assertEqual(rec.calls[1][2]["nextPageToken"], "n1")

    def test_transition_picks_by_destination_status(self):
        transitions = {"transitions": [{"id": "11", "name": "Start", "to": {"name": "En curso"}},
                                        {"id": "31", "name": "Finish", "to": {"name": "Done"}}]}
        jira, rec = client({("GET", "/rest/api/3/issue/PLATE-1/transitions"): transitions,
                            ("POST", "/rest/api/3/issue/PLATE-1/transitions"): {}})
        self.assertTrue(jira.transition("PLATE-1", "done"))
        self.assertEqual(rec.calls[-1][2], {"transition": {"id": "31"}})
        jira2, _ = client({("GET", "/rest/api/3/issue/PLATE-1/transitions"): transitions})
        self.assertFalse(jira2.transition("PLATE-1", "Archivado"))


def person(account_id, name, email="", active=True, kind="atlassian"):
    return {"accountId": account_id, "displayName": name, "emailAddress": email, "active": active, "accountType": kind}


class JiraPeopleTest(unittest.TestCase):
    def test_search_users_asks_for_people_assignable_in_the_project_and_keeps_only_active_humans(self):
        page = [person("a1", "Ana Gomez", "ana@x.com"), person("b2", "Ex Employee", "ex@x.com", active=False),
                person("c3", "Automation", "", kind="app")]
        jira, rec = client({("GET", "/rest/api/3/user/assignable/search"): page})
        self.assertEqual(jira.search_users("Ana", "PLATE"), [{"id": "a1", "name": "Ana Gomez", "email": "ana@x.com"}])
        method, path, _ = rec.calls[0]
        self.assertIn("project=PLATE", path)
        self.assertIn("query=Ana", path)

    def test_search_users_without_a_project_uses_the_general_search(self):
        jira, rec = client({("GET", "/rest/api/3/user/search"): [person("a1", "Ana Gomez", "ana@x.com")]})
        jira.search_users("Ana")
        self.assertTrue(rec.calls[0][1].startswith("/rest/api/3/user/search"))

    def test_search_users_pages_until_a_short_page_and_stops_at_the_limit(self):
        pages = [[person("a1", "A One"), person("a2", "A Two")], [person("a3", "A Three")]]
        jira, rec = client({("GET", "/rest/api/3/user/assignable/search"): lambda body: pages.pop(0)})
        found = jira.search_users("A", "PLATE", page=2)
        self.assertEqual([u["id"] for u in found], ["a1", "a2", "a3"])
        self.assertIn("startAt=0", rec.calls[0][1])
        self.assertIn("startAt=2", rec.calls[1][1])
        pages = [[person("a1", "A One"), person("a2", "A Two")], [person("a3", "A Three"), person("a4", "A Four")]]
        jira, _ = client({("GET", "/rest/api/3/user/assignable/search"): lambda body: pages.pop(0)})
        self.assertEqual(len(jira.search_users("A", "PLATE", limit=3, page=2)), 3)

    def test_user_returns_the_person_for_an_account_id(self):
        jira, rec = client({("GET", "/rest/api/3/user"): person("a1", "Ana Gomez", "ana@x.com")})
        self.assertEqual(jira.user("a1"), {"id": "a1", "name": "Ana Gomez", "email": "ana@x.com"})
        self.assertIn("accountId=a1", rec.calls[0][1])

    def test_user_is_none_when_jira_does_not_know_the_id(self):
        def missing(request, timeout=None):
            error = urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))
            self.addCleanup(error.close)
            raise error

        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=missing)
        self.assertIsNone(jira.user("Fernandez"))

    def test_assign_sets_the_assignee_and_is_journaled(self):
        seen = []
        rec = Recorder({("PUT", "/rest/api/3/issue/PLATE-5/assignee"): {}})
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=seen.append)
        jira.assign("PLATE-5", "a1")
        self.assertEqual(rec.calls[0], ("PUT", "/rest/api/3/issue/PLATE-5/assignee", {"accountId": "a1"}))
        self.assertEqual(seen, [{"action": "assign", "key": "PLATE-5", "accountId": "a1"}])


if __name__ == "__main__":
    unittest.main()
