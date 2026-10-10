# Aprobación con diálogo nativo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuando no hay terminal, `jtk apply` y los `--apply` piden la aprobación en una ventana nativa de macOS con el detalle del plan y los botones `Cancelar` (predeterminado) y `Apruebo <n>`, en lugar de negarse.

**Architecture:** Un módulo CORE `jkan/approval.py` (HTML del detalle + lanzador de `osascript` con `jkan/alert.js`, patrón copiado de pbmcp) y una subclase de `str`, `approval.Summary`, que lleva las filas del detalle sin cambiar la firma de `confirm`. `guard.confirm` prueba la terminal primero y el diálogo después; sin ninguno, rechaza como hoy. Los puntos de llamada (applier y comandos viejos) arman el `Summary`. Un parche nuevo del hook deja pasar `apply` solo y bloquea los rodeos que aprobarían por la persona.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9), JavaScript for Automation (`osascript -l JavaScript`), AppKit `NSAlert`, bash.

**Spec:** `docs/superpowers/specs/2026-10-10-aprobacion-con-dialogo-design.md`

## Global Constraints

- Python 3 solo con stdlib; la suite pasa con `python3 -m unittest discover -s tests` y con `/usr/bin/python3` (3.9).
- Rama `feat/approval-dialog` desde `main` (con `fix/acceptance-findings` ya mergeada o rebaseada); conventional commits, sin atribución de IA.
- Sin variable de entorno, bandera ni configuración que salte la aprobación. Los únicos parámetros extra de `guard.confirm` son de prueba (`open_tty`, `dialog`).
- `osascript` se invoca con ruta absoluta `/usr/bin/osascript`; el HTML va a un archivo 0600 que se borra siempre.
- Timeout del diálogo: 100 s (Cursor corta una herramienta inactiva a los 120 s).
- Todo texto que viene de Jira (títulos, nombres, comentarios) se escapa como HTML.
- Los módulos nuevos se declaran en `tests/test_boundaries.py` (`approval` va en CORE).
- No se toca `~/.claude/hooks/*`: el parche se prueba sobre una copia en el scratchpad y lo aplica el usuario.
- Mensajes del CLI en inglés; documentación para personas en castellano rioplatense.

## Review Focus

- Un título de Jira con `<script>` o `&` no rompe ni se ejecuta en la ventana (test de escape).
- Return no aprueba y Cancelar es el predeterminado: el botón de aprobar no tiene `keyEquivalent` (test sobre el texto de `alert.js` + aceptación manual).
- Un plan guardado antes de este cambio, sin `title`, se sigue aplicando y la fila muestra solo la clave.
- Sin terminal y sin diálogo disponible (no macOS, `osascript` ausente) el resultado es el rechazo de hoy con el comando a correr.
- Si la persona cancela o vence el tiempo, el agente no reintenta: la skill lo dice y el mensaje de salida también.

---

### Task 1: Los items del plan guardan `title`

**Files:**
- Modify: `jkan/plan.py` (move, assign, comment, revert)
- Test: `tests/test_plan.py`

**Interfaces:**
- Consumes: `selection` (issues con `summary`), items existentes.
- Produces: cada item de un plan lleva `"title": <summary del issue o "">`; `plan.describe` no cambia de salida.

- [ ] **Step 1: Test que falla** (agregar a `MoveTest`, `AssignTest`, `CommentTest` de `tests/test_plan.py`, usando los helpers de cada clase; el issue de `put` ya trae `summary`):

```python
    def test_every_item_keeps_the_issue_title_for_the_approval_window(self):
        issue = self.put("TEAM-1", "todo", summary="Migrar el login")
        body = plan.move(self.jira, self.view, [issue], self.profiles, "active", now=NOW)
        self.assertEqual(body["items"][0]["title"], "Migrar el login")

```

Y en `RevertTest`:

```python
    def test_a_revert_keeps_the_titles_of_the_plan_it_undoes(self):
        from jkan import applier
        selection = [self.put("TEAM-1", "todo", summary="Uno"), self.put("TEAM-2", "todo", summary="Dos")]
        saved = state.save_plan(plan.move(self.jira, self.view, selection, self.profiles, "active", now=NOW))
        applier.run(self.jira, saved, lambda n, s, c: None, "jtk apply x", now=NOW)
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual([i["title"] for i in body["items"]], ["Uno", "Dos"])

    def test_reverting_a_plan_saved_before_titles_existed_still_works(self):
        saved = self.applied_move()
        for item in saved["items"]:
            item.pop("title", None)
        body = plan.revert(self.jira, saved, self.profiles, now=NOW)
        self.assertEqual([i["title"] for i in body["items"]], ["", ""])
```

Y en las clases de assign y comment de `tests/test_plan.py`, un test igual al de move: `plan.assign(self.view, [issue], person, now=NOW)["items"][0]["title"]` y `plan.comment(self.view, [issue], "hola", now=NOW)["items"][0]["title"]` con `issue = self.put("TEAM-1", "todo", summary="Migrar el login")`.

- [ ] **Step 2: Verlo fallar**
Run: `python3 -m unittest discover -s tests -p test_plan.py 2>&1 | tail -15`
Expected: FAIL con `KeyError: 'title'` en los tres tests nuevos.

- [ ] **Step 3: Implementar**
En `move`: el item pasa a `{"key", "title": issue.get("summary") or "", "from", "to", "transition"}`. En `assign`: igual. En `comment`: `{"key": i["key"], "title": i.get("summary") or ""}`. En `revert`: copiar `title` del item original de esa clave (`next((i.get("title","") for i in original["items"] if i["key"] == key), "")`), tolerando planes viejos sin `title`.

- [ ] **Step 4: Verlos pasar y la suite**
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`, salvo los tests que hoy comparan el item completo y no conocen `title`: `test_a_move_records_the_origin_the_destination_and_the_transition_id` y `test_reverting_a_move_goes_back_to_the_status_it_left_by_its_own_transition` (y los equivalentes de assign/comment que comparen el item entero). Es el cambio deliberado: agregar `"title": <el summary que ya tiene el issue de prueba>` al valor esperado, sin relajar ninguna otra aserción, y dejar un `Ruling` en el ledger.

- [ ] **Step 5: Commit**
`git add jkan/plan.py tests/test_plan.py && git commit -m "feat: plan items keep the issue title for the approval window"`

---

### Task 2: `approval.py`: el HTML, el lanzador y `alert.js`

**Files:**
- Create: `jkan/approval.py`, `jkan/alert.js`, `tests/test_approval.py`
- Modify: `tests/test_boundaries.py` (agregar `approval` a CORE)

**Interfaces:**
- Produces:
  - `class Summary(str)`: `Summary(text, title, rows, left_out=())` con atributos `.title: str`, `.rows: list[tuple[str, str, str]]` (clave, título, cambio) y `.left_out: list[tuple[str, str]]` (clave, motivo).
  - `render_html(summary, n) -> str`.
  - `class DialogApprover` con `approve(summary, n) -> bool` y constructor `DialogApprover(runner=None, platform=None, osascript="/usr/bin/osascript", plans_dir=None)`.
  - `available() -> bool` (macOS y `osascript` ejecutable).
  - `TIMEOUT = 100`.

- [ ] **Step 1: Tests que fallan (`tests/test_approval.py`)**

```python
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

    def test_an_item_without_a_title_shows_only_the_key(self):
        self.assertIn("TEAM-2", approval.render_html(SUMMARY, 2))


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
        self.assertIn("Apruebo 3", argv)
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
    """The dialog itself is checked by hand; these pin the settings that make approval a deliberate click."""

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
```

- [ ] **Step 2: Verlos fallar**
Run: `python3 -m unittest discover -s tests -p test_approval.py 2>&1 | tail -5`
Expected: `ImportError`/`AttributeError` (no existe `jkan.approval`).

- [ ] **Step 3: Implementar `jkan/alert.js`** (adaptación de `product-brain-mcp/src/pbmcp/alert.js`; argv: html, título, texto informativo, rótulo del botón):

```javascript
// jtk's approval alert: a native NSAlert with a scrollable, read-only render of the plan's HTML.
// argv: <html file> <title> <informative text> <approve button label>. Prints "approved" only when the second button is clicked.
// Cancelar is first, highlighted as the default and bound to Escape; the approve button has no key equivalent, so
// approving always takes a click (Return does nothing).
ObjC.import('Cocoa');

function run(argv) {
  const html = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null);
  const attr = $.NSAttributedString.alloc.initWithHTMLDocumentAttributes(html.dataUsingEncoding($.NSUTF8StringEncoding), null);

  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  app.activateIgnoringOtherApps(true);

  const scroll = $.NSScrollView.alloc.initWithFrame($.NSMakeRect(0, 0, 560, 340));
  scroll.hasVerticalScroller = true;
  const text = $.NSTextView.alloc.initWithFrame($.NSMakeRect(0, 0, 545, 340));
  text.editable = false;
  text.textStorage.setAttributedString(attr);
  text.backgroundColor = $.NSColor.whiteColor;
  scroll.backgroundColor = text.backgroundColor;
  text.textContainerInset = $.NSMakeSize(8, 8);
  scroll.documentView = text;

  const alert = $.NSAlert.alloc.init;
  const icon = $.NSImage.imageWithSystemSymbolNameAccessibilityDescription('checkmark.shield', 'jtk');
  if (icon && !icon.isNil()) alert.icon = icon;
  alert.messageText = argv[1];
  alert.informativeText = argv[2];
  const cancel = alert.addButtonWithTitle('Cancelar');
  cancel.keyEquivalent = '\u001b';
  const ok = alert.addButtonWithTitle(argv[3]);
  ok.keyEquivalent = '';
  alert.window.defaultButtonCell = cancel.cell;
  alert.accessoryView = scroll;
  alert.window.appearance = $.NSAppearance.appearanceNamed($.NSAppearanceNameAqua);
  alert.window.level = $.NSFloatingWindowLevel;
  return alert.runModal == $.NSAlertSecondButtonReturn ? 'approved' : 'cancelled';
}
```

- [ ] **Step 4: Implementar `jkan/approval.py`**

```python
"""Human approval in a native macOS window, for when there is no terminal: a person clicks «Apruebo <n>».

The window shows the saved plan's rows (key, title, change) and what was left out, never what the agent says. Cancelar is
the default and the only button Escape reaches; the approve button takes a click. Cancel, close, failure to start or
the timeout is a refusal. The pattern is pbmcp's (product-brain-mcp/src/pbmcp/approval.py:45-55, alert.js:31-38); the
timeout stays under Cursor's 120 s idle cut."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

ALERT_JS = Path(__file__).resolve().parent / "alert.js"
OSASCRIPT = "/usr/bin/osascript"
TIMEOUT = 100  # seconds; Cursor cuts a tool call at 120 s idle
_INFO = "Revisá el detalle. Aprobar solo con un clic; Escape o Cancelar no escriben nada. Se cancela sola a los 100 s."

_CSS = ("body{font:13px -apple-system,Helvetica,sans-serif;color:#172B4D;margin:0}h1{font-size:15px;margin:0 0 8px}"
        "table{border-collapse:collapse;width:100%}td{padding:5px 6px;border-bottom:1px solid #DFE1E6;vertical-align:top}"
        ".k{font-weight:600;white-space:nowrap}.c{color:#42526E}.out{color:#974F0C;margin-top:12px}.t{color:#42526E}")


class Summary(str):
    """The text the terminal shows, plus the rows the window shows. A plain string works everywhere a Summary does."""

    def __new__(cls, text: str, title: str = "", rows: Sequence[Tuple[str, str, str]] = (),
                left_out: Sequence[Tuple[str, str]] = ()):
        obj = super().__new__(cls, text)
        obj.title, obj.rows, obj.left_out = title, [tuple(r) for r in rows], [tuple(r) for r in left_out]
        return obj


def rows_of(summary) -> List[Tuple[str, str, str]]:
    return list(getattr(summary, "rows", []))


def render_html(summary, n: int) -> str:
    title = getattr(summary, "title", "") or str(summary).splitlines()[0]
    out = [f'<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}</style></head><body>',
           f"<h1>{escape(title)}</h1><table>"]
    rows = rows_of(summary)
    if not rows:  # a legacy writer with no rows: show the text it has
        out.append("".join(f'<tr><td colspan="3">{escape(line)}</td></tr>' for line in str(summary).splitlines()))
    for key, name, change in rows:
        label = f' <span class="t">{escape(name)}</span>' if name else ""
        out.append(f'<tr><td class="k">{escape(key)}{label}</td><td class="c">{escape(change)}</td></tr>')
    out.append("</table>")
    left_out = list(getattr(summary, "left_out", []))
    if left_out:
        out.append('<p class="out"><b>Quedan afuera</b></p><table>')
        out += [f'<tr><td class="k">{escape(k)}</td><td class="c">{escape(why)}</td></tr>' for k, why in left_out]
        out.append("</table>")
    out.append("</body></html>")
    return "\n".join(out)


def available(platform: Optional[str] = None, osascript: str = OSASCRIPT) -> bool:
    return (platform or sys.platform) == "darwin" and os.access(osascript, os.X_OK)


def _run(argv: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT)


class DialogApprover:
    def __init__(self, runner: Optional[Callable] = None, platform: Optional[str] = None, osascript: str = OSASCRIPT,
                 plans_dir: Optional[Path] = None):
        self._run, self._platform, self._osascript = runner or _run, platform, osascript
        self._dir = str(plans_dir) if plans_dir else None

    def available(self) -> bool:
        return available(self._platform, self._osascript)

    def approve(self, summary, n: int) -> bool:
        fd, path = tempfile.mkstemp(prefix="jtk-plan-", suffix=".html", dir=self._dir)  # created 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(render_html(summary, n))
            title = getattr(summary, "title", "") or "jtk quiere escribir en Jira"
            argv = [self._osascript, "-l", "JavaScript", str(ALERT_JS), path, title, _INFO, f"Apruebo {n}"]
            try:
                done = self._run(argv)
            except (OSError, subprocess.TimeoutExpired):
                return False
            return done.returncode == 0 and (done.stdout or "").strip() == "approved"
        finally:
            Path(path).unlink(missing_ok=True)  # missing_ok exists since 3.8, so it works on 3.9
```

Agregar `approval` a `CORE` en `tests/test_boundaries.py`. El orden de `argv` es `[osascript, -l, JavaScript, alert.js, html, title, info, label]`: el html es `argv[4]` y el rótulo `argv[7]`.

- [ ] **Step 5: Verlos pasar y la suite**
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3; /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` en ambos.

- [ ] **Step 6: Commit**
`git add jkan/approval.py jkan/alert.js tests/test_approval.py tests/test_boundaries.py && git commit -m "feat: native macOS approval window (Cancelar default, Apruebo n) and the Summary that feeds it"`

---

### Task 3: `guard.confirm` usa el diálogo cuando no hay terminal

**Files:**
- Modify: `jkan/guard.py`, `tests/test_guard.py`

**Interfaces:**
- Consumes: `approval.DialogApprover`, `approval.Summary`.
- Produces: `guard.confirm(n, summary, command, streams=None, open_tty=None, dialog=None)`; exit/mensajes como hoy.

- [ ] **Step 1: Tests que fallan** (en `tests/test_guard.py`)

```python
class FakeDialog:
    def __init__(self, answer, available=True):
        self.answer, self.is_available, self.asked = answer, available, []

    def available(self):
        return self.is_available

    def approve(self, summary, n):
        self.asked.append((str(summary), n))
        return self.answer


class DialogTest(unittest.TestCase):
    NO_TTY = (Stream(False),) * 3

    def test_without_a_terminal_a_click_approves(self):
        dialog = FakeDialog(True)
        guard.confirm(2, "THE SUMMARY", "jtk apply abc", streams=self.NO_TTY, dialog=dialog)
        self.assertEqual(dialog.asked, [("THE SUMMARY", 2)])

    def test_cancelling_the_window_is_not_an_approval_and_says_not_to_retry(self):
        with self.assertRaisesRegex(guard.NotApproved, "not approved.*nothing was written.*do not run it again"):
            guard.confirm(2, "S", "jtk apply abc", streams=self.NO_TTY, dialog=FakeDialog(False))

    def test_with_a_terminal_the_window_is_never_opened(self):
        dialog = FakeDialog(True)
        guard.confirm(1, "S", "jtk apply abc", streams=REAL, open_tty=lambda: Tty("APRUEBO 1"), dialog=dialog)
        self.assertEqual(dialog.asked, [])

    def test_without_a_terminal_and_without_a_window_it_refuses_like_before(self):
        with self.assertRaisesRegex(guard.NotApproved, "Run it yourself"):
            guard.confirm(1, "S", "jtk apply abc", streams=self.NO_TTY, dialog=FakeDialog(True, available=False))
```

Y cambiar la aserción de `test_the_only_knobs_are_the_streams_and_the_tty_opener_for_tests` a `["n", "summary", "command", "streams", "open_tty", "dialog"]`. Los tests existentes que usan `streams=(Stream(False),)*3` sin `dialog` deben seguir rechazando: en el entorno de tests el diálogo real no puede abrirse; para eso el diálogo por defecto solo se usa si `approval.available()`, y los tests existentes pasan `dialog=FakeDialog(True, available=False)` o se ajustan con un helper `NO_WINDOW` (documentar el ajuste en el ledger: no se relaja ninguna aserción, solo se evita abrir una ventana real desde la suite).

- [ ] **Step 2: Verlos fallar**
Run: `python3 -m unittest discover -s tests -p test_guard.py 2>&1 | tail -10`
Expected: FAIL/ERROR (`confirm()` no acepta `dialog`).

- [ ] **Step 3: Implementar** en `guard.py`: importar `approval`; en `confirm`, si no todos los streams son terminal **o** `/dev/tty` no abre, usar el diálogo:

```python
def _via_dialog(n, summary, command, dialog):
    dialog = dialog if dialog is not None else approval.DialogApprover()
    if not dialog.available():
        raise NotApproved(_needs_terminal(command))
    if not dialog.approve(summary, n):
        raise NotApproved("not approved in the window (cancelled, closed or timed out); nothing was written. "
                          "Do not run it again unless the person asks.")
```

y en `confirm`: `if not all(_is_tty(s) ...): return _via_dialog(...)`; el `except OSError` de `open_tty` también cae a `_via_dialog`. El camino de la terminal queda igual.

- [ ] **Step 4: Verlos pasar, suites completas en ambos Python**
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3; /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`. **Importante:** la suite no debe abrir ninguna ventana real; si alguna aparece, un test no está inyectando `dialog`.

- [ ] **Step 5: Commit**
`git add jkan/guard.py tests/ && git commit -m "feat: the guard asks in a native window when there is no terminal"`

---

### Task 4: Los puntos de llamada arman el `Summary`

**Files:**
- Modify: `jkan/plan.py` (`describe` queda; nueva `summary(plan, only)`), `jkan/applier.py`, `jkan/cli.py` (`_assign`, `create`, `push`)
- Test: `tests/test_plan.py`, `tests/test_applier.py`, `tests/test_who_assign.py`, `tests/test_legacy_guard.py`

**Interfaces:**
- Consumes: `approval.Summary`.
- Produces: `plan.summary(plan, only=None) -> approval.Summary` (texto = `describe`, título = primera línea, filas por item, `left_out` = skipped); los confirm reciben un `Summary` (sigue siendo `str`).

- [ ] **Step 1: Tests que fallan**

```python
    BODY = {"id": "x" * 12, "version": 1, "kind": "move", "view": "plataforma", "created": "2026-10-10T12:00:00Z",
            "options": {"to_role": "active", "to_status": None, "allow_close": False},
            "items": [{"key": "TEAM-1", "title": "Uno", "from": {"id": "1", "name": "Backlog"},
                       "to": {"id": "2", "name": "En curso", "role": "active"}, "transition": "1>2"},
                      {"key": "TEAM-2", "title": "Dos", "from": {"id": "1", "name": "Backlog"},
                       "to": {"id": "2", "name": "En curso", "role": "active"}, "transition": "1>2"}],
            "skipped": [{"key": "TEAM-3", "why": "already there"}]}

    def test_the_summary_for_the_window_has_a_row_per_change_and_the_left_out(self):
        summary = plan.summary(self.BODY)
        self.assertEqual(str(summary), plan.describe(self.BODY))
        self.assertEqual(summary.rows, [("TEAM-1", "Uno", "Backlog -> En curso"), ("TEAM-2", "Dos", "Backlog -> En curso")])
        self.assertEqual(summary.left_out, [("TEAM-3", "already there")])

    def test_only_the_pending_keys_get_a_row(self):
        self.assertEqual([r[0] for r in plan.summary(self.BODY, ["TEAM-2"]).rows], ["TEAM-2"])

    def test_an_old_plan_without_titles_still_summarises(self):
        body = dict(self.BODY, items=[{k: v for k, v in i.items() if k != "title"} for i in self.BODY["items"]])
        self.assertEqual([r[1] for r in plan.summary(body).rows], ["", ""])
```

(Van en la clase de `describe` de `tests/test_plan.py`.)

En `tests/test_applier.py`: el `confirm` inyectado recibe un `Summary` con `.rows` de los items pendientes. En `tests/test_who_assign.py` y `tests/test_legacy_guard.py`: el `confirm` inyectado recibe filas con la clave, el título y `-> <persona>` (assign) / `create` / `push`.

- [ ] **Step 2: Verlos fallar** (`AttributeError: module 'jkan.plan' has no attribute 'summary'`).

- [ ] **Step 3: Implementar**
`plan.summary` reutiliza `describe` para el texto y arma las filas: move `(key, title, f"{from} -> {to}")`, assign `(key, title, f"{_who(from)} -> {_who(to)}")`, comment `(key, title, f"Comment: {text}")`. `applier.run` llama `confirm(len(pending), plan_mod.summary(plan, keys), command)`. En `cli._assign`: `Summary(texto, "Asignar a <persona>", [(key, summary, f"-> {person}")…])`. En `create`: filas `(…, tipo + resumen, "crear")` a partir de los `ops` del dry run; en `push`: filas de `changes` y `new`.

- [ ] **Step 4: Suites** — `OK` en ambos Python, sin ventanas reales.

- [ ] **Step 5: Commit** — `git commit -m "feat: apply and the --apply writers hand the approval window a row per change"`

---

### Task 5: Hook, skills y documentos

**Files:**
- Create: `tools/git-guardrails-dialog.patch`
- Modify: `tools/check-guardrails.sh`, `ops/SKILL.md`, `em/SKILL.md` (si nombra el apply), `README.md`, `tests/test_skills.py`
- Fuera del repo: `~/CurrentCode/SPECKIT/AGENTS.md` (backup en el scratchpad)

- [ ] **Step 1: Casos nuevos en `tools/check-guardrails.sh`** (escribirlos con la herramienta de edición de archivos, no con `Bash`: el hook bloquea comandos de shell que mencionan el apply y `tmux`/`script` a la vez):

  - pasan (0): `jtk apply abc123def456`, `jtk assign PLATE-1 Ana --apply`, `jtk push PLATE-1 --apply`, `jtk create --spec s.json --apply`, y lo mismo con `jk`.
  - bloquean (2): `osascript -e 'tell application "System Events" to click button "Apruebo 2"' && jtk apply abc123def456`, `cliclick c:100,100; jtk apply abc123def456`, `osascript -l JavaScript x.js jtk apply abc123def456`, y los casos de pseudo-terminal que ya existen (siguen bloqueando).
  - Los casos viejos «bloquea `jtk apply` solo» pasan a «pasa».

- [ ] **Step 2: Verlos fallar contra el hook actual del usuario**
Run: `tools/check-guardrails.sh | tail -12`
Expected: `WRONG want=0 got=2` en los apply solos y `WRONG want=2 got=0` en los de `System Events`/`cliclick`. Anotar el total.

- [ ] **Step 3: Construir el parche delta en el scratchpad** (como en `git-guardrails-jtk.patch`): copiar `~/.claude/hooks/git-guardrails.sh` a `hook.orig`/`hook.new`; en `hook.new` (con la herramienta de edición):
  - Quitar el `bloquear` de `JK … (create|push|assign) … --apply` y el `bloquear_terminal` de `${JK}apply` (el comando pasa; la guarda pide la aprobación).
  - Mantener las reglas de pseudo-terminal (`APLICA`/`APLICA_ESCRIBE` + `PTY`).
  - Agregar `UI='(osascript[^;&|]*(System Events|click|keystroke)|cliclick|(^|[^[:alnum:]_])peekaboo)'` y bloquear si `coincide "$APLICA"` o `coincide "$APLICA_ESCRIBE"` junto con `coincide "$UI"`.
  - Generar `tools/git-guardrails-dialog.patch` con `diff -u`, probarlo con `patch --dry-run` y `patch -N` sobre `hook.orig`, y correr `tools/check-guardrails.sh hook.final`.
Expected: `N/N cases behaved as expected`, con el hook real sin tocar (`cmp`).

- [ ] **Step 4: Skills y tests de skills**
`ops/SKILL.md`: reemplazar «Never run `jtk apply`» por: correr `jtk apply <id>` **solo** cuando la persona pidió aplicar ese plan; decirle antes que le va a aparecer una ventana con botones y que `Apruebo <n>` es suyo; si cancela o vence, no reintentar y preguntar. Mismo criterio para los `--apply` viejos en `SKILL.md`. Actualizar `tests/test_skills.py` (hoy exige «Never run `jtk apply`»): ahora exige la regla nueva (la frase exacta se escribe en el test al mismo tiempo que en la skill) y que ninguna skill de solo lectura (`standup`, `em`) corra un apply.

- [ ] **Step 5: README y AGENTS.md**
README: sección «Segunda capa» y la de aprobación: la ventana de macOS, qué muestra, los botones, el timeout, que sin macOS queda la terminal, el orden de despliegue (primero el parche del hook, después el merge), y los límites de seguridad del spec. `AGENTS.md` (con backup): el bullet «El usuario publica» pasa a «…`jtk apply <id>` y los `jtk … --apply` los puede lanzar el agente, pero los aprueba la persona con un clic en la ventana; si cancela, no se reintenta».

- [ ] **Step 6: Suites y commit**
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3; /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`. `git add -A && git commit -m "feat: hook patch, skills and docs for approval in a native window"`.

---

### Task 6: Aceptación manual con el usuario (no la ejecuta un agente)

**Files:**
- Create: `docs/superpowers/acceptance/aprobacion-con-dialogo.md`

El agente solo escribe la guía; la corre el usuario en Cursor (la ventana no se automatiza, como en pbmcp).

- [ ] **Step 1: Guía de aceptación** con estos pasos, cada uno con el resultado esperado:
  1. Aplicar el parche del hook (`patch -N …`) y ver `check-guardrails.sh` en verde.
  2. Planificar un `move` de una tarea descartable y pedirle al agente que lo aplique desde Cursor: aparece la ventana **al frente**, con la fila (clave, título, cambio).
  3. **Cancelar** con el botón → nada se escribe y el agente no reintenta.
  4. Repetir y apretar **Escape** → igual. Repetir y apretar **Return** → no aprueba.
  5. Repetir y dejar pasar 100 s → se cancela sola.
  6. Repetir y hacer clic en **Apruebo 1** → se escribe y Jira lo refleja.
  7. Ver la ventana en modo oscuro y en pantalla secundaria.
  8. Un plan con un título de Jira con `<` y `&` se ve literal.
  9. Un `jtk assign … --apply` viejo usa la misma ventana.
- [ ] **Step 2: Commit** — `git add docs/superpowers/acceptance && git commit -m "docs: manual acceptance guide for the approval window"`.

Después de la aceptación: registrar los resultados en el spec («Resultados»), correr las dos suites y mergear; el despliegue es del usuario (parche del hook primero, merge, push).
