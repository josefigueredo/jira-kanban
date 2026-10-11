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
_CSS = """
:root{color-scheme:light dark;--fg:#1d1d1f;--muted:#6e6e73;--card:rgba(0,0,0,.045);--line:rgba(0,0,0,.08);
 --chip-bg:rgba(0,0,0,.07);--to-bg:rgba(0,113,227,.12);--to-fg:#0058b0;--out:#9a5b00;--out-bg:rgba(255,159,10,.14)}
@media (prefers-color-scheme:dark){:root{--fg:#f5f5f7;--muted:#a1a1a6;--card:rgba(255,255,255,.07);--line:rgba(255,255,255,.1);
 --chip-bg:rgba(255,255,255,.12);--to-bg:rgba(10,132,255,.22);--to-fg:#6cb4ff;--out:#ffb340;--out-bg:rgba(255,159,10,.16)}}
*{box-sizing:border-box}
html,body{margin:0;background:transparent;color:var(--fg);font:13px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;
 -webkit-font-smoothing:antialiased;cursor:default;-webkit-user-select:none}
body{padding:22px 24px 8px}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
h1{font-size:19px;line-height:1.25;font-weight:650;margin:4px 0 16px}
.cards{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.card{background:var(--card);border-radius:10px;padding:10px 12px;display:grid;gap:6px}
.top{display:flex;gap:8px;align-items:baseline}
.key{flex:none;font:600 11.5px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--chip-bg);border-radius:5px;padding:1px 6px}
.name{font-weight:500;overflow-wrap:anywhere}
.chg{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px}
.from{color:var(--muted)}
.arrow{color:var(--muted)}
.to{background:var(--to-bg);color:var(--to-fg);border-radius:999px;padding:1px 9px;font-weight:600}
.plain{color:var(--muted)}
.out-h{margin:18px 0 6px;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--out)}
.out{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.out li{background:var(--out-bg);border-radius:10px;padding:8px 12px;display:flex;gap:8px;align-items:baseline}
.out .why{color:var(--muted);font-size:12px}
.foot{margin:16px 0 0;color:var(--muted);font-size:11.5px}
"""


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


def _change(text: str) -> str:
    """«A -> B» as origin, arrow and a destination pill; «-> B» as the pill alone; anything else as plain text."""
    if "->" not in text:
        return f'<span class="plain">{escape(text)}</span>'
    origin, destination = (s.strip() for s in text.split("->", 1))
    left = f'<span class="from">{escape(origin)}</span><span class="arrow">→</span>' if origin else ""
    return f'{left}<span class="to">{escape(destination)}</span>'


def render_html(summary, n: int) -> str:
    """The window's whole page (the window is this page plus two native buttons). Every Jira string is escaped; the
    page has no script and loads nothing."""
    heading = getattr(summary, "heading", "") or (str(summary).splitlines() or [""])[0]
    out = [f'<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}</style></head><body>',
           '<div class="eyebrow">jtk quiere escribir en Jira</div>', f"<h1>{escape(heading)}</h1>", '<ul class="cards">']
    rows = rows_of(summary)
    if not rows:  # a writer with no rows: show the text it has
        out += [f'<li class="card"><div class="top"><span class="name">{escape(line)}</span></div></li>'
                for line in str(summary).splitlines()]
    for key, name, change in rows:
        title = f'<span class="name">{escape(name)}</span>' if name else ""
        out.append(f'<li class="card"><div class="top"><span class="key">{escape(key)}</span>{title}</div>'
                   f'<div class="chg">{_change(change)}</div></li>')
    out.append("</ul>")
    left_out = list(getattr(summary, "left_out", []))
    if left_out:
        out.append('<div class="out-h">Quedan afuera</div><ul class="out">')
        out += [f'<li><span class="key">{escape(k)}</span><span class="why">{escape(why)}</span></li>' for k, why in left_out]
        out.append("</ul>")
    out.append(f'<p class="foot">Aprobás con un clic en Apruebo {n}. Escape o Cancelar no escriben nada. '
               f"Se cancela sola a los {TIMEOUT} s.</p></body></html>")
    return "\n".join(out)


def window_height(summary) -> int:
    """Height in points of the page area: an estimate from the rows (long titles wrap), clamped; past the cap the page scrolls."""
    rows = rows_of(summary)
    height = 150 + 74 * len(rows)
    height += sum(18 * (max(len(name) - 1, 0) // 52) for _key, name, _change in rows)
    if not rows:
        height += 40 * max(len(str(summary).splitlines()), 1)
    left_out = list(getattr(summary, "left_out", []))
    if left_out:
        height += 40 + 36 * len(left_out)
    return max(240, min(560, height))


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
            argv = [self._osascript, "-l", "JavaScript", str(ALERT_JS), path, title, f"Apruebo {n}", str(window_height(summary))]
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
