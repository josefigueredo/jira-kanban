from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from jkan import approval

SUMMARY = approval.Summary("TEXT", "Plan abc · move · 2 issue(s)",
                           [("TEAM-1", "Migrar <b>el</b> login & más", "Backlog -> En curso"),
                            ("TEAM-2", "", "Backlog -> En curso")],
                           [("TEAM-3", "already there")])


class Done:
    def __init__(self, code=0, out="approved"):
        self.returncode, self.stdout = code, out


def approver(result=None, boom=None, seen=None):
    def runner(argv):
        if seen is not None:
            seen.append(argv)
        if boom:
            raise boom
        return result or Done()
    return approval.DialogApprover(runner=runner, platform="darwin")


class SummaryTest(unittest.TestCase):
    def test_it_is_a_plain_string_for_the_terminal_and_carries_the_rows(self):
        self.assertEqual(str(SUMMARY), "TEXT")
        self.assertEqual(SUMMARY.rows[0][0], "TEAM-1")
        self.assertEqual(SUMMARY.left_out, [("TEAM-3", "already there")])

    def test_it_does_not_shadow_the_methods_of_str(self):
        self.assertEqual(SUMMARY.title(), "Text")
        self.assertEqual(SUMMARY.heading, "Plan abc · move · 2 issue(s)")

    def test_a_plain_string_has_no_rows(self):
        self.assertEqual(approval.rows_of("just text"), [])


class HtmlTest(unittest.TestCase):
    def test_it_shows_every_change_and_what_was_left_out(self):
        html = approval.render_html(SUMMARY, 2)
        for part in ("TEAM-1", "TEAM-2", "Backlog", "En curso", "TEAM-3", "already there"):
            self.assertIn(part, html)

    def test_the_page_carries_its_own_header_so_the_window_is_just_this_page_and_two_buttons(self):
        html = approval.render_html(SUMMARY, 2)
        self.assertIn("jtk quiere escribir en Jira", html)
        self.assertIn("<h1>Plan abc · move · 2 issue(s)</h1>", html)

    def test_each_task_is_a_card_with_its_key_chip_and_the_change_as_from_arrow_to(self):
        html = approval.render_html(SUMMARY, 2)
        self.assertEqual(html.count('class="card"'), 2)
        self.assertEqual(html.count('class="key"'), 3)  # two cards and the left-out one
        self.assertIn('<span class="from">Backlog</span><span class="arrow">→</span><span class="to">En curso</span>', html)
        self.assertNotIn("-&gt;", html)

    def test_a_change_with_no_origin_shows_only_the_destination(self):
        summary = approval.Summary("T", "Asignar", [("A-1", "x", "-> Ana Gómez")])
        html = approval.render_html(summary, 1)
        self.assertIn('<span class="to">Ana Gómez</span>', html)
        self.assertNotIn('class="from"', html)

    def test_the_footer_says_which_button_and_how_long_the_window_waits(self):
        html = approval.render_html(SUMMARY, 2)
        self.assertIn("Apruebo 2", html)
        self.assertIn(f"{approval.TIMEOUT} s", html)

    def test_the_page_has_no_script_and_no_external_resource(self):
        html = approval.render_html(SUMMARY, 2).lower()
        for part in ("<script", "http://", "https://", "<link", "<img", "<iframe"):
            self.assertNotIn(part, html)

    def test_jira_text_is_escaped_so_a_hostile_title_cannot_become_markup(self):
        html = approval.render_html(SUMMARY, 2)
        self.assertNotIn("<b>el</b>", html)
        self.assertIn("&lt;b&gt;el&lt;/b&gt; login &amp; más", html)

    def test_the_height_grows_with_the_plan_and_stays_between_a_floor_and_a_cap(self):
        one = approval.Summary("T", "h", [("A-1", "x", "a -> b")])
        many = approval.Summary("T", "h", [(f"A-{i}", "x" * 120, "a -> b") for i in range(30)], [("A-9", "r")])
        self.assertEqual(approval.window_height(one), 240)
        self.assertEqual(approval.window_height(many), 560)
        self.assertGreater(approval.window_height(SUMMARY), approval.window_height(one))

    def test_a_plain_summary_without_rows_shows_its_text(self):
        html = approval.render_html("create 3 issue(s) in PLATE", 3)
        self.assertIn("create 3 issue(s) in PLATE", html)


class ApproveTest(unittest.TestCase):
    def test_only_a_clean_exit_with_approved_counts(self):
        self.assertTrue(approver().approve(SUMMARY, 2))

    def test_a_person_who_did_not_click_approve_is_a_refusal(self):
        for result in (Done(0, "cancelled"), Done(0, ""), Done(0, "approved extra")):
            self.assertFalse(approver(result).approve(SUMMARY, 2), result.stdout)
        self.assertFalse(approver(boom=subprocess.TimeoutExpired("osascript", 100)).approve(SUMMARY, 2))

    def test_a_window_that_could_not_start_is_not_a_refusal_by_the_person(self):
        for result in (Done(1, "approved"), Done(2, ""), Done(1, "")):
            with self.assertRaises(approval.Unavailable, msg=result.stdout):
                approver(result).approve(SUMMARY, 2)
        with self.assertRaises(approval.Unavailable):
            approver(boom=OSError("no osascript")).approve(SUMMARY, 2)

    def test_it_runs_the_absolute_osascript_with_the_button_label_and_a_timeout_under_cursors(self):
        seen = []
        approver(seen=seen).approve(SUMMARY, 3)
        argv = seen[0]
        self.assertEqual(argv[:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        self.assertEqual(Path(argv[3]).name, "alert.js")
        self.assertEqual(argv[6], "Apruebo 3")
        self.assertEqual(argv[7], str(approval.window_height(SUMMARY)))
        self.assertLess(approval.TIMEOUT, 120)

    def test_the_temporary_html_exists_while_the_window_runs_is_private_and_is_removed_after(self):
        folder = Path(tempfile.mkdtemp(prefix="jtk-approval-test-"))
        during = []

        def runner(argv):  # argv: osascript -l JavaScript alert.js <html> <title> <label> <height>
            html = Path(argv[4])
            during.append((html.exists(), oct(html.stat().st_mode & 0o777)))
            return Done()

        approval.DialogApprover(runner=runner, platform="darwin", plans_dir=folder).approve(SUMMARY, 2)
        self.assertEqual(during, [(True, "0o600")])
        self.assertEqual(list(folder.iterdir()), [])

        def boom(argv):
            raise OSError("the window could not start")

        with self.assertRaises(approval.Unavailable):
            approval.DialogApprover(runner=boom, platform="darwin", plans_dir=folder).approve(SUMMARY, 2)
        self.assertEqual(list(folder.iterdir()), [])

    def test_it_is_not_available_outside_macos(self):
        self.assertFalse(approval.available(platform="linux"))
        self.assertFalse(approval.available(platform="darwin", osascript="/nonexistent/osascript"))


class AlertScriptTest(unittest.TestCase):
    """The window itself is checked by hand; these pin the settings that make approval a deliberate click."""

    def setUp(self):
        self.js = (ROOT / "jkan" / "alert.js").read_text(encoding="utf-8")

    def test_the_window_is_our_own_panel_around_a_web_view_not_an_nsalert(self):
        self.assertIn("NSPanel", self.js)
        self.assertIn("WKWebView", self.js)
        self.assertNotIn("NSAlert", self.js)

    def test_the_page_runs_no_javascript(self):
        self.assertIn("allowsContentJavaScript = false", self.js)

    def test_cancel_is_first_and_escape_is_bound_to_it(self):
        self.assertLess(self.js.index("'Cancelar'"), self.js.index("argv[2]"))
        self.assertIn("cancel.keyEquivalent = '\\u001b'", self.js)

    def test_nothing_gives_return_to_a_button(self):
        self.assertNotIn("defaultButtonCell", self.js)
        self.assertNotIn("\\r", self.js)

    def test_the_approve_button_has_no_key_equivalent_so_it_takes_a_click(self):
        self.assertIn("ok.keyEquivalent = ''", self.js)

    def test_the_result_is_cancelled_unless_the_approve_button_sets_it(self):
        self.assertIn("let result = 'cancelled'", self.js)
        self.assertEqual(self.js.count("result = 'approved'"), 1)
        self.assertIn("windowWillClose", self.js)  # the red close button is a cancel too

    def test_the_height_comes_from_python_and_the_page_scrolls_past_it(self):
        self.assertIn("Number(argv[3])", self.js)


if __name__ == "__main__":
    unittest.main()
