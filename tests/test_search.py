from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401
from test_jira import FIELDS, client

BLOCKER = {"key": "PLATE-5", "fields": {"summary": "Esperar a Okta", "status": {"name": "Blocked",
           "statusCategory": {"key": "indeterminate"}}, "assignee": {"displayName": "Ana Gómez"}}}
RAW = {"key": "PLATE-9", "fields": {
    "summary": "[BE] Algo", "issuetype": {"name": "Tarea"},
    "status": {"name": "PROCESANDO", "statusCategory": {"key": "indeterminate"}},
    "parent": {"key": "PLATE-1", "fields": {"summary": "Épica", "issuetype": {"name": "Epic"}}},
    "assignee": {"accountId": "acc-me", "displayName": "Yo"}, "priority": {"name": "High"},
    "duedate": "2026-10-10", "created": "2026-10-01T09:00:00.000-0300", "resolutiondate": None,
    "statuscategorychangedate": "2026-10-07T14:03:00.000-0300", "customfield_10023": [{"value": "Impediment"}],
    "issuelinks": [{"type": {"inward": "is blocked by"}, "inwardIssue": BLOCKER},
                   {"type": {"inward": "relates to"}, "inwardIssue": {"key": "PLATE-6", "fields": {}}},
                   {"type": {"inward": "is blocked by"}, "outwardIssue": {"key": "PLATE-7", "fields": {}}}]}}


class SearchTest(unittest.TestCase):
    def test_search_normalizes_an_issue_and_follows_the_pages(self):
        pages = [{"issues": [RAW], "nextPageToken": "n1"}, {"issues": [dict(RAW, key="PLATE-10")]}]
        jira, rec = client({("POST", "/rest/api/3/search/jql"): lambda body: pages.pop(0),
                            ("GET", "/rest/api/3/field"): FIELDS})
        found = jira.search("assignee = currentUser()")
        self.assertEqual([i["key"] for i in found], ["PLATE-9", "PLATE-10"])
        self.assertEqual(found[0], {
            "key": "PLATE-9", "summary": "[BE] Algo", "issuetype": "Tarea", "status": "PROCESANDO",
            "category": "in_progress", "parent": {"key": "PLATE-1", "summary": "Épica", "issuetype": "Epic"},
            "assignee": {"id": "acc-me", "name": "Yo"}, "priority": "High", "duedate": "2026-10-10",
            "created": "2026-10-01", "resolved": None, "changed": "2026-10-07", "flagged": True,
            "blocked_by": [{"key": "PLATE-5", "summary": "Esperar a Okta", "status": "Blocked",
                            "category": "in_progress", "assignee": "Ana Gómez"}]})
        posts = [c for c in rec.calls if c[0] == "POST"]
        self.assertEqual(posts[0][2]["jql"], "assignee = currentUser()")
        self.assertIn("statuscategorychangedate", posts[0][2]["fields"])
        self.assertIn("customfield_10023", posts[0][2]["fields"])
        self.assertEqual(posts[1][2]["nextPageToken"], "n1")

    def test_search_survives_an_issue_with_nothing_optional(self):
        bare = {"key": "PLATE-2", "fields": {"summary": "x", "status": {"name": "Backlog",
                "statusCategory": {"key": "new"}}, "issuelinks": [{"type": {"inward": "is blocked by"},
                "inwardIssue": {"key": "PLATE-3"}}]}}
        jira, _ = client({("POST", "/rest/api/3/search/jql"): {"issues": [bare]}, ("GET", "/rest/api/3/field"): FIELDS})
        issue = jira.search("x")[0]
        self.assertIsNone(issue["parent"])
        self.assertIsNone(issue["assignee"])
        self.assertEqual(issue["priority"], "")
        self.assertFalse(issue["flagged"])
        self.assertEqual(issue["blocked_by"], [{"key": "PLATE-3", "summary": "", "status": "", "category": "",
                                                "assignee": ""}])

    def test_search_uses_the_link_text_it_is_told_to(self):
        jira, _ = client({("POST", "/rest/api/3/search/jql"): {"issues": [RAW]}, ("GET", "/rest/api/3/field"): FIELDS})
        self.assertEqual(jira.search("x", blocked_link="relates to")[0]["blocked_by"][0]["key"], "PLATE-6")


if __name__ == "__main__":
    unittest.main()
