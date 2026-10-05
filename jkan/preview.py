"""A standalone, navigable HTML preview of what `jk create --apply` would create, laid out like a Jira issue view.

Everything is inline (CSS, SVG icons, a few lines of JS): no network, no external fonts, no Atlassian logo or assets.
Keys are placeholders (NUEVO-n) in creation order; Jira assigns the real ones on --apply.
"""
from __future__ import annotations

import html
from typing import Dict, List

ICON = {
    "epic": '<svg viewBox="0 0 16 16" class="ti"><rect width="16" height="16" rx="3" fill="#904EE2"/>'
            '<path d="M9.2 3 5 9h2.6L6.8 13 11 7H8.4z" fill="#fff"/></svg>',
    "story": '<svg viewBox="0 0 16 16" class="ti"><rect width="16" height="16" rx="3" fill="#63BA3C"/>'
             '<path d="M5 3.5h6v9L8 10.4 5 12.5z" fill="#fff"/></svg>',
    "task": '<svg viewBox="0 0 16 16" class="ti"><rect width="16" height="16" rx="3" fill="#4BADE8"/>'
            '<path d="m4.5 8.2 2.3 2.3 4.7-4.9" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>',
    "subtask": '<svg viewBox="0 0 16 16" class="ti"><rect width="16" height="16" rx="3" fill="#4BADE8"/>'
               '<rect x="4" y="4" width="5" height="5" rx="1" fill="none" stroke="#fff" stroke-width="1.4"/>'
               '<rect x="7" y="7" width="5" height="5" rx="1" fill="#fff"/></svg>',
}
PRIORITY = {
    "Highest": '<svg viewBox="0 0 16 16" class="pi"><path d="m3 9 5-4 5 4M3 13l5-4 5 4" stroke="#C9372C" stroke-width="2" fill="none"/></svg>',
    "High": '<svg viewBox="0 0 16 16" class="pi"><path d="m3 11 5-5 5 5" stroke="#E2483D" stroke-width="2" fill="none"/></svg>',
    "Medium": '<svg viewBox="0 0 16 16" class="pi"><path d="M3 6h10M3 10h10" stroke="#E2B203" stroke-width="2"/></svg>',
    "Low": '<svg viewBox="0 0 16 16" class="pi"><path d="m3 5 5 5 5-5" stroke="#1D7AFC" stroke-width="2" fill="none"/></svg>',
    "Lowest": '<svg viewBox="0 0 16 16" class="pi"><path d="m3 3 5 4 5-4M3 7l5 4 5-4" stroke="#0C66E4" stroke-width="2" fill="none"/></svg>',
}
GRID = ('<svg viewBox="0 0 16 16" width="18" height="18"><g fill="#44546F"><rect x="1" y="1" width="4" height="4" rx="1"/>'
        '<rect x="6" y="1" width="4" height="4" rx="1"/><rect x="11" y="1" width="4" height="4" rx="1"/>'
        '<rect x="1" y="6" width="4" height="4" rx="1"/><rect x="6" y="6" width="4" height="4" rx="1"/>'
        '<rect x="11" y="6" width="4" height="4" rx="1"/><rect x="1" y="11" width="4" height="4" rx="1"/>'
        '<rect x="6" y="11" width="4" height="4" rx="1"/><rect x="11" y="11" width="4" height="4" rx="1"/></g></svg>')

CSS = """
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{font:14px/20px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;color:#172B4D;background:#fff}
a{color:#0C66E4;text-decoration:none}a:hover{text-decoration:underline}
.top{height:56px;display:flex;align-items:center;gap:12px;padding:0 16px;border-bottom:1px solid #DCDFE4;background:#fff;position:sticky;top:0;z-index:2}
.top .app{display:flex;align-items:center;gap:8px;font-weight:600;color:#44546F}
.top .search{margin-left:auto;width:280px;height:32px;border:1px solid #8590A2;border-radius:4px;padding:0 10px;color:#626F86;display:flex;align-items:center;font-size:14px}
.pill{background:#E9F2FF;color:#0055CC;border-radius:3px;padding:2px 8px;font-size:12px;font-weight:600;text-transform:uppercase}
.banner{background:#FFF7D6;border-bottom:1px solid #F8E6A0;padding:8px 16px;color:#533F04}
.shell{display:flex;min-height:calc(100% - 96px)}
.side{width:260px;flex:none;background:#F7F8F9;border-right:1px solid #DCDFE4;padding:16px 8px}
.side .proj{display:flex;gap:10px;align-items:center;padding:0 8px 16px}
.side .proj b{display:block}.side .proj span{color:#626F86;font-size:12px}
.avatar-p{width:32px;height:32px;border-radius:4px;background:#1D7AFC;color:#fff;display:grid;place-items:center;font-weight:700}
.side h4{font-size:11px;color:#626F86;text-transform:uppercase;letter-spacing:.04em;margin:8px 8px 6px}
.side a{display:flex;gap:8px;align-items:center;color:#44546F;padding:5px 8px;border-radius:3px;font-size:13px}
.side a:hover{background:#091E420F;text-decoration:none}.side a.on{background:#E9F2FF;color:#0C66E4}
.side a .k{color:#626F86;white-space:nowrap}.side a .s{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l1{padding-left:24px!important}.l2{padding-left:40px!important}
main{flex:1;min-width:0;padding:24px 32px}
.issue{display:none}.issue.on{display:block}
.crumbs{display:flex;gap:6px;align-items:center;color:#44546F;font-size:14px;margin-bottom:12px;flex-wrap:wrap}
.crumbs .sep{color:#8590A2}
h1{font-size:24px;line-height:28px;font-weight:500;margin:0 0 16px}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:32px}
h3{font-size:14px;font-weight:600;margin:24px 0 8px}
.desc p{margin:0 0 10px;white-space:pre-wrap}.desc ul{margin:0 0 10px;padding-left:20px}.muted{color:#626F86}
table{width:100%;border-collapse:collapse;border:1px solid #DCDFE4;border-radius:3px}
td{padding:6px 8px;border-top:1px solid #DCDFE4;vertical-align:middle}tr:first-child td{border-top:0}
td.key{white-space:nowrap;width:1%}td.pri,td.st{width:1%;white-space:nowrap}
.lz{display:inline-block;background:#DCDFE4;color:#44546F;border-radius:3px;padding:0 4px;font-size:11px;font-weight:700;text-transform:uppercase;line-height:16px}
.status{display:inline-flex;gap:6px;align-items:center;background:#091E420F;border-radius:3px;padding:6px 12px;font-weight:600;color:#44546F;margin-bottom:16px}
.panel{border:1px solid #DCDFE4;border-radius:3px}.panel h4{margin:0;padding:12px;border-bottom:1px solid #DCDFE4;font-size:14px}
.row{display:grid;grid-template-columns:120px 1fr;gap:8px;padding:8px 12px;align-items:center}.row .lbl{color:#44546F;font-weight:600;font-size:12px}
.who{display:inline-flex;gap:6px;align-items:center}.av.off{background:#8590A2}.av{width:24px;height:24px;border-radius:50%;background:#8270DB;color:#fff;display:grid;place-items:center;font-size:11px;font-weight:700}
.ti{width:16px;height:16px;flex:none;vertical-align:-3px}.pi{width:16px;height:16px;vertical-align:-3px}
.foot{color:#626F86;font-size:12px;padding:12px}
.tag{display:inline-block;background:#091E420F;border-radius:3px;padding:0 6px;margin:0 4px 4px 0}
@media (max-width:900px){.side{display:none}.cols{grid-template-columns:1fr}main{padding:16px}}
"""

JS = """
(function(){var ids=[].map.call(document.querySelectorAll('.issue'),function(s){return s.id});
function show(){var id=location.hash.slice(1);if(ids.indexOf(id)<0)id=ids[0];
[].forEach.call(document.querySelectorAll('.issue'),function(s){s.classList.toggle('on',s.id===id)});
[].forEach.call(document.querySelectorAll('.side a'),function(a){a.classList.toggle('on',a.getAttribute('href')==='#'+id)});
window.scrollTo(0,0);}window.addEventListener('hashchange',show);show();})();
"""

ASSIGNEE = {"me-done": ("Vos · completa", ""), "me": ("Vos", ""), "none": ("Sin asignar", " off"),
            "ask": ("A decidir", " off")}

e = html.escape


def _desc(text: str) -> str:
    if not text.strip():
        return '<p class="muted">Sin descripción.</p>'
    out: List[str] = []
    for block in text.split("\n\n"):
        lines = block.splitlines()
        bullets = [ln for ln in lines if ln.startswith("- ")]
        head = [ln for ln in lines if not ln.startswith("- ")]
        if head:
            out.append(f"<p>{e(chr(10).join(head))}</p>")
        if bullets:
            out.append("<ul>" + "".join(f"<li>{e(b[2:])}</li>" for b in bullets) + "</ul>")
    return "".join(out)


def render(ops: List[dict], conv: dict) -> str:
    types: Dict[str, str] = conv["issue_types"]
    project = conv["project"]
    status = conv.get("initial_status", "Backlog")
    key = {op["ref"]: f"NUEVO-{i}" for i, op in enumerate(ops, 1)}
    by_ref = {op["ref"]: op for op in ops}
    children: Dict[str, List[dict]] = {}
    for op in ops:
        if op["parent"]:
            children.setdefault(op["parent"], []).append(op)

    def link(op: dict, text_only: bool = False) -> str:
        label = f'{ICON[op["kind"]]} <span class="k">{key[op["ref"]]}</span>'
        return label if text_only else f'<a href="#{key[op["ref"]]}">{label}</a>'

    side = []
    for op in ops:
        level = {"epic": "", "story": "l1", "task": "l1", "subtask": "l2"}[op["kind"]]
        side.append(f'<a class="{level}" href="#{key[op["ref"]]}">{ICON[op["kind"]]}<span class="k">{key[op["ref"]]}</span>'
                    f'<span class="s">{e(op["summary"])}</span></a>')

    pages = []
    for n, op in enumerate(ops, 1):
        chain, ref = [], op["parent"]
        while ref:
            chain.insert(0, by_ref[ref])
            ref = by_ref[ref]["parent"]
        crumbs = [f"<span>{e(project)}</span>"] + [link(p) for p in chain] + [link(op, text_only=True)]
        kids = children.get(op["ref"], [])
        title = "Issues secundarios" if op["kind"] == "epic" else "Subtareas"
        rows = "".join(f'<tr><td>{ICON[k["kind"]]}</td><td class="key"><a href="#{key[k["ref"]]}">{key[k["ref"]]}</a></td>'
                       f'<td>{e(k["summary"])}</td><td class="pri">{PRIORITY.get(k.get("priority") or "", "")}</td>'
                       f'<td class="st"><span class="lz">{e(status)}</span></td></tr>' for k in kids)
        table = f"<h3>{title}</h3><table>{rows}</table>" if kids else (
            f'<h3>{title}</h3><p class="muted">Ninguno.</p>' if op["kind"] != "subtask" else "")
        parent = by_ref.get(op["parent"]) if op["parent"] else None
        labels = "".join(f'<span class="tag">{e(lb)}</span>' for lb in op.get("labels") or []) or '<span class="muted">Ninguno</span>'
        prio = op.get("priority") or ""
        who, av_cls = ASSIGNEE.get(op.get("assignee") or "ask", ASSIGNEE["ask"])
        order = (f"Se crea primero (paso 1 de {len(ops)}): el resto cuelga de esta épica." if not parent
                 else f"Se crea en el paso {n} de {len(ops)}, después de {key[parent['ref']]}.")
        pages.append(f"""
<section class="issue" id="{key[op['ref']]}">
  <div class="crumbs">{' <span class="sep">/</span> '.join(crumbs)}</div>
  <h1>{e(op['summary'])}</h1>
  <div class="cols">
    <div>
      <h3>Descripción</h3><div class="desc">{_desc(op.get('description') or '')}</div>
      {table}
    </div>
    <div>
      <div class="status">{e(status)} <span class="muted">▾</span></div>
      <div class="panel"><h4>Detalles</h4>
        <div class="row"><span class="lbl">Tipo</span><span>{ICON[op['kind']]} {e(types[op['kind']])}</span></div>
        <div class="row"><span class="lbl">Responsable</span><span class="who"><span class="av{av_cls}"><svg viewBox="0 0 16 16" width="14" height="14"><circle cx="8" cy="5.5" r="3" fill="#fff"/><path d="M2.5 14c.6-3 2.8-4.5 5.5-4.5s4.9 1.5 5.5 4.5z" fill="#fff"/></svg></span> {who}</span></div>
        <div class="row"><span class="lbl">Prioridad</span><span>{PRIORITY.get(prio, '')} {e(prio)}</span></div>
        <div class="row"><span class="lbl">Etiquetas</span><span>{labels}</span></div>
        <div class="row"><span class="lbl">Principal</span><span>{link(parent) if parent else '<span class="muted">Ninguno</span>'}</span></div>
        <div class="foot">{order}</div>
      </div>
    </div>
  </div>
</section>""")

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(project)} · vista previa</title><link rel="icon" href="data:,"><style>{CSS}</style></head>
<body>
<header class="top"><span class="app">{GRID} Proyectos <span class="muted">/</span> {e(project)}</span>
  <span class="pill">Vista previa</span><span class="search">Buscar</span></header>
<div class="banner"><b>Vista previa:</b> nada se creó en Jira. <code>jk create --apply</code> crea estos {len(ops)} issues en
  {e(project)}, en este orden, con claves reales en lugar de NUEVO-n.</div>
<div class="shell">
  <aside class="side"><div class="proj"><div class="avatar-p">{e(project[:1])}</div><div><b>{e(project)}</b><span>Épica en preparación</span></div></div>
    <h4>Issues a crear</h4>{''.join(side)}</aside>
  <main>{''.join(pages)}</main>
</div>
<script>{JS}</script>
</body></html>
"""
