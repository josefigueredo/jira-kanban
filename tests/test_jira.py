from __future__ import annotations

import io
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
