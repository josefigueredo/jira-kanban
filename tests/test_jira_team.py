"""The two reads the team reports add to the Jira client: a capped search and the size of a group."""
from __future__ import annotations

import io
import unittest
import urllib.error

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import jira as jira_mod
from jkan.jira import JiraError
from test_jira import FIELDS, client


def raw(n: int, updated: str = "2026-10-07T10:00:00.000-0300") -> dict:
    return {"key": f"UA-{n}", "fields": {"summary": f"s{n}", "issuetype": {"name": "Tarea"}, "updated": updated,
                                         "status": {"id": "7", "name": "Review",
                                                    "statusCategory": {"key": "indeterminate"}}}}


def pages_of(*sizes, last_token=None):
    """Result pages with the given number of issues; every page but the last carries a next-page token."""
    out, n = [], 0
    for k, size in enumerate(sizes):
        page = {"issues": [raw(n + i) for i in range(size)]}
        n += size
        if k < len(sizes) - 1 or last_token:
            page["nextPageToken"] = f"t{k}"
        out.append(page)
    return out


class SearchCappedTest(unittest.TestCase):
    def search(self, pages, cap):
        jira, rec = client({("POST", "/rest/api/3/search/jql"): lambda body: pages.pop(0), ("GET", "/rest/api/3/field"): FIELDS})
        return jira.search_capped("project = UA", cap), rec

    def test_it_stops_at_the_cap_and_says_there_was_more(self):
        (found, more), rec = self.search(pages_of(100, 100, 100), 150)
        self.assertEqual((len(found), more), (150, True))
        self.assertEqual(len([c for c in rec.calls if c[0] == "POST"]), 2)  # the third page is never asked for

    def test_fewer_results_than_the_cap_are_all_returned_and_nothing_is_missing(self):
        (found, more), _ = self.search(pages_of(3), 10)
        self.assertEqual((len(found), more), (3, False))

    def test_exactly_the_cap_with_nothing_after_it_is_not_a_truncation(self):
        (found, more), _ = self.search(pages_of(5), 5)
        self.assertEqual((len(found), more), (5, False))

    def test_exactly_the_cap_with_a_next_page_is_a_truncation(self):
        (found, more), _ = self.search(pages_of(5, last_token="more"), 5)
        self.assertEqual((len(found), more), (5, True))

    def test_the_plain_search_still_returns_everything(self):
        jira, _ = client({("POST", "/rest/api/3/search/jql"): lambda body, p=pages_of(2, 2): p.pop(0),
                          ("GET", "/rest/api/3/field"): FIELDS})
        self.assertEqual(len(jira.search("project = UA")), 4)

    def test_issues_carry_the_day_they_were_last_updated(self):
        (found, _), _ = self.search(pages_of(1), 10)
        self.assertEqual(found[0]["updated"], "2026-10-07")


class GroupTotalTest(unittest.TestCase):
    def test_it_returns_how_many_members_the_group_has_and_encodes_the_name(self):
        jira, rec = client({("GET", "/rest/api/3/group/member"): {"total": 7, "values": []}})
        self.assertEqual(jira.group_total("team"), 7)
        self.assertIn("groupname=team", rec.calls[0][1])
        self.assertIn("maxResults=1", rec.calls[0][1])

    def test_an_unknown_group_is_a_jira_error_with_the_status(self):
        def missing(request, timeout=None):
            error = urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b'{"errorMessages":["no group"]}'))
            self.addCleanup(error.close)
            raise error

        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=missing)
        with self.assertRaisesRegex(JiraError, "HTTP 404"):
            jira.group_total("nope")


if __name__ == "__main__":
    unittest.main()
