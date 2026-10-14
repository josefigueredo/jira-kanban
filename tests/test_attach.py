from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path

from helpers import FakeJira, epic_with_children, make_project
from jkan import approval, attach, cli, guard
from jkan import jira as jira_mod

# Fake secrets with the real formats; none of them is a live credential.
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
NRAK = "NRAK-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0"
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
ATL = "ATATT3x" + "FfGF0abcdefghijklmnopqrstuvwxyz0123456789"
LICENSE = "0123456789abcdef0123456789abcdef0123" + "NRAL"
KEY_BLOCK = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----"
JIRA_TOKEN = "tok-of-the-configured-jira-credentials"


class Asked:
    def __init__(self, approve=True):
        self.approve, self.calls = approve, []

    def __call__(self, n, summary, command):
        self.calls.append((n, summary, command))
        if not self.approve:
            raise guard.NotApproved("not approved; nothing was written.")


def run(args, jira, confirm):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args, client=lambda project: jira, confirm=confirm)
    return code, out.getvalue(), err.getvalue()


class SanitizeTest(unittest.TestCase):
    def test_every_category_is_replaced_and_counted_without_its_value(self):
        text = (f"gh {GH}\nnr {NRAK} lic {LICENSE}\naws {AWS}\natl {ATL}\nAuthorization: Bearer abcdefghij0123456789xyz\n"
                f"{KEY_BLOCK}\njira {JIRA_TOKEN}\nsee /Users/ana.perez/CurrentCode/x.py:3 and /home/ana/notes.md\n"
                "by Jose Figueredo <jose@example.com>\n")
        clean, counts = attach.sanitize(text.encode(), secrets=[JIRA_TOKEN])
        out = clean.decode()
        for secret in (GH, NRAK, LICENSE, AWS, ATL, "abcdefghij0123456789xyz", "b3BlbnNzaC1rZXktdjEAAAAA", JIRA_TOKEN,
                       "/Users/ana.perez", "/home/ana"):
            self.assertNotIn(secret, out)
        self.assertIn("~/CurrentCode/x.py:3", out)
        self.assertIn("~/notes.md", out)
        self.assertIn("Jose Figueredo <jose@example.com>", out)  # authorship is kept on purpose
        self.assertEqual(counts, {"credencial de Jira": 1, "token": 6, "clave privada": 1, "ruta local": 2})

    def test_a_clean_text_is_sanitized_with_no_changes(self):
        clean, counts = attach.sanitize(b"<h1>Hola</h1>\n", secrets=[])
        self.assertEqual((clean, counts), (b"<h1>Hola</h1>\n", {}))
        self.assertEqual(attach.describe(True, counts), "sí — sin cambios")
        self.assertEqual(attach.describe(True, {"ruta local": 2, "token": 1}), "sí — 2 rutas locales, 1 token")

    def test_binary_content_cannot_be_sanitized(self):
        self.assertIsNone(attach.sanitize(b"\x89PNG\r\n\x1a\n\x00\xff", secrets=[])[0])


class AttachCommandTest(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()
        epic_with_children(self.jira)  # PLATE-600 epic > PLATE-601 story > PLATE-602 subtask; PLATE-603 task
        self.project = make_project()
        self.doc = self.project / "guia.html"
        self.doc.write_text(f"<p>ruta /Users/ana.perez/x y token {GH}</p>\n", encoding="utf-8")
        self.original = self.doc.read_bytes()

    def args(self, *extra, key="PLATE-603"):
        return ["attach", key, str(self.doc), "--project", str(self.project), *extra]

    def test_a_dry_run_says_what_would_go_and_writes_nothing(self):
        asked = Asked()
        code, out, _ = run(self.args(), self.jira, asked)
        self.assertEqual((code, asked.calls, self.jira.writes), (0, [], []))
        self.assertIn("guia.html", out)
        self.assertIn("Sanitizado: sí — 1 ruta local, 1 token", out)
        self.assertIn("dry run: nothing written; --apply uploads 1 file(s) to PLATE-603", out)

    def test_apply_shows_the_attachment_and_its_sanitizing_then_uploads_exactly_that(self):
        asked = Asked()
        code, out, _ = run(self.args("--apply"), self.jira, asked)
        self.assertEqual(code, 0, out)
        n, summary, command = asked.calls[0]
        self.assertEqual(n, 1)
        self.assertIn("adjunto", summary.heading)
        self.assertIn("PLATE-603", summary.heading)
        [(key, name, change)] = summary.rows
        self.assertEqual((key, name), ("PLATE-603", "guia.html"))
        uploaded = self.jira.files["PLATE-603"]["guia.html"]
        self.assertNotIn("Acción", change)  # the heading already says it uploads
        self.assertIn(f"sha256 {hashlib.sha256(uploaded).hexdigest()[:12]}", change)
        self.assertIn("Sanitizado: sí — 1 ruta local, 1 token", change)
        self.assertIn("Sanitizado: sí — 1 ruta local, 1 token", str(summary))  # the terminal says the same
        self.assertEqual(summary.kinds, ["task"])
        self.assertNotIn(GH.encode(), uploaded)
        self.assertNotIn(b"/Users/ana.perez", uploaded)
        self.assertEqual(self.doc.read_bytes(), self.original)  # the original file is never touched
        self.assertNotIn(GH, str(summary) + approval.render_html(summary, n))
        self.assertTrue(command.startswith("jtk attach PLATE-603 "))
        self.assertIn("uploaded 1 file(s) to PLATE-603", out)

    def test_no_sanitize_uploads_the_file_as_is_and_says_so(self):
        asked = Asked()
        self.assertEqual(run(self.args("--no-sanitize", "--apply"), self.jira, asked)[0], 0)
        self.assertIn("Sanitizado: no (--no-sanitize)", asked.calls[0][1].rows[0][2])
        self.assertEqual(self.jira.files["PLATE-603"]["guia.html"], self.original)

    def test_a_binary_file_is_refused_unless_no_sanitize(self):
        image = self.project / "captura.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
        asked = Asked()
        code, _, err = run(["attach", "PLATE-603", str(image), "--project", str(self.project), "--apply"], self.jira, asked)
        self.assertEqual((code, asked.calls, self.jira.writes), (1, [], []))
        self.assertIn("--no-sanitize", err)
        code, _, _ = run(["attach", "PLATE-603", str(image), "--project", str(self.project), "--no-sanitize", "--apply"],
                         self.jira, asked)
        self.assertEqual(code, 0)
        self.assertIn("Sanitizado: no (binario, --no-sanitize)", asked.calls[0][1].rows[0][2])

    def test_the_same_name_and_size_already_attached_is_left_out(self):
        run(self.args("--apply"), self.jira, Asked())
        asked = Asked()
        code, out, _ = run(self.args("--apply"), self.jira, asked)
        self.assertEqual((code, asked.calls), (0, []))
        self.assertIn("already attached", out)
        self.assertEqual(self.jira.writes.count(("attach", "PLATE-603", "guia.html")), 1)
        other = self.project / "otra.txt"
        other.write_text("x\n", encoding="utf-8")
        asked = Asked()
        run(["attach", "PLATE-603", str(self.doc), str(other), "--project", str(self.project), "--apply"], self.jira, asked)
        n, summary, _ = asked.calls[0]
        self.assertEqual((n, [r[1] for r in summary.rows]), (1, ["otra.txt"]))
        self.assertEqual(summary.left_out, [("guia.html", "ya adjunto en PLATE-603 (mismo nombre y tamaño)")])

    def test_without_approval_nothing_is_uploaded(self):
        code, _, err = run(self.args("--apply"), self.jira, Asked(approve=False))
        self.assertEqual((code, self.jira.writes), (guard.EXIT_NEEDS_PERSON, []))
        self.assertIn("nothing was written", err)

    def test_a_missing_file_or_one_over_the_limit_writes_nothing(self):
        code, _, err = run(["attach", "PLATE-603", str(self.project / "nope.md"), "--project", str(self.project)],
                           self.jira, Asked())
        self.assertEqual(code, 2)
        self.assertIn("nope.md", err)
        self.jira.attachment_meta = {"enabled": True, "uploadLimit": 10}
        code, _, err = run(self.args("--apply"), self.jira, Asked())
        self.assertEqual((code, self.jira.writes), (1, []))
        self.assertIn("upload limit", err)


class RawRecorder:
    def __init__(self, answer):
        self.answer, self.requests = answer, []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        return FakeResponse(json.dumps(self.answer).encode())


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class JiraAttachTest(unittest.TestCase):
    def test_the_upload_is_multipart_with_the_no_check_header_and_journaled_without_content(self):
        log = []
        rec = RawRecorder([{"id": "9", "filename": "guia.html", "size": 5}])
        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=rec, journal=log.append)
        got = jira.attach("PLATE-1", "guia.html", b"hola\n", record={"sanitized": True, "redactions": {"token": 1}})
        req = rec.requests[0]
        self.assertEqual((req.get_method(), req.full_url),
                         ("POST", "https://example.atlassian.net/rest/api/3/issue/PLATE-1/attachments"))
        self.assertEqual(req.get_header("X-atlassian-token"), "no-check")
        content_type = req.get_header("Content-type")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        boundary = content_type.split("boundary=", 1)[1].encode()
        self.assertIn(b'Content-Disposition: form-data; name="file"; filename="guia.html"', req.data)
        self.assertIn(b"\r\n\r\nhola\n\r\n--" + boundary + b"--\r\n", req.data)
        self.assertEqual(got, {"id": "9", "filename": "guia.html", "size": 5})
        self.assertEqual(log, [{"action": "attach", "key": "PLATE-1", "file": "guia.html", "bytes": 5,
                                "sha256": hashlib.sha256(b"hola\n").hexdigest(), "sanitized": True,
                                "redactions": {"token": 1}}])

    def test_attachments_and_the_upload_limit_are_read(self):
        answers = {"/rest/api/3/attachment/meta": {"enabled": True, "uploadLimit": 1073741824},
                   "/rest/api/3/issue/PLATE-1": {"key": "PLATE-1", "fields": {
                       "summary": "S", "issuetype": {"name": "Tarea"},
                       "attachment": [{"filename": "a.html", "size": 3, "id": "1", "mimeType": "text/html"}]}}}

        def opener(request, timeout=None):
            path = request.full_url.split("example.atlassian.net", 1)[1].split("?", 1)[0]
            return FakeResponse(json.dumps(answers[path]).encode())

        jira = jira_mod.Jira("https://example.atlassian.net", "me@x", "tok", opener=opener)
        self.assertEqual(jira.attachment_limit(), 1073741824)
        self.assertEqual(jira.attachments("PLATE-1"), {"key": "PLATE-1", "summary": "S", "issuetype": "Tarea",
                                                       "attachments": [{"filename": "a.html", "size": 3}]})


if __name__ == "__main__":
    unittest.main()
