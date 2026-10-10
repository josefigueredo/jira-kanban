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
        for part in ("TEAM-1", "TEAM-2", "Backlog -&gt; En curso", "TEAM-3", "already there", "Plan abc"):
            self.assertIn(part, html)

    def test_jira_text_is_escaped_so_a_hostile_title_cannot_become_markup(self):
        html = approval.render_html(SUMMARY, 2)
        self.assertNotIn("<b>el</b>", html)
        self.assertIn("&lt;b&gt;el&lt;/b&gt; login &amp; más", html)

    def test_a_plain_summary_without_rows_shows_its_text(self):
        html = approval.render_html("create 3 issue(s) in PLATE", 3)
        self.assertIn("create 3 issue(s) in PLATE", html)


class ApproveTest(unittest.TestCase):
    def test_only_a_clean_exit_with_approved_counts(self):
        self.assertTrue(approver().approve(SUMMARY, 2))

    def test_everything_else_is_a_refusal(self):
        for result in (Done(0, "cancelled"), Done(0, ""), Done(1, "approved"), Done(0, "approved extra"), Done(2, "")):
            self.assertFalse(approver(result).approve(SUMMARY, 2), result.stdout)
        self.assertFalse(approver(boom=OSError("no osascript")).approve(SUMMARY, 2))
        self.assertFalse(approver(boom=subprocess.TimeoutExpired("osascript", 100)).approve(SUMMARY, 2))

    def test_it_runs_the_absolute_osascript_with_the_button_label_and_a_timeout_under_cursors(self):
        seen = []
        approver(seen=seen).approve(SUMMARY, 3)
        argv = seen[0]
        self.assertEqual(argv[:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        self.assertEqual(Path(argv[3]).name, "alert.js")
        self.assertEqual(argv[7], "Apruebo 3")
        self.assertLess(approval.TIMEOUT, 120)

    def test_the_temporary_html_exists_while_the_window_runs_is_private_and_is_removed_after(self):
        folder = Path(tempfile.mkdtemp(prefix="jtk-approval-test-"))
        during = []

        def runner(argv):  # argv: osascript -l JavaScript alert.js <html> <title> <info> <label>
            html = Path(argv[4])
            during.append((html.exists(), oct(html.stat().st_mode & 0o777)))
            return Done()

        approval.DialogApprover(runner=runner, platform="darwin", plans_dir=folder).approve(SUMMARY, 2)
        self.assertEqual(during, [(True, "0o600")])
        self.assertEqual(list(folder.iterdir()), [])

        def boom(argv):
            raise OSError("the window could not start")

        approval.DialogApprover(runner=boom, platform="darwin", plans_dir=folder).approve(SUMMARY, 2)
        self.assertEqual(list(folder.iterdir()), [])

    def test_it_is_not_available_outside_macos(self):
        self.assertFalse(approval.available(platform="linux"))
        self.assertFalse(approval.available(platform="darwin", osascript="/nonexistent/osascript"))


class AlertScriptTest(unittest.TestCase):
    """The window itself is checked by hand; these pin the settings that make approval a deliberate click."""

    def setUp(self):
        self.js = (ROOT / "jkan" / "alert.js").read_text(encoding="utf-8")

    def test_cancel_is_first_and_default_and_escape_is_bound_to_it(self):
        self.assertLess(self.js.index("addButtonWithTitle('Cancelar')"), self.js.index("addButtonWithTitle(argv[3])"))
        self.assertIn("cancel.keyEquivalent = '\\u001b'", self.js)
        self.assertIn("defaultButtonCell", self.js)

    def test_the_approve_button_has_no_key_equivalent_so_it_takes_a_click(self):
        self.assertIn("ok.keyEquivalent = ''", self.js)

    def test_only_the_second_button_prints_approved(self):
        self.assertIn("NSAlertSecondButtonReturn ? 'approved' : 'cancelled'", self.js)


if __name__ == "__main__":
    unittest.main()
