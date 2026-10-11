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
_INFO = f"Aprobás con un clic en el botón Apruebo. Escape o Cancelar no escriben nada. Se cancela sola a los {TIMEOUT} s."

_CSS = ("body{font:13px -apple-system,Helvetica,sans-serif;color:#172B4D;margin:0}"
        ".row{padding:7px 2px;border-bottom:1px solid #DFE1E6}.k{font-weight:600}.t{color:#172B4D}"
        ".chg{color:#42526E;font-size:12px;margin-top:2px}.out{color:#974F0C;font-weight:600;margin:14px 0 2px}")


class Unavailable(Exception):
    """The window could not be shown (osascript failed or is missing): nobody was asked."""


class Summary(str):
    """The text the terminal shows, plus the heading and rows the window shows. A plain string works everywhere a
    Summary does. (`heading`, not `title`: str already has a title() method.)"""

    def __new__(cls, text: str, heading: str = "", rows: Sequence[Tuple[str, str, str]] = (),
                left_out: Sequence[Tuple[str, str]] = ()):
        obj = super().__new__(cls, text)
        obj.heading, obj.rows, obj.left_out = heading, [tuple(r) for r in rows], [tuple(r) for r in left_out]
        return obj


def rows_of(summary) -> List[Tuple[str, str, str]]:
    return list(getattr(summary, "rows", []))


def _arrow(text: str) -> str:
    return escape(text.replace("->", "→"))


def render_html(summary, n: int) -> str:
    """The window's body. Its heading is the window title, so it is not repeated here (`n` is the button's, not ours)."""
    out = [f'<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}</style></head><body>']
    rows = rows_of(summary)
    if not rows:  # a writer with no rows: show the text it has
        out += [f'<div class="row">{escape(line)}</div>' for line in str(summary).splitlines()]
    for key, name, change in rows:
        label = f' <span class="t">{escape(name)}</span>' if name else ""
        out.append(f'<div class="row"><span class="k">{escape(key)}</span>{label}<div class="chg">{_arrow(change)}</div></div>')
    left_out = list(getattr(summary, "left_out", []))
    if left_out:
        out.append('<div class="out">Quedan afuera</div>')
        out += [f'<div class="row"><span class="k">{escape(k)}</span><div class="chg">{_arrow(why)}</div></div>'
                for k, why in left_out]
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
            title = getattr(summary, "heading", "") or "jtk quiere escribir en Jira"
            argv = [self._osascript, "-l", "JavaScript", str(ALERT_JS), path, title, _INFO, f"Apruebo {n}"]
            try:
                done = self._run(argv)
            except subprocess.TimeoutExpired:
                return False  # the window was up and nobody clicked
            except OSError as exc:
                raise Unavailable(f"the approval window could not start ({exc})") from None
            if done.returncode != 0:
                raise Unavailable(f"the approval window failed (osascript exit {done.returncode})")
            return (done.stdout or "").strip() == "approved"
        finally:
            Path(path).unlink(missing_ok=True)  # missing_ok exists since 3.8, so it works on 3.9
