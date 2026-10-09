# jira-em, fase 2: views y reportes de equipo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un EM o Sr EM guarde los boards y el equipo que sigue como un *view* y pida, con `jk team`, siete reportes de solo lectura (estado, estancados, bloqueos, flujo, resumen del período, mesa de ayuda y comparación entre equipos), todos calculados con los roles de los perfiles de board y con el contrato de salida de la spec.

**Architecture:** Módulos planos nuevos del lado de lectura: `views` (los boards y el equipo), `team` (los reportes como funciones puras sobre issues que ya traen su rol), `team_render` (Markdown con el contrato de salida) y `team_cli` (`jk team ...`). Las consultas se arman en `queries` a partir de los ids de estado de cada perfil: lo abierto como `status not in (<cerrados>)`, lo entregado y descartado como `status in (<ids>)`. El cliente de Jira suma una búsqueda con tope y el tamaño de un grupo. Una skill nueva, `jira-em`, se instala por defecto.

**Tech Stack:** Python 3.9 o más (solo biblioteca estándar), `unittest`, bash.

**Spec:** `docs/superpowers/specs/2026-10-09-jira-em-design.md` (secciones «Views y reportes de equipo», «Contrato de las skills» y fase 2). Este plan sigue al de las fases 0 y 1 (`docs/superpowers/plans/2026-10-09-jira-em-fases-0-1.md`), ya mergeado en `main`.

## Alcance de este plan

Cubre la **fase 2** de la spec. La fase 3 (`jk plan` y `jk apply`) y la fase 4 (cierre) van en planes propios. La fase 3 sigue necesitando probar si `!` entrega una terminal interactiva, **un proyecto de pruebas** para escribir de verdad y la decisión sobre los comandos `--apply` que ya existen.

## Global Constraints

- Python **3.9 o más, solo biblioteca estándar**; la suite corre igual con `python3` y con `/usr/bin/python3` (3.9).
- Pruebas con `python3 -m unittest discover -s tests` y un Jira falso (`tests/helpers.py`): nada sale a la red.
- TDD y **conventional commits, sin atribución de IA** (regla del usuario). No hay push, PR ni merge: los hace el usuario.
- Documentación para personas en castellano rioplatense; **código, skills y mensajes del CLI en inglés** (las etiquetas de los reportes siguen en castellano, como hoy).
- Las credenciales `IC_JIRA_*` no se imprimen ni se commitean.
- `jk team` **no escribe en Jira**; lo único que escribe es el view local (`~/.config/jk/views/`, o `$JK_CONFIG_DIR`).
- Ningún módulo del lado de lectura importa uno del lado de escritura (`tests/test_boundaries.py`); los cuatro módulos nuevos van al lado de lectura.
- **Nada que venga de afuera llega a una consulta JQL sin validarse**: claves de proyecto, nombre de grupo, ids de cuenta y ids de estado. Los ids de estado van **sin comillas** (entre comillas Jira devuelve otra cosa: medido, 142 issues contra 240).
- Los tests nunca leen ni escriben el `~/.config/jk` real: `tests/helpers.py` apunta `JK_CONFIG_DIR` a un directorio temporal al importarse.

## Desvíos y precisiones respecto de la spec (a revisar junto con este plan)

| Spec | Este plan | Por qué (medido) |
|---|---|---|
| Consultas por rol como `status in (<ids>)` | Lo abierto, como `status not in (<ids de lo cerrado>)`; lo entregado y descartado, como `status in (<ids>)`. Ids sin comillas | Con `status in (<abiertos>)` un perfil sin decidir **omite issues** (240 contra 244 en PLATE+UA); con `not in` entran y salen como «sin rol». La spec se corrige en la Task 8 |
| El perfil tiene `wip_limit`, pero no hay cómo ponerlo | Nuevo `jk board limit KEY N\|none` | Sin él, el veredicto de carga de `jk team status` no se puede usar sin editar el JSON a mano |
| «Reportes corren con perfil sin confirmar» | Con perfil sin confirmar corren y lo avisan; **con un board sin perfil se niegan** (código 1, «run jk board setup KEY») | Sin perfil no hay ids de estado con los que armar la consulta |
| `rollup`: una fila por view | Un view que no se puede calcular **sigue apareciendo** como fila con el motivo, y el comando sale con 1 | Que un view roto no esconda a los demás |
| Veredicto de carga por persona | Por persona **y por board** | Cada perfil tiene su propio límite; sumar boards con límites distintos no tiene sentido |
| `--view` en `jk done\|next\|blocked` | Igual, y no se puede combinar con `--jira-project`. La persona se busca entre los asignables del **primer** board del view | `people.resolve` busca por un solo proyecto |
| «Estancado» | Se decide por los **días en la categoría**; los días desde la última edición van al lado | Es lo que dice la spec; ninguna de las dos fechas es «sin progreso» y los Límites lo aclaran |

**Hallazgo para decidir (no se resuelve acá):** `jk create`, `jk push` y `jk assign --apply` siguen sin guardia (spec, «Riesgos»). La fase 3 tiene que decidir si les aplica el mismo.

## Review Focus

Modos de falla que la spec implica y que las tareas de los reportes no cubren «de oficio»; cada uno tiene su test.

1. **Un perfil ilegible no se confunde con «sin perfil»**: la negativa nombra el archivo y el motivo → `ReportsTest.test_a_profile_file_nobody_can_read_is_named_in_the_refusal` (Task 6).
2. **Una búsqueda que llega al tope de 1000 issues lo dice**, en el texto y en el JSON, en vez de cortar en silencio → `ReportsTest.test_a_search_that_hits_the_cap_says_so_instead_of_cutting_in_silence` (Task 6) y `SearchCappedTest` (Task 1).
3. **Los estados sin rol siguen visibles** («sin rol») y no se cuentan como entregados ni se descartan → `StatusReportTest`, `ReportsTest.test_undecided_statuses_are_counted_as_without_role_and_announced` y `test_open_work_is_everything_not_closed...` (Tasks 3, 4 y 6).
4. **Nada de lo que viene de un view o de un perfil puede alterar una consulta** → `BuildTest.test_the_team_is_a_group_or_a_list_of_people_and_nothing_that_can_alter_a_query` y `TeamQueriesTest.test_nothing_from_outside_reaches_the_query` (Task 3).
5. **Un view roto no esconde a los demás en `rollup`** → `ReportsTest.test_rollup_gives_a_row_per_view_and_keeps_a_view_that_cannot_be_computed` (Task 6).

Además quedan fijados: que `--all` levanta el corte de 20 filas y que sin él se avisa cuántas quedaron afuera, que `jk team` no escribe en Jira, que un límite de WIP sin sentido invalida el perfil, que un view con un nombre de grupo malicioso se rechaza al guardarlo y al leerlo, y que la skill de equipo solo menciona comandos que existen.

## Estructura de archivos

| Archivo | Responsabilidad | Task |
|---|---|---|
| `jkan/jira.py` (edición) | `search_capped`, `group_total`, el día de `updated` | 1 |
| `tests/helpers.py` (edición), `tests/test_jira_team.py`, `tests/test_search.py` | Jira falso ampliado y pruebas del cliente | 1 |
| `jkan/board_profile.py`, `jkan/board_cli.py` (edición), `tests/test_board_limit.py` | Escritura atómica común y `jk board limit` | 2 |
| `jkan/queries.py` (edición), `jkan/views.py` (nuevo), `tests/team_fixtures.py`, `tests/test_views.py`, `tests/test_queries_team.py`, `tests/test_boundaries.py` | Consultas por rol y views | 3 |
| `jkan/team.py` (nuevo), `tests/test_team.py` | Los reportes como funciones puras | 4 |
| `jkan/team_render.py` (nuevo), `tests/test_team_render.py` | Markdown y contrato de salida | 5 |
| `jkan/team_cli.py` (nuevo), `jkan/cli.py` (edición), `tests/test_team_cli.py` | `jk team ...` | 6 |
| `jkan/cli.py` (edición), `tests/test_view_flag.py` | `--view` en `done`, `next` y `blocked` | 7 |
| `em/SKILL.md` (nuevo), `install.sh`, `tests/test_install.py`, `tests/test_skills.py`, `standup/SKILL.md`, `README.md`, la spec | Skill, instalación y docs | 8 |

Línea base antes de empezar: **327 tests en verde** (`python3 -m unittest discover -s tests`). Al terminar: **439**.

---

### Task 1: El cliente de Jira lee con tope, mide un grupo y trae `updated`

**Files:**
- Modify: `jkan/jira.py` (cuatro ediciones), `tests/helpers.py` (tres), `tests/test_search.py` (una)
- Test: `tests/test_jira_team.py`

**Interfaces:**
- Produces: `Jira.search_capped(jql, cap, blocked_link=...) -> (List[dict], bool)` (a lo sumo `cap` issues y si había más); `Jira.group_total(name) -> int` (HTTP 404 como `JiraError` si el grupo no existe); cada issue de `search` trae `updated` (día `YYYY-MM-DD` o `None`).
- Produces (tests): `FakeJira.search_capped`, `FakeJira.group_total` y `FakeJira.groups` (`{"team": 7}`); `helpers.issue()` trae `updated`.

- [ ] **Step 1: Crear la rama de trabajo y confirmar la línea base**

```bash
cd Harness/jira-kanban
git switch docs/jira-em-fase-2      # main más este plan
git switch -c feat/jira-em-fase-2
python3 -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 327 tests ... OK`.

- [ ] **Step 2: Escribir los tests del cliente**

```python
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
```

Y la igualdad exacta de `test_search_normalizes_an_issue_and_follows_the_pages` ahora incluye `updated`:

Reemplazá en `tests/test_search.py` este texto:

```python
"created": "2026-10-01", "resolved": None, "changed": "2026-10-07", "flagged": True,
```

por este:

```python
"created": "2026-10-01", "resolved": None, "changed": "2026-10-07", "updated": None, "flagged": True,
```

- [ ] **Step 3: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_jira_team.py' 2>&1 | tail -4; python3 -m unittest discover -s tests -p 'test_search.py' 2>&1 | tail -4`
Expected: `test_jira_team.py` falla con 7 errores (`AttributeError: 'Jira' object has no attribute 'search_capped'` / `'group_total'` y `KeyError: 'updated'`); `test_search.py` falla en `test_search_normalizes_an_issue_and_follows_the_pages` porque el diccionario esperado ya trae `updated`.

- [ ] **Step 4: Implementar en el cliente**

Reemplazá en `jkan/jira.py` este texto:

```python
from typing import Callable, Dict, List, Optional
```

por este:

```python
from typing import Callable, Dict, List, Optional, Tuple
```

Reemplazá en `jkan/jira.py` este texto:

```python
"resolutiondate", "statuscategorychangedate", "issuelinks"]
```

por este:

```python
"resolutiondate", "statuscategorychangedate", "issuelinks", "updated"]
```

Reemplazá en `jkan/jira.py` este texto:

```python
"changed": _day(f.get("statuscategorychangedate")),
```

por este:

```python
"changed": _day(f.get("statuscategorychangedate")), "updated": _day(f.get("updated")),
```

Reemplazá en `jkan/jira.py` este texto:

```python
    def search(self, jql: str, blocked_link: str = BLOCKED_LINK) -> List[dict]:
        """Every issue the JQL finds, in the shape the reports use. Read only; follows the result pages."""
        flag = self._flag_field()
        fields = STANDUP_FIELDS + ([flag] if flag else [])
        found: List[dict] = []
        token = None
        while True:
            body = {"jql": jql, "fields": fields, "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = self._send("POST", "/rest/api/3/search/jql", body)
            found += [self._report_issue(raw, flag, blocked_link) for raw in page.get("issues", [])]
            token = page.get("nextPageToken")
            if not token:
                return found
```

por este:

```python
    def search(self, jql: str, blocked_link: str = BLOCKED_LINK) -> List[dict]:
        """Every issue the JQL finds, in the shape the reports use. Read only; follows the result pages."""
        return self._search(jql, blocked_link, None)[0]

    def search_capped(self, jql: str, cap: int, blocked_link: str = BLOCKED_LINK) -> Tuple[List[dict], bool]:
        """At most `cap` issues and whether Jira had more. Read only; stops asking for pages once it has enough."""
        return self._search(jql, blocked_link, cap)

    def _search(self, jql: str, blocked_link: str, cap: Optional[int]) -> Tuple[List[dict], bool]:
        flag = self._flag_field()
        fields = STANDUP_FIELDS + ([flag] if flag else [])
        found: List[dict] = []
        token = None
        while True:
            body = {"jql": jql, "fields": fields, "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = self._send("POST", "/rest/api/3/search/jql", body)
            found += [self._report_issue(raw, flag, blocked_link) for raw in page.get("issues", [])]
            token = page.get("nextPageToken")
            if cap is not None and len(found) >= cap:
                return found[:cap], bool(token) or len(found) > cap
            if not token:
                return found, False

    def group_total(self, name: str) -> int:
        """How many people a Jira group has; an unknown group is an HTTP 404 JiraError. Read only."""
        query = urllib.parse.urlencode({"groupname": name, "maxResults": 1})
        return int(self._send("GET", f"/rest/api/3/group/member?{query}").get("total", 0))
```

- [ ] **Step 5: Correrlos y ver que pasan**

Run: `python3 -m unittest discover -s tests -p 'test_jira_team.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_search.py' 2>&1 | tail -3`
Expected: `OK` en los dos.

- [ ] **Step 6: Ampliar el Jira falso para las tareas siguientes**

Reemplazá en `tests/helpers.py` este texto:

```python
"changed": "2026-09-01", "flagged": False, "blocked_by": []}
```

por este:

```python
"changed": "2026-09-01", "updated": "2026-09-01",
            "flagged": False, "blocked_by": []}
```

Reemplazá en `tests/helpers.py` este texto:

```python
        self.project_list: List[dict] = []  # what Jira.projects returns
```

por este:

```python
        self.project_list: List[dict] = []  # what Jira.projects returns
        self.groups: Dict[str, int] = {"team": 7}  # Jira group -> members
```

Reemplazá en `tests/helpers.py` este texto:

```python
    def update(self, key: str, fields: dict) -> None:
        for name in ("summary", "description"):
```

por este:

```python
    def search_capped(self, jql: str, cap: int, blocked_link: str = "is blocked by"):
        found = self.search(jql, blocked_link)
        return found[:cap], len(found) > cap

    def group_total(self, name: str) -> int:
        from jkan.jira import JiraError
        if name not in self.groups:
            raise JiraError(f"GET /rest/api/3/group/member: HTTP 404 no group {name}")
        return self.groups[name]

    def update(self, key: str, fields: dict) -> None:
        for name in ("summary", "description"):
```

- [ ] **Step 7: Suite completa y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
git add jkan/jira.py tests/helpers.py tests/test_jira_team.py tests/test_search.py
git commit -m "feat(jira): capped search, group size and the day an issue was last updated"
```

Expected: `OK`.

---

### Task 2: `jk board limit` y una sola escritura atómica

**Files:**
- Modify: `jkan/board_profile.py` (dos ediciones), `jkan/board_cli.py` (cuatro)
- Test: `tests/test_board_limit.py`

**Interfaces:**
- Produces: `board_profile.write_json(path, data) -> Path` (escritura atómica que no deja archivos temporales si falla); `board_profile.set_wip_limit(profile, value)` (entero de 1 o más, o `None`; si no, `BadSelection`); `jk board limit KEY N|none`; un perfil con `wip_limit` sin sentido es `BadProfile`.
- Consumes: `board_profile.save`, `_read`, `BadProfile` y `BadSelection` de la fase 1.

- [ ] **Step 1: Escribir los tests**

```python
"""jk board limit, the WIP limit in a profile, and the atomic JSON write views and profiles share."""
from __future__ import annotations

import contextlib
import io
import json
import unittest

import shapes
from helpers import FakeJira, config_dir
from jkan import board_profile as bp
from jkan import cli


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["board"] + args, client=lambda project: FakeJira())
    return code, out.getvalue(), err.getvalue()


class LimitCommandTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        bp.save(bp.build("PEHD", shapes.PEHD, None))

    def test_a_limit_is_saved_and_none_removes_it(self):
        code, out, _ = run(["limit", "PEHD", "3"])
        self.assertEqual((code, bp.load("PEHD")["wip_limit"]), (0, 3))
        self.assertIn("límite de WIP 3", out)
        self.assertEqual(run(["limit", "PEHD", "none"])[0], 0)
        self.assertIsNone(bp.load("PEHD")["wip_limit"])

    def test_anything_that_is_not_a_positive_whole_number_is_refused_and_changes_nothing(self):
        run(["limit", "PEHD", "3"])
        for bad in ("0", "-2", "1.5", "muchos", ""):
            code, _, err = run(["limit", "PEHD", bad])
            self.assertEqual(code, 1, bad)
            self.assertTrue(err.strip(), bad)
        self.assertEqual(bp.load("PEHD")["wip_limit"], 3)

    def test_a_limit_needs_a_profile(self):
        code, _, err = run(["limit", "UA", "3"])
        self.assertEqual(code, 1)
        self.assertIn("run jk board setup UA", err)

    def test_setup_again_keeps_the_limit(self):
        run(["limit", "PEHD", "4"])
        jira = FakeJira()
        jira.status_groups = {"PEHD": shapes.PEHD}
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main(["board", "setup", "PEHD"], client=lambda project: jira)
        self.assertEqual(bp.load("PEHD")["wip_limit"], 4)


class ProfileLimitTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_set_wip_limit_accepts_a_positive_whole_number_or_none(self):
        profile = bp.build("PEHD", shapes.PEHD, None)
        self.assertEqual(bp.set_wip_limit(profile, 2)["wip_limit"], 2)
        self.assertIsNone(bp.set_wip_limit(profile, None)["wip_limit"])
        for bad in (0, -1, True, 1.5, "3"):
            with self.assertRaises(bp.BadSelection, msg=repr(bad)):
                bp.set_wip_limit(profile, bad)

    def test_a_profile_file_with_a_nonsense_limit_is_not_a_profile(self):
        profile = bp.build("PEHD", shapes.PEHD, None)
        profile["wip_limit"] = "muchos"
        bp.save(profile)
        with self.assertRaisesRegex(bp.BadProfile, "wrong shape"):
            bp.load("PEHD")
        self.assertEqual(bp.load_all(), {})


class WriteJsonTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_a_failed_write_leaves_neither_the_new_file_nor_a_temporary_one(self):
        target = self.base / "x" / "a.json"
        bp.write_json(target, {"ok": 1})
        with self.assertRaises(TypeError):
            bp.write_json(target, {"bad": object()})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": 1})
        self.assertEqual([p.name for p in target.parent.iterdir()], ["a.json"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_board_limit.py' 2>&1 | tail -4`
Expected: los 7 tests fallan: `jk board limit` todavía no existe y `set_wip_limit` / `write_json` tampoco.

- [ ] **Step 3: Implementar en `board_profile.py`**

Reemplazá en `jkan/board_profile.py` este texto:

```python
def save(profile: dict, base: Optional[Path] = None) -> Path:
    path = path_of(profile["project"], base)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return path
```

por este:

```python
def _wip_ok(value) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 1)


def set_wip_limit(profile: dict, value: Optional[int]) -> dict:
    """The most work a person should have in flight on this board; None means no limit."""
    if not _wip_ok(value):
        raise BadSelection("the WIP limit must be a whole number of 1 or more, or none")
    profile["wip_limit"] = value
    return profile


def write_json(path: Path, data: dict) -> Path:
    """Write `data` as JSON atomically (a temporary file in the same folder, then a rename); no stray file on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def save(profile: dict, base: Optional[Path] = None) -> Path:
    return write_json(path_of(profile["project"], base), profile)
```

Reemplazá en `jkan/board_profile.py` este texto:

```python
    if not (data.get("project") == path.stem and isinstance(statuses, list)
```

por este:

```python
    if not (data.get("project") == path.stem and isinstance(statuses, list) and _wip_ok(data.get("wip_limit"))
```

- [ ] **Step 4: Implementar `jk board limit`**

Reemplazá en `jkan/board_cli.py` este texto:

```python
VERBS = ("setup", "set", "show", "check", "survey")
```

por este:

```python
VERBS = ("setup", "set", "show", "check", "survey", "limit")
```

Reemplazá en `jkan/board_cli.py` este texto:

```python
def _show(args) -> int:
```

por este:

```python
def _limit(args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    text = args.value.strip().lower()
    try:
        value = None if text == "none" else int(text)
    except ValueError:
        sys.stderr.write(f"the WIP limit must be a whole number or none, not {args.value!r}\n")
        return FINDINGS
    try:
        board_profile.set_wip_limit(profile, value)
    except board_profile.BadSelection as exc:
        sys.stderr.write(f"{exc}\n")
        return FINDINGS
    board_profile.save(profile)
    print(f"{args.key}: límite de WIP {'sin límite' if value is None else value}.")
    return OK


def _show(args) -> int:
```

Reemplazá en `jkan/board_cli.py` este texto:

```python
    for name, text in (("show", "print the saved profile")
```

por este:

```python
    cap = sub.add_parser("limit", help="set how much work a person may have in flight on this board (the WIP limit), or none")
    cap.add_argument("key")
    cap.add_argument("value", help="a whole number of 1 or more, or none")
    for name, text in (("show", "print the saved profile")
```

Reemplazá en `jkan/board_cli.py` este texto:

```python
        if args.verb == "show":
            return _show(args)
```

por este:

```python
        if args.verb == "limit":
            return _limit(args)
        if args.verb == "show":
            return _show(args)
```

- [ ] **Step 5: Correrlos y ver que pasan, y suite completa**

Run: `python3 -m unittest discover -s tests -p 'test_board_limit.py' 2>&1 | tail -3; python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` en los dos.

- [ ] **Step 6: Commit**

```bash
git add jkan/board_profile.py jkan/board_cli.py tests/test_board_limit.py
git commit -m "feat(board): jk board limit; profiles and views share one atomic JSON writer"
```

---

### Task 3: Views y consultas por rol

**Files:**
- Modify: `jkan/queries.py` (cuatro ediciones), `tests/test_boundaries.py` (una)
- Create: `jkan/views.py`, `tests/team_fixtures.py`
- Test: `tests/test_views.py`, `tests/test_queries_team.py`

**Interfaces:**
- Produces: `views.build(name, boards, team=None, stalled_days=7) -> view`, `views.save(view)`, `views.load(name)`, `views.names()`, `views.path_of(name)`, `class BadView(ValueError)`. Forma del view: `{"version", "name", "boards": [KEY], "team": None | {"group": str} | {"people": [{"id", "name"}]}, "stalled_days"}`.
- Produces: `queries.team_open(boards, profiles, team) -> jql`, `queries.team_closed(boards, profiles, team, wanted, since) -> jql | None`, `queries.team_created(boards, since, until) -> jql`, `queries.team_scope(team, include_unassigned=False) -> str | None`, `queries.GROUP`, `queries._scope` acepta una clave o una lista.
- Produces (tests): `team_fixtures` con los perfiles `TEAM` (flujo, ids 1 a 6) y `DESK` (mesa de ayuda, ids 11 a 16), `at(key, role, **over)`, `answers(open_, delivered, dropped, created)`, `view()`, `TODAY`.
- Consumes: `board_profile.set_wip_limit` y `write_json` (Task 2), `board_profile.KEY`, `roles.CLOSED`, `shapes.status`.

- [ ] **Step 1: Escribir los fixtures y los tests**

```python
"""Fixtures for the team report tests: two boards with profiles (a flow board TEAM and a help desk DESK), issues that
carry the role of their status, and a router that answers each kind of query the team reports make."""
from __future__ import annotations

from datetime import date

import shapes
from helpers import issue
from jkan import board_profile, roles, views

TODAY = date(2026, 10, 8)  # a Thursday; its week starts on 2026-10-05
ANA = {"id": "acc-ana", "name": "Ana Gómez"}
BETO = {"id": "acc-beto", "name": "Beto Ruiz"}

STATUSES = (("todo", "Backlog", "todo"), ("active", "En curso", "in_progress"), ("blocked", "Blocked", "in_progress"),
            ("waiting", "Esperando al cliente", "in_progress"), ("delivered", "Done", "done"),
            ("dropped", "Cancelado", "done"))
BASE = {"TEAM": 0, "DESK": 10}  # status ids: TEAM 1-6, DESK 11-16
IDS = {role: n + 1 for n, (role, _, _) in enumerate(STATUSES)}


def groups(offset: int) -> list:
    return [{"types": ["Tarea"], "statuses": [shapes.status(offset + n + 1, name, category)
                                                for n, (_, name, category) in enumerate(STATUSES)]}]


def profile(project: str, kind: str = "flow", wip_limit=None, decide_waiting: bool = True) -> dict:
    prof = board_profile.build(project, groups(BASE[project]), kind)
    if decide_waiting:
        board_profile.assign(prof, "waiting", ["Esperando al cliente"])
    return board_profile.set_wip_limit(prof, wip_limit)


def profiles(**limits) -> dict:
    return {"TEAM": profile("TEAM", wip_limit=limits.get("TEAM")), "DESK": profile("DESK", kind="helpdesk")}


def view(boards=("TEAM", "DESK"), team=None, name="plataforma", stalled_days=7) -> dict:
    return views.build(name, list(boards), {"group": "team"} if team is None else team, stalled_days)


def at(key: str, role, **over) -> dict:
    """An issue in the status that plays `role` on its board, already annotated (as team._fetch leaves it)."""
    project = roles.project_of(key)
    if role is None:  # a status the profile has not decided
        fields = {"status": "Revisión", "status_id": str(BASE[project] + 90), "category": "in_progress"}
    else:
        _, name, category = STATUSES[IDS[role] - 1]
        fields = {"status": name, "status_id": str(BASE[project] + IDS[role]), "category": category}
    fields.update(role=role, role_source="profile")
    fields.update(over)
    return issue(key, **fields)


def answers(open_=(), delivered=(), dropped=(), created=()):
    """A FakeJira.search_answer: tells the four kinds of team query apart by their text."""
    def answer(jql: str) -> list:
        if "created >=" in jql:
            return list(created)
        if "updated >=" in jql:
            return list(delivered if "status in (5)" in jql else dropped)
        return list(open_)
    return answer
```

```python
from __future__ import annotations

import unittest

from helpers import config_dir
from jkan import views


class BuildTest(unittest.TestCase):
    def test_a_view_keeps_what_it_was_given(self):
        view = views.build("plataforma", ["PLATE", "UA"], {"group": "team"}, 5)
        self.assertEqual(view, {"version": 1, "name": "plataforma", "boards": ["PLATE", "UA"],
                                "team": {"group": "team"}, "stalled_days": 5})
        self.assertIsNone(views.build("solo", ["UA"])["team"])

    def test_a_name_is_lower_case_letters_digits_dash_and_underscore(self):
        for bad in ("", "Plat", "a b", "../x", "a\n", "x" * 41, "-x"):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build(bad, ["UA"])
        views.build("equipo-2_a", ["UA"])

    def test_boards_are_a_list_of_distinct_project_keys(self):
        for bad in ([], "PLATE", ["plate"], ["UA", "UA"], ["UA\n"], [1]):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build("v", bad)

    def test_the_team_is_a_group_or_a_list_of_people_and_nothing_that_can_alter_a_query(self):
        views.build("v", ["UA"], {"people": [{"id": "acc-1", "name": "Ana"}]})
        for bad in ({"group": 'x") OR 1=1 --'}, {"group": ""}, {"people": []}, {"people": [{"id": "a b", "name": "x"}]},
                    {"people": [{"id": 'a"b', "name": "x"}]}, {"group": "g", "people": [{"id": "a", "name": "x"}]},
                    {"other": 1}, "platform", {}):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build("v", ["UA"], bad)

    def test_stalled_days_is_a_whole_number_from_1_to_365(self):
        for bad in (0, 366, True, "7", 1.5, None):
            with self.assertRaises(views.BadView, msg=repr(bad)):
                views.build("v", ["UA"], None, bad)
        views.build("v", ["UA"], None, 1)
        views.build("v", ["UA"], None, 365)


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def write(self, name, text):
        (self.base / "views").mkdir(exist_ok=True)
        (self.base / "views" / f"{name}.json").write_text(text, encoding="utf-8")

    def test_save_then_load_gives_back_the_same_view(self):
        view = views.build("plataforma", ["PLATE", "UA"], {"group": "team"})
        path = views.save(view)
        self.assertEqual(path, self.base / "views" / "plataforma.json")
        self.assertEqual(views.load("plataforma"), view)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["plataforma.json"])

    def test_a_view_that_does_not_exist_says_how_to_make_it(self):
        with self.assertRaisesRegex(views.BadView, "jk team setup nada --boards"):
            views.load("nada")

    def test_a_file_that_is_not_a_view_is_refused_with_its_name(self):
        wrong = ["{not json", "[1]", "{}", '{"version": "1"}', '{"version": 1, "name": "otro", "boards": ["UA"]}',
                 '{"version": 1, "name": "v", "boards": "UA", "team": null, "stalled_days": 7}',
                 '{"version": 1, "name": "v", "boards": ["UA"], "team": null}',
                 '{"version": 1, "name": "v", "boards": ["UA"], "team": {"group": "x\\") OR 1=1"}, "stalled_days": 7}']
        for text in wrong:
            self.write("v", text)
            with self.assertRaisesRegex(views.BadView, "v.json"):
                views.load("v")

    def test_a_view_from_a_newer_jk_is_refused(self):
        self.write("v", '{"version": 2, "name": "v"}')
        with self.assertRaisesRegex(views.BadView, "newer jk"):
            views.load("v")

    def test_names_lists_the_saved_views_in_order_and_ignores_anything_else(self):
        for name in ("zeta", "alfa"):
            views.save(views.build(name, ["UA"]))
        self.write("Bad Name", "{}")
        self.assertEqual(views.names(), ["alfa", "zeta"])

    def test_names_of_a_missing_folder_is_empty(self):
        self.assertEqual(views.names(), [])


if __name__ == "__main__":
    unittest.main()
```

```python
from __future__ import annotations

import unittest
from datetime import date

import team_fixtures as fx
from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import queries

GROUP = {"group": "team"}


class TeamQueriesTest(unittest.TestCase):
    def test_open_work_is_everything_not_closed_in_each_board_for_the_team_or_nobody(self):
        jql = queries.team_open(["TEAM", "DESK"], fx.profiles(), GROUP)
        self.assertEqual(jql, '((project = TEAM AND status not in (5, 6)) OR (project = DESK AND status not in (15, 16)))'
                              ' AND (assignee in membersOf("team") OR assignee is EMPTY)'
                              ' ORDER BY updated DESC')

    def test_a_board_with_no_closed_status_is_asked_whole(self):
        only_open = {"OPEN": {"statuses": [{"id": "1", "role": "todo"}, {"id": "2", "role": "active"}]}}
        self.assertEqual(queries.team_open(["OPEN"], only_open, None), "((project = OPEN)) ORDER BY updated DESC")

    def test_without_a_team_nobody_is_filtered_out(self):
        jql = queries.team_open(["TEAM"], fx.profiles(), None)
        self.assertEqual(jql, "((project = TEAM AND status not in (5, 6))) ORDER BY updated DESC")

    def test_people_become_quoted_account_ids(self):
        team = {"people": [{"id": "acc-1", "name": "Ana"}, {"id": "acc-2", "name": "Beto"}]}
        self.assertIn('(assignee in ("acc-1", "acc-2") OR assignee is EMPTY)', queries.team_open(["TEAM"], fx.profiles(), team))
        self.assertTrue(queries.team_closed(["TEAM"], fx.profiles(), team, ("delivered",), date(2026, 9, 1))
                        .endswith('AND assignee in ("acc-1", "acc-2") ORDER BY updated DESC'))

    def test_closed_work_names_the_statuses_and_the_day_and_asks_for_the_team_only(self):
        jql = queries.team_closed(["TEAM", "DESK"], fx.profiles(), GROUP, ("delivered",), date(2026, 9, 1))
        self.assertEqual(jql, '((project = TEAM AND status in (5)) OR (project = DESK AND status in (15)))'
                              ' AND updated >= "2026-09-01" AND assignee in membersOf("team")'
                              ' ORDER BY updated DESC')
        dropped = queries.team_closed(["TEAM"], fx.profiles(), GROUP, ("dropped",), date(2026, 9, 1))
        self.assertIn("status in (6)", dropped)

    def test_closed_work_is_none_when_no_board_has_such_a_status(self):
        only_open = {"OPEN": {"statuses": [{"id": "1", "role": "todo"}]}}
        self.assertIsNone(queries.team_closed(["OPEN"], only_open, GROUP, ("delivered",), date(2026, 9, 1)))

    def test_created_covers_the_last_day_too(self):
        jql = queries.team_created(["TEAM", "DESK"], date(2026, 10, 1), date(2026, 10, 8))
        self.assertEqual(jql, 'project in (TEAM, DESK) AND created >= "2026-10-01" AND created < "2026-10-09"'
                              ' ORDER BY created DESC')

    def test_ids_are_sorted_as_numbers_not_as_text(self):
        prof = {"X": {"statuses": [{"id": "10", "role": "delivered"}, {"id": "9", "role": "dropped"}]}}
        self.assertIn("status not in (9, 10)", queries.team_open(["X"], prof, None))

    def test_nothing_from_outside_reaches_the_query(self):
        bad_status = {"X": {"statuses": [{"id": "1) OR (1=1", "role": "delivered"}]}}
        with self.assertRaisesRegex(ValueError, "not status ids"):
            queries.team_open(["X"], bad_status, None)
        with self.assertRaisesRegex(ValueError, "not a project key"):
            queries.team_open(["x y"], {"x y": {"statuses": []}}, None)
        with self.assertRaisesRegex(ValueError, "not a group name"):
            queries.team_scope({"group": 'g") OR (1=1'})
        with self.assertRaisesRegex(ValueError, "not account ids"):
            queries.team_scope({"people": [{"id": 'a" OR "1"="1', "name": "x"}]})
        with self.assertRaisesRegex(ValueError, "not a project key"):
            queries.team_created(["UA", "u a"], date(2026, 10, 1), date(2026, 10, 2))

    def test_no_team_means_no_scope(self):
        self.assertIsNone(queries.team_scope(None))
        self.assertIsNone(queries.team_scope({}))


class ScopeTest(unittest.TestCase):
    def test_a_single_project_reads_as_before(self):
        jql = queries.open_of(None, "PLATE")
        self.assertIn(" AND project = PLATE ", jql)

    def test_a_list_of_projects_is_an_in_clause(self):
        jql = queries.changed_in(None, date(2026, 10, 1), date(2026, 10, 7), ["PLATE", "UA"])
        self.assertIn(" AND project in (PLATE, UA) ", jql)
        self.assertIn(" AND project = UA ", queries.open_of(None, ["UA"]))

    def test_every_key_of_the_list_is_checked(self):
        with self.assertRaisesRegex(ValueError, "not a project key"):
            queries.open_of(None, ["PLATE", "x; drop"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_views.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_queries_team.py' 2>&1 | tail -3`
Expected: `ImportError: cannot import name 'views' from 'jkan'` en los dos (`team_fixtures` importa `views`).

- [ ] **Step 3: Las consultas por rol**

Reemplazá en `jkan/queries.py` este texto:

```python
from typing import Iterable, Optional
```

por este:

```python
from typing import Dict, Iterable, List, Optional, Union
```

Reemplazá en `jkan/queries.py` este texto:

```python
ACCOUNT = re.compile(r"^[A-Za-z0-9:_-]+$")
```

por este:

```python
ACCOUNT = re.compile(r"^[A-Za-z0-9:_-]+$")
GROUP = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._@:-]{0,99}")
STATUS_ID = re.compile(r"\d+")
```

Reemplazá en `jkan/queries.py` este texto:

```python
def _scope(project: Optional[str]) -> str:
    if not project:
        return ""
    if not PROJECT.match(project):
        raise ValueError(f"not a project key: {project!r}")
    return f" AND project = {project}"
```

por este:

```python
def _scope(project: Optional[Union[str, List[str]]]) -> str:
    """One project key, or a view's list of them."""
    if not project:
        return ""
    keys = [project] if isinstance(project, str) else list(project)
    for key in keys:
        if not PROJECT.match(key):
            raise ValueError(f"not a project key: {key!r}")
    return f" AND project = {keys[0]}" if len(keys) == 1 else f" AND project in ({', '.join(keys)})"
```

Reemplazá en `jkan/queries.py` este texto:

```python
def by_keys(keys: Iterable[str]) -> str:
    return f"key in ({_keys(keys)})"
```

por este:

```python
def by_keys(keys: Iterable[str]) -> str:
    return f"key in ({_keys(keys)})"


# ---- team reports: JQL built from the roles of each board's profile -------------------------------------------------

def _id_list(ids: Iterable[str]) -> str:
    ids = set(ids)
    bad = sorted(i for i in ids if not STATUS_ID.fullmatch(i))
    if bad:
        raise ValueError(f"not status ids: {bad}")
    return ", ".join(sorted(ids, key=int))


def _board(board: str) -> str:
    if not PROJECT.fullmatch(board):
        raise ValueError(f"not a project key: {board!r}")
    return board


def _ids_with(profile: dict, wanted: Iterable[str]) -> List[str]:
    return [s["id"] for s in profile["statuses"] if s["role"] in wanted]


def team_scope(team: Optional[dict], include_unassigned: bool = False) -> Optional[str]:
    """JQL for "assigned to the team"; None when the view has no team (everybody counts)."""
    if not team:
        return None
    if "group" in team:
        if not GROUP.fullmatch(team["group"]):
            raise ValueError(f"not a group name: {team['group']!r}")
        clause = f'assignee in membersOf("{team["group"]}")'
    else:
        ids = [p["id"] for p in team["people"]]
        bad = [i for i in ids if not ACCOUNT.fullmatch(i)]
        if bad:
            raise ValueError(f"not account ids: {bad}")
        clause = "assignee in (" + ", ".join(f'"{i}"' for i in ids) + ")"
    return f"({clause} OR assignee is EMPTY)" if include_unassigned else clause


def team_open(boards: List[str], profiles: Dict[str, dict], team: Optional[dict]) -> str:
    """Open work in the boards: everything that is not delivered or dropped, so statuses without a role come back too
    (as «sin rol»). The team's work and what nobody owns; the ids go unquoted, which is what Jira reads as ids."""
    parts = []
    for board in boards:
        closed = _ids_with(profiles[board], ("delivered", "dropped"))
        parts.append(f"(project = {_board(board)} AND status not in ({_id_list(closed)}))" if closed
                     else f"(project = {_board(board)})")
    scope = team_scope(team, include_unassigned=True)
    return "(" + " OR ".join(parts) + ")" + (f" AND {scope}" if scope else "") + " ORDER BY updated DESC"


def team_closed(boards: List[str], profiles: Dict[str, dict], team: Optional[dict], wanted: Iterable[str],
                since: _dt.date) -> Optional[str]:
    """Issues in a status whose role is in `wanted` (delivered, dropped) and updated since a day, assigned to the team.
    None when no board has such a status. `updated` is a superset of the delivery day: the report narrows it."""
    parts = []
    for board in boards:
        ids = _ids_with(profiles[board], tuple(wanted))
        if ids:
            parts.append(f"(project = {_board(board)} AND status in ({_id_list(ids)}))")
    if not parts:
        return None
    scope = team_scope(team)
    return ("(" + " OR ".join(parts) + f') AND updated >= "{since.isoformat()}"' + (f" AND {scope}" if scope else "")
            + " ORDER BY updated DESC")


def team_created(boards: List[str], since: _dt.date, until: _dt.date) -> str:
    projects = ", ".join(_board(b) for b in boards)
    return (f'project in ({projects}) AND created >= "{since.isoformat()}" '
            f'AND created < "{(until + _dt.timedelta(days=1)).isoformat()}" ORDER BY created DESC')
```

- [ ] **Step 4: Los views**

```python
"""Views: the boards and the team a manager follows. One JSON per view under ~/.config/jk/views/ (or
$JK_CONFIG_DIR/views/). Written only by `jk team setup`; the team reports read them."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from . import board_profile, queries

VERSION = 1
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


class BadView(ValueError):
    pass


def path_of(name: str, base: Optional[Path] = None) -> Path:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise BadView(f"not a view name: {name!r} (lower case letters, digits, - and _)")
    return (base or board_profile.config_dir()) / "views" / f"{name}.json"


def _check_team(team) -> None:
    if not isinstance(team, dict) or len(team) != 1:
        raise BadView("team must be {group: NAME} or {people: [{id, name}]}")
    if "group" in team:
        if not isinstance(team["group"], str) or not queries.GROUP.fullmatch(team["group"]):
            raise BadView(f"not a group name: {team['group']!r}")
    elif "people" in team:
        people = team["people"]
        if not (isinstance(people, list) and people and all(
                isinstance(p, dict) and isinstance(p.get("id"), str) and queries.ACCOUNT.fullmatch(p["id"])
                and isinstance(p.get("name"), str) for p in people)):
            raise BadView("people must be a non-empty list of {id, name}")
    else:
        raise BadView("team must be {group: NAME} or {people: [{id, name}]}")


def build(name: str, boards, team=None, stalled_days=7) -> dict:
    """A view, checked: every value that later goes into a JQL query is validated here, once."""
    path_of(name)
    if not isinstance(boards, list) or not boards:
        raise BadView("a view needs at least one board")
    for board in boards:
        if not isinstance(board, str) or not board_profile.KEY.fullmatch(board):
            raise BadView(f"not a project key: {board!r}")
    if len(set(boards)) != len(boards):
        raise BadView("a board is listed twice")
    if team is not None:
        _check_team(team)
    if isinstance(stalled_days, bool) or not isinstance(stalled_days, int) or not 1 <= stalled_days <= 365:
        raise BadView("stalled days must be a whole number from 1 to 365")
    return {"version": VERSION, "name": name, "boards": list(boards), "team": team, "stalled_days": stalled_days}


def save(view: dict, base: Optional[Path] = None) -> Path:
    return board_profile.write_json(path_of(view["name"], base), view)


def load(name: str, base: Optional[Path] = None) -> dict:
    path = path_of(name, base)
    if not path.is_file():
        raise BadView(f"no view {name!r}: run jk team setup {name} --boards KEY[,KEY...]")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BadView(f"{path.name} is not valid JSON ({exc.msg})") from exc
    version = data.get("version") if isinstance(data, dict) else None
    if isinstance(version, bool) or not isinstance(version, int):
        raise BadView(f"{path.name} is not a view")
    if version > VERSION:
        raise BadView(f"{path.name} was written by a newer jk (view version {version}); update jk")
    if data.get("name") != name:
        raise BadView(f"{path.name} is not a view (wrong name)")
    try:
        return build(name, data.get("boards"), data.get("team"), data.get("stalled_days"))
    except BadView as exc:
        raise BadView(f"{path.name} is not a view ({exc})") from exc


def names(base: Optional[Path] = None) -> List[str]:
    folder = (base or board_profile.config_dir()) / "views"
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if NAME.fullmatch(p.stem))
```

- [ ] **Step 5: Clasificar los módulos nuevos en el test de fronteras**

Los cuatro módulos de esta fase (`views`, `team`, `team_render`, `team_cli`) son del lado de lectura. Se declaran ahora aunque tres todavía no existan: el test solo mira los que existen.

Reemplazá en `tests/test_boundaries.py` este texto:

```python
READ = {"window", "queries", "standup", "stats", "render", "roles", "board_profile", "board_cli"}
```

por este:

```python
READ = {"window", "queries", "standup", "stats", "render", "roles", "board_profile", "board_cli", "views", "team",
        "team_render", "team_cli"}
```

- [ ] **Step 6: Correrlos y ver que pasan**

Run: `python3 -m unittest discover -s tests -p 'test_views.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_queries_team.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_boundaries.py' 2>&1 | tail -3`
Expected: `OK` en los tres.

- [ ] **Step 7: Suite completa y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
git add jkan/queries.py jkan/views.py tests/team_fixtures.py tests/test_views.py tests/test_queries_team.py tests/test_boundaries.py
git commit -m "feat(views): saved boards-and-team views; JQL built from the roles of each profile"
```

---

### Task 4: Los reportes como funciones puras

**Files:**
- Create: `jkan/team.py`
- Test: `tests/test_team.py`

**Interfaces:**
- Consumes: `queries.team_open/team_closed/team_created` (Task 3), `roles.annotate/role_of/project_of/CLOSED`, `standup.blockers`, `stats.throughput/lead_days/spread/wip/week_of`, `Jira.search_capped` (Task 1), `team_fixtures` (Task 3).
- Produces: `team.CAP = 1000`, `team.NoDesk`, `delivery_day(issue)`, `first_week(today, weeks)`, `missing_profiles(view, profiles)`, `gather_open(jira, view, profiles, conv) -> (issues, truncated)`, `gather_closed(jira, view, profiles, conv, wanted, since)`, `gather_created(jira, view, profiles, conv, since, until)`, `status_report`, `stalled_report`, `blocked_report`, `flow_report`, `digest_report`, `desk_boards`, `desk_report`, `rollup_row`.

- [ ] **Step 1: Escribir los tests**

```python
from __future__ import annotations

import unittest
from datetime import date

import team_fixtures as fx
from helpers import CONVENTIONS, FakeJira, config_dir, issue
from jkan import team

TODAY = fx.TODAY
VIEW = fx.view()


class StatusReportTest(unittest.TestCase):
    def setUp(self):
        self.profiles = fx.profiles(TEAM=2)
        self.report = team.status_report(
            [fx.at("TEAM-1", "todo", assignee=fx.ANA), fx.at("TEAM-2", "active", assignee=fx.ANA),
             fx.at("TEAM-3", "blocked", assignee=fx.ANA), fx.at("TEAM-4", "waiting", assignee=fx.BETO),
             fx.at("TEAM-5", "todo", assignee=None), fx.at("TEAM-6", None, assignee=fx.BETO),
             fx.at("DESK-1", "active", assignee=fx.ANA)], VIEW, self.profiles)

    def test_each_board_counts_its_roles_the_unowned_and_what_has_no_role(self):
        team_board, desk_board = self.report["boards"]
        self.assertEqual({k: team_board[k] for k in ("board", "n", "todo", "active", "blocked", "waiting", "none", "unassigned")},
                         {"board": "TEAM", "n": 6, "todo": 2, "active": 1, "blocked": 1, "waiting": 1, "none": 1, "unassigned": 1})
        self.assertEqual((desk_board["board"], desk_board["n"], desk_board["active"]), ("DESK", 1, 1))
        self.assertEqual(self.report["n"], 7)

    def test_each_person_per_board_with_wip_and_the_room_the_limit_leaves(self):
        rows = {(r["person"], r["board"]): r for r in self.report["people"]}
        self.assertEqual(list(rows), [("Ana Gómez", "DESK"), ("Ana Gómez", "TEAM"), ("Beto Ruiz", "TEAM")])
        ana = rows[("Ana Gómez", "TEAM")]
        self.assertEqual((ana["n"], ana["wip"], ana["wip_limit"], ana["room"]), (3, 2, 2, 0))  # active + blocked
        self.assertEqual((rows[("Ana Gómez", "DESK")]["wip_limit"], rows[("Ana Gómez", "DESK")]["room"]), (None, None))
        beto = rows[("Beto Ruiz", "TEAM")]
        self.assertEqual((beto["wip"], beto["none"], beto["room"]), (1, 1, 1))  # waiting counts; «sin rol» does not

    def test_the_unowned_do_not_appear_as_a_person(self):
        self.assertNotIn(None, [r["person"] for r in self.report["people"]])


class StalledReportTest(unittest.TestCase):
    def issues(self):
        return [fx.at("TEAM-1", "active", changed="2026-09-20", updated="2026-10-07"),
                fx.at("TEAM-2", "active", changed="2026-10-05"),
                fx.at("TEAM-3", "blocked", changed="2026-08-01"),
                fx.at("TEAM-4", "active", changed=None),
                fx.at("TEAM-5", "active", changed="2026-09-20", updated=None)]

    def test_only_active_work_that_has_not_changed_category_for_the_days_asked(self):
        report = team.stalled_report(self.issues(), TODAY, 7)
        self.assertEqual([r["issue"]["key"] for r in report["rows"]], ["TEAM-1", "TEAM-5"])
        self.assertEqual((report["days"], report["n_active"]), (7, 4))

    def test_it_shows_the_days_in_the_category_and_the_days_since_the_last_edit_apart(self):
        first, second = team.stalled_report(self.issues(), TODAY, 7)["rows"]
        self.assertEqual((first["days_in_category"], first["days_since_edit"]), (18, 1))
        self.assertIsNone(second["days_since_edit"])

    def test_a_lower_threshold_brings_more_and_the_oldest_comes_first(self):
        rows = team.stalled_report(self.issues(), TODAY, 3)["rows"]
        self.assertEqual([r["issue"]["key"] for r in rows], ["TEAM-1", "TEAM-5", "TEAM-2"])


class BlockedReportTest(unittest.TestCase):
    def test_blocked_by_role_flag_or_link_and_waiting_apart_and_closed_never(self):
        linked = fx.at("TEAM-2", "active", changed="2026-10-01",
                       blocked_by=[{"key": "UA-9", "summary": "Okta", "status": "En curso", "category": "in_progress",
                                    "assignee": "Ana"}])
        report = team.blocked_report(
            [fx.at("TEAM-1", "blocked", changed="2026-09-28"), linked, fx.at("TEAM-3", "todo", flagged=True, changed="2026-10-07"),
             fx.at("TEAM-4", "waiting", changed="2026-10-02"), fx.at("TEAM-5", "delivered", flagged=True),
             fx.at("TEAM-6", "active")], CONVENTIONS, TODAY)
        self.assertEqual([(r["issue"]["key"], r["by"]) for r in report["blocked"]],
                         [("TEAM-1", "Estado Blocked, sin link"), ("TEAM-2", "UA-9"), ("TEAM-3", "Flagged, sin link")])
        self.assertEqual([r["issue"]["key"] for r in report["waiting"]], ["TEAM-4"])
        self.assertEqual(report["blocked"][0]["days"], 10)

    def test_the_conventions_list_of_blocked_statuses_does_not_apply_to_a_profiled_board(self):
        in_blocked_status_name = fx.at("TEAM-1", "active", status="Blocked")
        self.assertEqual(team.blocked_report([in_blocked_status_name], CONVENTIONS, TODAY)["blocked"], [])


class FlowReportTest(unittest.TestCase):
    def test_deliveries_are_counted_by_their_delivery_day_inside_the_weeks_asked(self):
        delivered = [fx.at("TEAM-1", "delivered", resolved="2026-10-06"), fx.at("TEAM-2", "delivered", resolved="2026-09-29"),
                     fx.at("TEAM-3", "delivered", resolved="2026-09-20"),
                     fx.at("TEAM-4", "delivered", resolved=None, changed="2026-10-07")]
        dropped = [fx.at("TEAM-5", "dropped", changed="2026-10-01"), fx.at("TEAM-6", "dropped", changed="2026-09-01")]
        open_ = [fx.at("TEAM-7", "active", changed="2026-09-30")]
        report = team.flow_report(delivered, dropped, open_, TODAY, 2)
        self.assertEqual((report["since"], report["delivered_n"], report["dropped_n"]), ("2026-09-28", 3, 1))
        self.assertEqual([(w["week"], w["closed"], w["partial"]) for w in report["weekly"]],
                         [("2026-09-28", 1, False), ("2026-10-05", 2, True)])
        self.assertEqual([r["issue"]["key"] for r in report["wip"]], ["TEAM-7"])

    def test_lead_time_goes_from_creation_to_delivery_with_its_n(self):
        delivered = [fx.at("TEAM-1", "delivered", created="2026-10-01", resolved="2026-10-06"),
                     fx.at("TEAM-2", "delivered", created="2026-09-01", resolved="2026-09-29")]
        lead = team.flow_report(delivered, [], [], TODAY, 2)["lead"]
        self.assertEqual((lead["n"], lead["median"], lead["p85"]), (2, 5, 28))

    def test_nothing_delivered_has_no_lead_time(self):
        self.assertIsNone(team.flow_report([], [], [], TODAY, 4)["lead"])


class DigestReportTest(unittest.TestCase):
    def test_the_period_lists_what_was_delivered_dropped_and_created_and_today_s_blocked_and_stalled(self):
        report = team.digest_report(
            [fx.at("TEAM-1", "delivered", resolved="2026-10-02"), fx.at("TEAM-2", "delivered", resolved="2026-09-30")],
            [fx.at("TEAM-3", "dropped", changed="2026-10-08"), fx.at("TEAM-4", "dropped", changed="2026-10-09")],
            [fx.at("TEAM-5", "todo", created="2026-10-01"), fx.at("TEAM-6", "todo", created="2026-09-30")],
            [fx.at("TEAM-7", "blocked"), fx.at("TEAM-8", "waiting"), fx.at("TEAM-9", "active", changed="2026-09-01")],
            CONVENTIONS, date(2026, 10, 1), date(2026, 10, 8), TODAY, 7)
        self.assertEqual(([i["key"] for i in report["delivered"]], [i["key"] for i in report["dropped"]],
                          [i["key"] for i in report["created"]]), (["TEAM-1"], ["TEAM-3"], ["TEAM-5"]))
        self.assertEqual((report["blocked_now"], report["waiting_now"], report["stalled_now"]), (1, 1, 1))
        self.assertEqual((report["since"], report["until"]), ("2026-10-01", "2026-10-08"))


class DeskReportTest(unittest.TestCase):
    def setUp(self):
        self.profiles = fx.profiles()
        self.open = [fx.at("DESK-1", "todo", created="2026-10-07"), fx.at("DESK-2", "active", created="2026-10-01"),
                     fx.at("DESK-3", "blocked", created="2026-09-20"), fx.at("DESK-4", "waiting", created="2026-08-01"),
                     fx.at("DESK-5", "todo", created="2026-09-30", assignee=None), fx.at("TEAM-1", "todo")]
        self.delivered = [fx.at("DESK-9", "delivered", created="2026-10-01", resolved="2026-10-05"),
                          fx.at("DESK-8", "delivered", created="2026-08-01", resolved="2026-08-02")]

    def test_only_help_desk_boards_are_reported_and_what_waits_for_a_third_party_is_not_aged(self):
        report = team.desk_report(self.open, self.delivered, VIEW, self.profiles, TODAY, 4)
        self.assertEqual([r["board"] for r in report["boards"]], ["DESK"])
        row = report["boards"][0]
        self.assertEqual(row["age"], {"0–2 d": 1, "3–7 d": 1, "8–14 d": 1, "15+ d": 1})
        self.assertEqual((row["open"], row["waiting"], row["unassigned"]), (5, 1, 1))

    def test_resolution_time_counts_only_what_was_delivered_inside_the_weeks_asked(self):
        row = team.desk_report(self.open, self.delivered, VIEW, self.profiles, TODAY, 4)["boards"][0]
        self.assertEqual((row["resolved_n"], row["resolution"]["median"]), (1, 4))

    def test_a_view_without_a_help_desk_board_is_refused(self):
        with self.assertRaisesRegex(team.NoDesk, "no help desk board"):
            team.desk_report(self.open, [], fx.view(boards=("TEAM",)), self.profiles, TODAY, 4)


class RollupTest(unittest.TestCase):
    def test_one_row_per_view_with_the_numbers_a_sr_em_compares(self):
        open_ = [fx.at("TEAM-1", "blocked"), fx.at("TEAM-2", "active", changed="2026-09-01"), fx.at("TEAM-3", "todo")]
        delivered = [fx.at("TEAM-4", "delivered", created="2026-10-01", resolved="2026-10-06")]
        row = team.rollup_row(VIEW, open_, delivered, CONVENTIONS, TODAY)
        self.assertEqual({k: row[k] for k in ("view", "open", "blocked", "stalled", "delivered")},
                         {"view": "plataforma", "open": 3, "blocked": 1, "stalled": 1, "delivered": 1})
        self.assertEqual(row["lead"]["p85"], 5)


class GatherTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        self.profiles = fx.profiles()

    def test_open_work_is_asked_in_one_search_epics_are_dropped_and_roles_are_set(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("TEAM-1", status="En curso", status_id="2", category="in_progress"),
                                          issue("TEAM-2", issuetype="Epic")]
        issues, cut = team.gather_open(jira, VIEW, self.profiles, CONVENTIONS)
        self.assertEqual(len(jira.jqls), 1)
        self.assertTrue(jira.jqls[0].startswith("((project = TEAM AND status not in (5, 6)) OR (project = DESK"))
        self.assertEqual(([i["key"] for i in issues], issues[0]["role"], cut), (["TEAM-1"], "active", False))

    def test_a_search_that_reaches_the_cap_says_so(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue(f"TEAM-{n}") for n in range(team.CAP + 1)]
        issues, cut = team.gather_open(jira, VIEW, self.profiles, CONVENTIONS)
        self.assertEqual((len(issues), cut), (team.CAP, True))

    def test_closed_work_is_not_asked_when_no_board_has_such_a_status(self):
        jira = FakeJira()
        no_dropped = {"TEAM": {"statuses": [{"id": "1", "role": "todo"}]}}
        view = fx.view(boards=("TEAM",))
        self.assertEqual(team.gather_closed(jira, view, no_dropped, CONVENTIONS, ("dropped",), date(2026, 9, 1)), ([], False))
        self.assertEqual(jira.jqls, [])

    def test_created_work_is_asked_for_the_window(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("TEAM-1", created="2026-10-02")]
        issues, _ = team.gather_created(jira, VIEW, self.profiles, CONVENTIONS, date(2026, 10, 1), date(2026, 10, 8))
        self.assertIn('created >= "2026-10-01"', jira.jqls[0])
        self.assertEqual([i["key"] for i in issues], ["TEAM-1"])

    def test_missing_profiles_are_listed_in_the_order_of_the_view(self):
        self.assertEqual(team.missing_profiles(VIEW, {"DESK": {}}), ["TEAM"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_team.py' 2>&1 | tail -4`
Expected: `ImportError: cannot import name 'team' from 'jkan'`.

- [ ] **Step 3: Implementar**

```python
"""Team reports: what each report shows, computed from issues that carry a role (roles.annotate). Pure functions, plus
the gather_* that ask Jira. A report never writes anything."""
from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional, Tuple

from . import queries, roles, standup, stats

CAP = 1000  # issues one search may return; past it the report says so
COUNTED = ("todo", "active", "blocked", "waiting")
AGE_BUCKETS = ((0, 2, "0–2 d"), (3, 7, "3–7 d"), (8, 14, "8–14 d"), (15, None, "15+ d"))


class NoDesk(ValueError):
    """The view has no board whose profile says it is a help desk."""


def _day(text: str) -> _dt.date:
    return _dt.date.fromisoformat(text)


def delivery_day(issue: dict) -> Optional[str]:
    """When the issue was delivered: its resolution day or, without one, its last change of category."""
    return issue.get("resolved") or issue.get("changed")


def _days_since(text: Optional[str], today: _dt.date) -> Optional[int]:
    return (today - _day(text)).days if text else None


def missing_profiles(view: dict, profiles: Dict[str, dict]) -> List[str]:
    return [board for board in view["boards"] if board not in profiles]


def first_week(today: _dt.date, weeks: int) -> _dt.date:
    return stats.week_of(today) - _dt.timedelta(weeks=weeks - 1)


# ---- asking Jira -------------------------------------------------------------------------------------------------

def _fetch(jira, jql: str, conv: dict, profiles: Dict[str, dict]) -> Tuple[List[dict], bool]:
    found, truncated = jira.search_capped(jql, CAP, blocked_link=conv.get("blocked_link") or "is blocked by")
    roles.annotate(found, profiles)
    epic = conv["issue_types"]["epic"]
    return [i for i in found if i["issuetype"] != epic], truncated


def gather_open(jira, view: dict, profiles: Dict[str, dict], conv: dict) -> Tuple[List[dict], bool]:
    """Open work of the team, plus what nobody owns, in the view's boards. Statuses without a role come back with role None."""
    return _fetch(jira, queries.team_open(view["boards"], profiles, view["team"]), conv, profiles)


def gather_closed(jira, view: dict, profiles: Dict[str, dict], conv: dict, wanted: tuple,
                  since: _dt.date) -> Tuple[List[dict], bool]:
    jql = queries.team_closed(view["boards"], profiles, view["team"], wanted, since)
    return ([], False) if jql is None else _fetch(jira, jql, conv, profiles)


def gather_created(jira, view: dict, profiles: Dict[str, dict], conv: dict, since: _dt.date,
                   until: _dt.date) -> Tuple[List[dict], bool]:
    return _fetch(jira, queries.team_created(view["boards"], since, until), conv, profiles)


# ---- the reports -------------------------------------------------------------------------------------------------

def _bucket(issue: dict) -> str:
    role = roles.role_of(issue)
    return role if role in COUNTED else "none"


def _tally() -> dict:
    return {role: 0 for role in COUNTED + ("none",)}


def status_report(open_issues: List[dict], view: dict, profiles: Dict[str, dict]) -> dict:
    """How much open work there is in each role, per board and per person; the WIP verdict needs the profile's wip_limit."""
    boards = []
    for board in view["boards"]:
        mine = [i for i in open_issues if roles.project_of(i["key"]) == board]
        row = dict(_tally(), board=board, n=len(mine), unassigned=sum(1 for i in mine if not i["assignee"]))
        for issue in mine:
            row[_bucket(issue)] += 1
        boards.append(row)
    grouped: Dict[tuple, dict] = {}
    for issue in open_issues:
        if not issue["assignee"]:
            continue
        board, name = roles.project_of(issue["key"]), issue["assignee"]["name"]
        row = grouped.setdefault((name, board), dict(_tally(), person=name, board=board, n=0))
        row["n"] += 1
        row[_bucket(issue)] += 1
    people = []
    for (name, board), row in sorted(grouped.items(), key=lambda kv: (kv[0][0].lower(), kv[0][1])):
        wip = row["active"] + row["blocked"] + row["waiting"]
        limit = profiles[board].get("wip_limit")
        row.update(wip=wip, wip_limit=limit, room=None if limit is None else limit - wip)
        people.append(row)
    return {"n": len(open_issues), "boards": boards, "people": people}


def stalled_report(open_issues: List[dict], today: _dt.date, days: int) -> dict:
    """The `active` issues whose category has not changed for `days` days or more, with the days since the last edit beside it."""
    rows = []
    for issue in open_issues:
        if roles.role_of(issue) != "active" or not issue.get("changed"):
            continue
        in_category = _days_since(issue["changed"], today)
        if in_category < days:
            continue
        rows.append({"issue": issue, "days_in_category": in_category,
                     "days_since_edit": _days_since(issue.get("updated"), today)})
    rows.sort(key=lambda r: (-r["days_in_category"], r["issue"]["key"]))
    return {"days": days, "n_active": sum(1 for i in open_issues if roles.role_of(i) == "active"), "rows": rows}


def blocked_report(open_issues: List[dict], conv: dict, today: _dt.date) -> dict:
    """What is blocked (by role, flag or an unresolved «is blocked by» link) and, apart, what waits for a third party."""
    statuses = conv.get("blocked_statuses") or []
    age = lambda i: _days_since(i.get("changed"), today)  # noqa: E731
    order = lambda days, key: (-(days if days is not None else -1), key)  # noqa: E731
    blocked = [dict(why, issue=i, days=age(i)) for i in open_issues for why in standup.blockers(i, statuses)]
    waiting = [{"issue": i, "days": age(i)} for i in open_issues if roles.role_of(i) == "waiting"]
    blocked.sort(key=lambda r: order(r["days"], r["issue"]["key"]))
    waiting.sort(key=lambda r: order(r["days"], r["issue"]["key"]))
    return {"n": len(open_issues), "blocked": blocked, "waiting": waiting}


def flow_report(delivered: List[dict], dropped: List[dict], open_issues: List[dict], today: _dt.date,
                weeks: int) -> dict:
    """Deliveries per week, lead time and the age of the work in flight. Only `delivered` counts as delivery."""
    first = first_week(today, weeks).isoformat()
    mine = [dict(i, changed=delivery_day(i)) for i in delivered if (delivery_day(i) or "") >= first]
    gone = [i for i in dropped if (i.get("changed") or "") >= first]
    return {"weeks": weeks, "since": first, "delivered_n": len(mine), "dropped_n": len(gone),
            "weekly": stats.throughput(mine, today, weeks), "lead": stats.spread(stats.lead_days(mine)),
            "wip": stats.wip(open_issues, today)}


def digest_report(delivered: List[dict], dropped: List[dict], created: List[dict], open_issues: List[dict],
                  conv: dict, since: _dt.date, until: _dt.date, today: _dt.date, days: int) -> dict:
    lo, hi = since.isoformat(), until.isoformat()
    done = sorted((i for i in delivered if lo <= (delivery_day(i) or "") <= hi),
                  key=lambda i: (delivery_day(i), i["key"]))
    gone = sorted((i for i in dropped if lo <= (i.get("changed") or "") <= hi), key=lambda i: (i["changed"], i["key"]))
    new = sorted((i for i in created if lo <= (i.get("created") or "") <= hi), key=lambda i: i["key"])
    blocked = blocked_report(open_issues, conv, today)
    stalled = stalled_report(open_issues, today, days)
    return {"since": lo, "until": hi, "days": days, "delivered": done, "dropped": gone, "created": new,
            "blocked_now": len({r["issue"]["key"] for r in blocked["blocked"]}), "waiting_now": len(blocked["waiting"]),
            "stalled_now": len(stalled["rows"])}


def desk_boards(view: dict, profiles: Dict[str, dict]) -> List[str]:
    return [board for board in view["boards"] if profiles[board].get("kind") == "helpdesk"]


def _age_label(days: int) -> str:
    for low, high, label in AGE_BUCKETS:
        if days >= low and (high is None or days <= high):
            return label
    return AGE_BUCKETS[0][2]  # a creation date in the future counts as the youngest


def desk_report(open_issues: List[dict], delivered: List[dict], view: dict, profiles: Dict[str, dict],
                today: _dt.date, weeks: int) -> dict:
    """For the view's help desk boards: age of what is open (what waits for a third party is counted apart), what has no
    owner, and how long resolving took. There is no SLA here: no service desk measured had SLA data."""
    boards = desk_boards(view, profiles)
    if not boards:
        raise NoDesk(f"view {view['name']!r} has no help desk board: set one with jk board setup KEY --kind helpdesk")
    first = first_week(today, weeks).isoformat()
    rows = []
    for board in boards:
        mine = [i for i in open_issues if roles.project_of(i["key"]) == board]
        age = {label: 0 for _, _, label in AGE_BUCKETS}
        for issue in (i for i in mine if roles.role_of(i) in ("todo", "active", "blocked")):
            days = _days_since(issue.get("created"), today)
            if days is not None:
                age[_age_label(days)] += 1
        solved = [i for i in delivered if roles.project_of(i["key"]) == board and (delivery_day(i) or "") >= first]
        rows.append({"board": board, "open": len(mine), "age": age,
                     "unassigned": sum(1 for i in mine if not i["assignee"]),
                     "waiting": sum(1 for i in mine if roles.role_of(i) == "waiting"),
                     "resolved_n": len(solved), "resolution": stats.spread(stats.lead_days(solved))})
    return {"weeks": weeks, "since": first, "boards": rows}


def rollup_row(view: dict, open_issues: List[dict], delivered: List[dict], conv: dict, today: _dt.date,
               weeks: int = 4) -> dict:
    blocked = blocked_report(open_issues, conv, today)
    flow = flow_report(delivered, [], open_issues, today, weeks)
    return {"view": view["name"], "open": len(open_issues),
            "blocked": len({r["issue"]["key"] for r in blocked["blocked"]}),
            "stalled": len(stalled_report(open_issues, today, view["stalled_days"])["rows"]),
            "delivered": flow["delivered_n"], "lead": flow["lead"], "weeks": weeks}
```

- [ ] **Step 4: Correrlos y ver que pasan, y suite completa**

Run: `python3 -m unittest discover -s tests -p 'test_team.py' 2>&1 | tail -3; python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` en los dos (`team` ya está clasificado como lado de lectura).

- [ ] **Step 5: Commit**

```bash
git add jkan/team.py tests/test_team.py
git commit -m "feat(team): the team reports as pure functions over issues with a role"
```

---

### Task 5: El Markdown de los reportes

**Files:**
- Create: `jkan/team_render.py`
- Test: `tests/test_team_render.py`

**Interfaces:**
- Consumes: `render.table`, `render.KEYLIKE`, `board_profile.open_statuses`, los reportes de la Task 4.
- Produces: `team_render.head(title, view, profiles, today, window=None)`, `limits(verb)`, `table(headers, rows, show_all, empty=...)`, `profile_state(view, profiles)`, `team_label(team)`, `render_status/stalled/blocked/flow/digest/desk/rollup`. Los de `stalled`, `blocked`, `flow` y `digest` reciben además `link(key) -> str`.

- [ ] **Step 1: Escribir los tests**

```python
from __future__ import annotations

import unittest

import team_fixtures as fx
from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import team, team_render

LINK = lambda key: f"[{key}]"  # noqa: E731
VIEW = fx.view()


class HeadTest(unittest.TestCase):
    def test_the_first_block_names_the_view_the_boards_the_team_the_window_and_the_profiles(self):
        text = team_render.head("Flujo", VIEW, fx.profiles(), fx.TODAY, ("2026-09-14", fx.TODAY))
        self.assertEqual(text, "## Flujo\n**View:** plataforma · **Boards:** TEAM, DESK · **Equipo:** grupo team · "
                               "**Ventana:** 2026-09-14 → 2026-10-08 · **Consultado:** 2026-10-08 · **Perfiles:** confirmados")

    def test_undecided_statuses_make_the_profiles_unconfirmed_and_say_where(self):
        profiles = {"TEAM": fx.profile("TEAM", decide_waiting=False), "DESK": fx.profile("DESK", kind="helpdesk")}
        self.assertIn("**Perfiles:** sin confirmar — TEAM (1 sin decidir)", team_render.head("x", VIEW, profiles, fx.TODAY))

    def test_the_team_is_described_whatever_its_form(self):
        self.assertEqual(team_render.team_label(None), "todos los asignados")
        self.assertEqual(team_render.team_label({"people": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}), "2 personas")


class TableTest(unittest.TestCase):
    ROWS = [[n, "x"] for n in range(25)]

    def test_more_than_20_rows_are_cut_and_the_note_says_how_many_were_left_out(self):
        text = team_render.table(["N", "T"], self.ROWS, False)
        self.assertEqual(text.count("\n| "), 20 + 1)  # the separator line plus 20 rows
        self.assertTrue(text.endswith("_… y 5 más (usá --all)._"))

    def test_all_lifts_the_cut(self):
        text = team_render.table(["N", "T"], self.ROWS, True)
        self.assertNotIn("más", text)
        self.assertIn("| 24 | x |", text)

    def test_exactly_20_rows_are_not_cut(self):
        self.assertNotIn("más", team_render.table(["N", "T"], self.ROWS[:20], False))

    def test_no_rows_says_nothing_instead_of_an_empty_table(self):
        self.assertEqual(team_render.table(["N"], [], False, "_Nada._"), "_Nada._")


class LimitsTest(unittest.TestCase):
    def test_every_report_ends_with_its_own_limits(self):
        for verb in ("status", "stalled", "blocked", "flow", "digest", "desk", "rollup"):
            text = team_render.limits(verb)
            self.assertTrue(text.startswith("### Límites\n- "), verb)

    def test_the_desk_report_says_there_is_no_sla_and_stalled_says_what_it_is_not(self):
        self.assertIn("Sin SLA", team_render.limits("desk"))
        self.assertIn("no es «sin progreso»", team_render.limits("stalled"))


class BodiesTest(unittest.TestCase):
    def test_status_shows_the_verdict_only_where_there_is_a_limit(self):
        open_ = [fx.at("TEAM-1", "active", assignee=fx.ANA), fx.at("TEAM-2", "blocked", assignee=fx.ANA),
                 fx.at("DESK-1", "active", assignee=fx.ANA)]
        text = team_render.render_status(team.status_report(open_, VIEW, fx.profiles(TEAM=2)), False)
        self.assertIn("| Ana Gómez | TEAM | 2 | 0 | 1 | 1 | 0 | 0 | 2 | 2 | sin espacio |", text)
        self.assertIn("| Ana Gómez | DESK | 1 | 0 | 1 | 0 | 0 | 0 | 1 | – | – |", text)
        self.assertIn("**3 abiertos**", text)

    def test_flow_flags_a_small_n_and_names_the_dropped_apart(self):
        report = team.flow_report([fx.at("TEAM-1", "delivered", created="2026-10-01", resolved="2026-10-06")],
                                  [fx.at("TEAM-2", "dropped", changed="2026-10-02")], [], fx.TODAY, 2)
        text = team_render.render_flow(report, False, LINK)
        self.assertIn("n=1 · mediana 5 d · p85 5 d · pocos casos, no concluyas nada", text)
        self.assertIn("**1 entregados** desde 2026-09-28; 1 descartados (no cuentan como entregas)", text)

    def test_stalled_names_the_two_day_counts(self):
        report = team.stalled_report([fx.at("TEAM-1", "active", changed="2026-09-20", updated="2026-10-07")], fx.TODAY, 7)
        text = team_render.render_stalled(report, False, LINK)
        self.assertIn("| [TEAM-1] | Summary of TEAM-1 | Yo | En curso | 18 | 1 |", text)
        self.assertIn("**1 de 1 en curso** llevan 7 días o más", text)

    def test_blocked_separates_the_waiting(self):
        report = team.blocked_report([fx.at("TEAM-1", "blocked"), fx.at("TEAM-2", "waiting")], {"blocked_statuses": []}, fx.TODAY)
        text = team_render.render_blocked(report, False, LINK)
        self.assertIn("### Bloqueados (1)", text)
        self.assertIn("### Esperando a un tercero (1)", text)

    def test_rollup_shows_a_view_that_could_not_be_computed_instead_of_dropping_it(self):
        good = {"view": "a", "open": 3, "blocked": 1, "stalled": 0, "delivered": 2, "lead": {"n": 4, "median": 3, "p85": 6}}
        text = team_render.render_rollup([good, {"view": "b", "error": "sin perfil: UA"}], False)
        self.assertIn("| a | 3 | 1 | 0 | 2 | 6 d (n=4) |", text)
        self.assertIn("| b | sin perfil: UA |", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_team_render.py' 2>&1 | tail -4`
Expected: `ImportError: cannot import name 'team_render' from 'jkan'`.

- [ ] **Step 3: Implementar**

```python
"""Markdown for the team reports, following the output contract of the spec: a fixed first block, every number with its n,
at most 20 rows per table (--all lifts it), and a fixed «Límites» section. Labels are Spanish, like the other reports."""
from __future__ import annotations

import datetime as _dt
from typing import Callable, Dict, List, Optional

from . import board_profile, render

Link = Callable[[str], str]
CAP_ROWS = 20
SMALL_N = 10

LIMITS = {
    "status": [
        "«Sin rol» son issues en estados que el perfil todavía no decidió o no conoce.",
        "«Sin asignar» cuenta lo abierto sin dueño en esos boards, sea o no del equipo; lo asignado a otras personas no se cuenta.",
        "El veredicto de carga sale del límite de WIP de cada perfil (`jk board limit KEY N`); sin límite, solo números."],
    "stalled": [
        "«Estancado» no es «sin progreso»: la categoría de Jira solo cambia al pasar de una categoría a otra, así que moverse "
        "entre dos estados «en curso» no reinicia los días en la categoría.",
        "Los días desde la última edición se reinician con cualquier cambio, comentarios incluidos."],
    "blocked": [
        "Un issue figura como bloqueado por su rol, por el flag o por un link «is blocked by» sin resolver.",
        "«Esperando» (rol `waiting`) es trabajo frenado por un tercero y va aparte."],
    "flow": [
        "Sin story points: la velocidad se mide en issues entregados (rol `delivered`) por semana.",
        "La fecha de entrega es la de resolución o, si falta, la del último cambio de categoría: un `Done` archivado en otra "
        "categoría puede figurar con una fecha anterior.",
        "No hay tiempo de ciclo real: el lead time va de la creación a la entrega."],
    "digest": [
        "«Nuevo» es lo creado en el período en esos boards, sea o no del equipo.",
        "Bloqueados, esperando y estancados son el estado de hoy, no el del período."],
    "desk": [
        "Sin SLA: ningún service desk medido tenía datos de SLA. La edad corre desde la creación y no cuenta lo que espera a un tercero.",
        "El tiempo de resolución va de la creación a la entrega."],
    "rollup": [
        "Cada fila sale de un view completo; un view con un board sin perfil no se calcula.",
        "Entregados y p85 miden las últimas 4 semanas."],
}


def team_label(team: Optional[dict]) -> str:
    if not team:
        return "todos los asignados"
    if "group" in team:
        return f"grupo {team['group']}"
    return f"{len(team['people'])} personas"


def profile_state(view: dict, profiles: Dict[str, dict]) -> str:
    pending = {b: len(board_profile.open_statuses(profiles[b])) for b in view["boards"] if b in profiles}
    pending = {b: n for b, n in pending.items() if n}
    if not pending:
        return "confirmados"
    return "sin confirmar — " + ", ".join(f"{b} ({n} sin decidir)" for b, n in sorted(pending.items()))


def head(title: str, view: dict, profiles: Dict[str, dict], today: _dt.date, window: Optional[tuple] = None) -> str:
    parts = [f"**View:** {view['name']}", f"**Boards:** {', '.join(view['boards'])}",
             f"**Equipo:** {team_label(view['team'])}"]
    if window:
        parts.append(f"**Ventana:** {window[0]} → {window[1]}")
    parts += [f"**Consultado:** {today}", f"**Perfiles:** {profile_state(view, profiles)}"]
    return f"## {title}\n" + " · ".join(parts)


def limits(verb: str) -> str:
    return "### Límites\n" + "\n".join(f"- {line}" for line in LIMITS[verb])


def table(headers: List[str], rows: List[list], show_all: bool, empty: str = "_Nada._") -> str:
    """The table, cut at 20 rows with a note that says how many were left out (nothing is dropped silently)."""
    shown = rows if show_all or len(rows) <= CAP_ROWS else rows[:CAP_ROWS]
    note = "" if len(shown) == len(rows) else f"\n\n_… y {len(rows) - len(shown)} más (usá --all)._"
    return render.table(headers, shown, empty) + note


def _who(issue: dict) -> str:
    owner = issue.get("assignee")
    return owner["name"] if owner else "sin asignar"


def _days(value) -> str:
    return "–" if value is None else str(value)


def _small(n: int) -> str:
    return " · pocos casos, no concluyas nada" if n < SMALL_N else ""


def _spread(spread: Optional[dict], empty: str) -> str:
    if not spread:
        return empty
    return f"n={spread['n']} · mediana {spread['median']} d · p85 {spread['p85']} d{_small(spread['n'])}"


def render_status(report: dict, show_all: bool) -> str:
    boards = table(["Board", "Abiertos", "Por hacer", "En curso", "Bloqueado", "Esperando", "Sin rol", "Sin asignar"],
                   [[r["board"], r["n"], r["todo"], r["active"], r["blocked"], r["waiting"], r["none"], r["unassigned"]]
                    for r in report["boards"]], show_all)

    def verdict(row: dict) -> str:
        if row["room"] is None:
            return "–"
        return "sin espacio" if row["room"] <= 0 else f"espacio para {row['room']}"

    people = table(["Persona", "Board", "Abiertos", "Por hacer", "En curso", "Bloqueado", "Esperando", "Sin rol", "WIP",
                    "Límite", "Veredicto"],
                   [[r["person"], r["board"], r["n"], r["todo"], r["active"], r["blocked"], r["waiting"], r["none"],
                     r["wip"], r["wip_limit"], verdict(r)] for r in report["people"]], show_all,
                   "_Nadie del equipo tiene trabajo abierto._")
    return "\n\n".join([f"**{report['n']} abiertos** (issues del equipo y sin asignar)", "### Por board\n" + boards,
                        "### Por persona y board\n" + people])


def render_stalled(report: dict, show_all: bool, link: Link) -> str:
    rows = report["rows"]
    body = table(["Key", "Título", "Dueño", "Estado", "Días en la categoría", "Días desde la última edición"],
                 [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), r["issue"]["status"],
                   r["days_in_category"], _days(r["days_since_edit"])] for r in rows], show_all,
                 "_Nada estancado._")
    return "\n\n".join([f"**{len(rows)} de {report['n_active']} en curso** llevan {report['days']} días o más en su categoría",
                        body])


def render_blocked(report: dict, show_all: bool, link: Link) -> str:
    def by(row: dict) -> str:
        return f"{link(row['by'])} {row['title']}".strip() if render.KEYLIKE.match(row["by"]) else row["by"]

    blocked = table(["Key", "Título", "Dueño", "Por qué", "Estado del bloqueador", "Dueño del bloqueador", "Días"],
                    [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), by(r), r["status"], r["owner"],
                      _days(r["days"])] for r in report["blocked"]], show_all, "_Nada bloqueado._")
    waiting = table(["Key", "Título", "Dueño", "Estado", "Días"],
                    [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), r["issue"]["status"],
                      _days(r["days"])] for r in report["waiting"]], show_all, "_Nada esperando a un tercero._")
    return "\n\n".join([f"### Bloqueados ({len(report['blocked'])})\n" + blocked,
                        f"### Esperando a un tercero ({len(report['waiting'])})\n" + waiting])


def render_flow(report: dict, show_all: bool, link: Link) -> str:
    weekly = table(["Semana (lunes)", "Entregados"],
                   [[w["week"], f"{w['closed']}{' (en curso)' if w['partial'] else ''}"] for w in report["weekly"]],
                   show_all)
    wip = table(["Key", "Título", "Dueño", "Días sin cambio de categoría", "Estado"],
                [[link(r["issue"]["key"]), r["issue"]["summary"], _who(r["issue"]), r["days"],
                  "estancado" if r["stalled"] else ""] for r in report["wip"]], show_all, "_Nada en curso._")
    return "\n\n".join([
        f"**{report['delivered_n']} entregados** desde {report['since']}; {report['dropped_n']} descartados "
        "(no cuentan como entregas)",
        f"### Entregados por semana (últimas {report['weeks']})\n" + weekly,
        "### Lead time (creación → entrega)\n" + _spread(report["lead"], "_Sin entregas en el período._"),
        "### Edad del trabajo en curso\n" + wip])


def render_digest(report: dict, show_all: bool, link: Link) -> str:
    def listing(issues: List[dict], day: Callable[[dict], Optional[str]]) -> str:
        return table(["Key", "Título", "Dueño", "Fecha"],
                     [[link(i["key"]), i["summary"], _who(i), day(i) or "–"] for i in issues], show_all)

    totals = (f"**{len(report['delivered'])} entregados · {len(report['dropped'])} descartados · "
              f"{len(report['created'])} nuevos** · hoy: {report['blocked_now']} bloqueados, "
              f"{report['waiting_now']} esperando, {report['stalled_now']} estancados (≥ {report['days']} días)")
    return "\n\n".join([totals,
                        "### Entregados\n" + listing(report["delivered"], lambda i: i.get("resolved") or i.get("changed")),
                        "### Descartados\n" + listing(report["dropped"], lambda i: i.get("changed")),
                        "### Nuevos\n" + listing(report["created"], lambda i: i.get("created"))])


def render_desk(report: dict, show_all: bool) -> str:
    labels = list(report["boards"][0]["age"]) if report["boards"] else []
    body = table(["Board", "Abiertos"] + labels + ["Sin asignar", "Esperando", "Resueltos"],
                 [[r["board"], r["open"]] + [r["age"][label] for label in labels]
                  + [r["unassigned"], r["waiting"], r["resolved_n"]] for r in report["boards"]], show_all)
    times = "\n".join(f"- **{r['board']}:** " + _spread(r["resolution"], "sin resueltos en el período")
                      for r in report["boards"])
    return "\n\n".join(["### Abiertos por antigüedad (sin contar lo que espera a un tercero)\n" + body,
                        f"### Tiempo de resolución (últimas {report['weeks']} semanas)\n" + times])


def render_rollup(rows: List[dict], show_all: bool) -> str:
    def lead(row: dict) -> str:
        spread = row.get("lead")
        return "–" if not spread else f"{spread['p85']} d (n={spread['n']})"

    cells = []
    for r in rows:
        if "error" in r:
            cells.append([r["view"], r["error"], "", "", "", ""])
        else:
            cells.append([r["view"], r["open"], r["blocked"], r["stalled"], r["delivered"], lead(r)])
    return table(["View", "Abiertos", "Bloqueados", "Estancados", "Entregados (4 sem)", "Lead time p85"], cells, show_all)
```

- [ ] **Step 4: Correrlos y ver que pasan, y suite completa**

Run: `python3 -m unittest discover -s tests -p 'test_team_render.py' 2>&1 | tail -3; python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` en los dos.

- [ ] **Step 5: Commit**

```bash
git add jkan/team_render.py tests/test_team_render.py
git commit -m "feat(team): markdown for the team reports with the output contract of the spec"
```

---

### Task 6: `jk team ...`

**Files:**
- Create: `jkan/team_cli.py`
- Modify: `jkan/cli.py` (dos ediciones: imports y despacho)
- Test: `tests/test_team_cli.py`

**Interfaces:**
- Consumes: todo lo anterior, `people.resolve`, `window.weeks/span`, `board_profile.scan`.
- Produces: `team_cli.run(argv, jira, conv, today) -> int` con `argv` empezando en el verbo y `jira` una función que arma el cliente; `team_cli.VERBS`; códigos de salida `0` listo, `1` hallazgo o entrada rechazada (un board sin perfil, un view roto), `2` no se pudo (Jira, disco).
- Produces: `jk team <verbo>` despacha a `team_cli`; `--json` y `--all` en todos los reportes.

- [ ] **Step 1: Escribir los tests de punta a punta**

```python
from __future__ import annotations

import contextlib
import io
import json
import unittest

import team_fixtures as fx
from helpers import FakeJira, config_dir, issue
from jkan import board_profile, cli, views


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["team"] + args, client=lambda project: jira, today=lambda: fx.TODAY)
    return code, out.getvalue(), err.getvalue()


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        self.jira = FakeJira()

    def test_a_group_view_is_saved_after_checking_that_the_group_exists(self):
        code, out, _ = run(["setup", "nuevo", "--boards", "TEAM,DESK", "--group", "team"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("Grupo team: 7 miembros.", out)
        self.assertEqual(views.load("nuevo")["team"], {"group": "team"})
        self.assertIn("View guardado en", out)

    def test_it_says_which_boards_still_have_no_profile(self):
        board_profile.save(fx.profile("TEAM"))
        _, out, _ = run(["setup", "nuevo", "--boards", "TEAM,DESK"], self.jira)
        self.assertIn("Falta el perfil de: DESK. Corré `jk board setup KEY`", out)

    def test_a_group_that_does_not_exist_is_refused_and_nothing_is_saved(self):
        code, _, err = run(["setup", "nuevo", "--boards", "TEAM", "--group", "no-such-group"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("Jira has no group 'no-such-group'", err)
        self.assertEqual(views.names(), [])

    def test_people_are_resolved_to_account_ids(self):
        code, out, _ = run(["setup", "nuevo", "--boards", "TEAM", "--people", "Ana Gómez"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(views.load("nuevo")["team"], {"people": [{"id": "acc-ana", "name": "Ana Gómez"}]})
        self.assertIn("Personas: Ana Gómez.", out)

    def test_an_ambiguous_person_is_never_guessed(self):
        code, _, err = run(["setup", "nuevo", "--boards", "TEAM", "--people", "Martin"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("matches 2 people", err)
        self.assertEqual(views.names(), [])

    def test_a_group_and_people_together_are_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["setup", "nuevo", "--boards", "TEAM", "--group", "g", "--people", "Ana"], self.jira)

    def test_bad_input_is_refused_before_anything_is_saved(self):
        for args in (["--boards", "TEAM,x y"], ["--boards", ""], ["--boards", "TEAM", "--stalled-days", "0"]):
            code, _, err = run(["setup", "nuevo"] + args, self.jira)
            self.assertEqual(code, 1, args)
            self.assertTrue(err.strip(), args)
        self.assertEqual(views.names(), [])


class ShowAndListTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        board_profile.save(fx.profile("TEAM"))
        views.save(fx.view())

    def test_show_prints_the_view_and_the_state_of_each_profile(self):
        code, out, _ = run(["show", "plataforma"], FakeJira())
        self.assertEqual(code, 0)
        self.assertIn("**Boards:** TEAM, DESK", out)
        self.assertIn("| TEAM | confirmado |", out)
        self.assertIn("| DESK | sin perfil |", out)

    def test_list_names_the_views_and_an_empty_list_says_how_to_start(self):
        _, out, _ = run(["list"], FakeJira())
        self.assertIn("| plataforma | TEAM, DESK | grupo team |", out)
        config_dir()
        self.assertIn("Creá uno con `jk team setup`", run(["list"], FakeJira())[1])

    def test_an_unknown_view_says_how_to_create_it(self):
        code, _, err = run(["show", "nada"], FakeJira())
        self.assertEqual(code, 1)
        self.assertIn("jk team setup nada --boards", err)


class ReportsTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        for prof in fx.profiles(TEAM=2).values():
            board_profile.save(prof)
        views.save(fx.view())
        self.jira = FakeJira()

    def open_work(self):
        return [fx.at("TEAM-1", "active", assignee=fx.ANA, changed="2026-09-20"), fx.at("TEAM-2", "blocked", assignee=fx.ANA),
                fx.at("TEAM-3", "todo", assignee=None), fx.at("DESK-1", "waiting", assignee=fx.BETO)]

    def test_a_board_without_a_profile_is_refused_and_nothing_is_asked_of_jira(self):
        (self.base / "profiles" / "DESK.json").unlink()
        code, _, err = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no profile for DESK: run jk board setup DESK", err)
        self.assertEqual(self.jira.jqls, [])

    def test_a_profile_file_nobody_can_read_is_named_in_the_refusal(self):
        (self.base / "profiles" / "DESK.json").write_text("{}", encoding="utf-8")
        code, _, err = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("DESK.json is not a profile", err)

    def test_status_end_to_end_and_it_writes_nothing(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("## Estado del equipo\n**View:** plataforma · **Boards:** TEAM, DESK"))
        self.assertIn("**Perfiles:** confirmados", out)
        self.assertIn("**4 abiertos**", out)
        self.assertIn("| TEAM | 3 | 1 | 1 | 1 | 0 | 0 | 1 |", out)
        self.assertTrue(out.rstrip().endswith("sin límite, solo números."))
        self.assertEqual(self.jira.writes, [])

    def test_json_carries_the_same_facts_without_the_markdown(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["status", "plataforma", "--json"], self.jira)
        data = json.loads(out)
        self.assertEqual((code, data["view"], data["boards"], data["truncated"], data["notes"]),
                         (0, "plataforma", ["TEAM", "DESK"], False, []))
        self.assertEqual(data["report"]["n"], 4)

    def test_a_status_the_profile_never_saw_is_reported(self):
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "todo", status="Nuevo", status_id="99")])
        _, out, _ = run(["status", "plataforma"], self.jira)
        self.assertIn("> ⚠ Estado desconocido: Nuevo (TEAM).", out)

    def test_undecided_statuses_are_counted_as_without_role_and_announced(self):
        board_profile.save(fx.profile("TEAM", wip_limit=2, decide_waiting=False))
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "waiting")])
        _, out, _ = run(["status", "plataforma"], self.jira)
        self.assertIn("**Perfiles:** sin confirmar — TEAM (1 sin decidir)", out)
        self.assertIn("> ⚠ Perfil sin confirmar en TEAM: faltan decidir Esperando al cliente.", out)
        self.assertIn("| TEAM | 1 | 0 | 0 | 0 | 0 | 1 | 0 |", out)

    def test_a_search_that_hits_the_cap_says_so_instead_of_cutting_in_silence(self):
        self.jira.search_answer = fx.answers(open_=[fx.at(f"TEAM-{n}", "todo") for n in range(1001)])
        code, out, _ = run(["status", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("> ⚠ La búsqueda llegó al tope de 1000 issues: faltan resultados.", out)
        self.assertTrue(json.loads(run(["status", "plataforma", "--json"], self.jira)[1])["truncated"])

    def test_tables_are_cut_at_20_rows_and_all_lifts_the_cut(self):
        crowd = [fx.at(f"TEAM-{n}", "active", assignee={"id": f"acc-{n}", "name": f"Persona {n:02d}"}) for n in range(25)]
        self.jira.search_answer = fx.answers(open_=crowd)
        _, cut, _ = run(["status", "plataforma"], self.jira)
        _, full, _ = run(["status", "plataforma", "--all"], self.jira)
        self.assertIn("_… y 5 más (usá --all)._", cut)
        self.assertNotIn("más (usá", full)
        self.assertIn("Persona 24", full)
        self.assertNotIn("Persona 24", cut)

    def test_stalled_uses_the_view_days_unless_asked_otherwise(self):
        self.jira.search_answer = fx.answers(open_=[fx.at("TEAM-1", "active", changed="2026-10-02"),
                                                    fx.at("TEAM-2", "active", changed="2026-09-01")])
        _, default, _ = run(["stalled", "plataforma"], self.jira)
        _, three, _ = run(["stalled", "plataforma", "--days", "3"], self.jira)
        self.assertIn("**1 de 2 en curso** llevan 7 días", default)
        self.assertIn("**2 de 2 en curso** llevan 3 días", three)
        code, _, err = run(["stalled", "plataforma", "--days", "0"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("--days must be", err)

    def test_blocked_end_to_end(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["blocked", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("### Bloqueados (1)", out)
        self.assertIn("### Esperando a un tercero (1)", out)
        self.assertIn("[TEAM-2](https://example.atlassian.net/browse/TEAM-2)", out)

    def test_flow_asks_for_open_delivered_and_dropped_and_checks_the_weeks(self):
        self.jira.search_answer = fx.answers(open_=self.open_work(),
                                             delivered=[fx.at("TEAM-9", "delivered", created="2026-10-01", resolved="2026-10-06")])
        code, out, _ = run(["flow", "plataforma", "--weeks", "2"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.jira.jqls), 3)
        self.assertIn("**Ventana:** 2026-09-28 → 2026-10-08", out)
        self.assertIn("**1 entregados** desde 2026-09-28", out)
        self.assertEqual(run(["flow", "plataforma", "--weeks", "0"], self.jira)[0], 1)

    def test_digest_needs_a_period_and_refuses_a_bad_one(self):
        self.jira.search_answer = fx.answers(open_=self.open_work(), created=[fx.at("TEAM-7", "todo", created="2026-10-02")])
        code, out, _ = run(["digest", "plataforma", "--since", "2026-10-01"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.jira.jqls), 4)
        self.assertIn("**Ventana:** 2026-10-01 → 2026-10-08", out)
        self.assertIn("**0 entregados · 0 descartados · 1 nuevos**", out)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["digest", "plataforma"], self.jira)
        self.assertEqual(run(["digest", "plataforma", "--since", "ayer"], self.jira)[0], 1)
        self.assertEqual(run(["digest", "plataforma", "--since", "2026-10-09"], self.jira)[0], 1)

    def test_desk_reports_the_help_desk_boards_and_refuses_a_view_without_one(self):
        self.jira.search_answer = fx.answers(open_=[fx.at("DESK-1", "todo", created="2026-10-07"),
                                                    fx.at("DESK-2", "waiting", created="2026-08-01")])
        code, out, _ = run(["desk", "plataforma"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("| DESK | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 |", out)
        self.assertIn("Sin SLA", out)
        views.save(fx.view(boards=("TEAM",), name="solo"))
        code, _, err = run(["desk", "solo"], FakeJira())
        self.assertEqual(code, 1)
        self.assertIn("no help desk board", err)

    def test_rollup_gives_a_row_per_view_and_keeps_a_view_that_cannot_be_computed(self):
        views.save(fx.view(boards=("UA",), name="otro"))
        self.jira.search_answer = fx.answers(open_=self.open_work())
        code, out, _ = run(["rollup", "plataforma", "otro"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("| plataforma | 4 | 1 | 1 | 0 | – |", out)
        self.assertIn("| otro | sin perfil: UA |", out)
        data = json.loads(run(["rollup", "plataforma", "--json"], self.jira)[1])
        self.assertEqual(data["rows"][0]["open"], 4)

    def test_no_report_writes_anything_to_jira(self):
        self.jira.search_answer = fx.answers(open_=self.open_work())
        for args in (["status", "plataforma"], ["stalled", "plataforma"], ["blocked", "plataforma"],
                     ["flow", "plataforma"], ["digest", "plataforma", "--since", "2026-10-01"], ["desk", "plataforma"],
                     ["rollup", "plataforma"]):
            run(args, self.jira)
        self.assertEqual(self.jira.writes, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_team_cli.py' 2>&1 | tail -4`
Expected: los 24 tests fallan: `jk team` todavía no es un comando (error de argumentos de `argparse`).

- [ ] **Step 3: Crear el módulo**

```python
"""jk team setup | show | list | status | stalled | blocked | flow | digest | desk | rollup: reports about the boards and the
team a manager follows. They only read Jira; the one thing written is the local view (jk team setup).

Exit codes: 0 done, 1 findings or a refused input (a board without profile, a bad view), 2 could not do it (Jira, disk)."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import namedtuple
from typing import Callable, List

from . import board_profile, people, roles, team, team_render, views, window
from .jira import JiraError

OK, FINDINGS, CANNOT = 0, 1, 2
REPORTS = ("status", "stalled", "blocked", "flow", "digest", "desk")
VERBS = ("setup", "show", "list", "rollup") + REPORTS
Result = namedtuple("Result", "title window payload body seen truncated")


class Refusal(ValueError):
    """A report that cannot be computed honestly (a board without profile)."""


def _describe(view: dict) -> str:
    return (f"## View {view['name']}\n**Boards:** {', '.join(view['boards'])} · "
            f"**Equipo:** {team_render.team_label(view['team'])} · **Estancado desde:** {view['stalled_days']} días")


def _profile_rows(view: dict, profiles: dict) -> list:
    rows = []
    for board in view["boards"]:
        if board not in profiles:
            rows.append([board, "sin perfil"])
        else:
            pending = len(board_profile.open_statuses(profiles[board]))
            rows.append([board, "confirmado" if not pending else f"sin confirmar ({pending} sin decidir)"])
    return rows


def _setup(args, jira) -> int:
    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    chosen = None
    note = ""
    if args.group:
        try:
            total = jira().group_total(args.group)
        except JiraError as exc:
            if "HTTP 404" in str(exc):
                raise ValueError(f"Jira has no group {args.group!r}") from exc
            raise
        chosen, note = {"group": args.group}, f"Grupo {args.group}: {total} miembros."
    elif args.people:
        client = jira()
        found = [people.resolve(client, name, boards[0] if boards else None) for name in args.people]
        chosen = {"people": [{"id": p["id"], "name": p["name"]} for p in found]}
        note = "Personas: " + ", ".join(p["name"] for p in found) + "."
    view = views.build(args.name, boards, chosen, args.stalled_days)
    path = views.save(view)
    print(_describe(view))
    if note:
        print("\n" + note)
    profiles, _ = board_profile.scan()
    lacking = team.missing_profiles(view, profiles)
    if lacking:
        print(f"\nFalta el perfil de: {', '.join(lacking)}. Corré `jk board setup KEY` para cada uno antes de pedir reportes.")
    print(f"\nView guardado en {path}")
    return OK


def _show(args) -> int:
    view = views.load(args.name)
    profiles, _ = board_profile.scan()
    print(_describe(view) + "\n\n" + team_render.table(["Board", "Perfil"], _profile_rows(view, profiles), True))
    return OK


def _list() -> int:
    rows = []
    for name in views.names():
        try:
            view = views.load(name)
            rows.append([name, ", ".join(view["boards"]), team_render.team_label(view["team"])])
        except views.BadView as exc:
            rows.append([name, f"ilegible: {exc}", ""])
    print(team_render.table(["View", "Boards", "Equipo"], rows, True, "_Ningún view. Creá uno con `jk team setup`._"))
    return OK


def _context(name: str):
    view = views.load(name)
    profiles, problems = board_profile.scan()
    lacking = team.missing_profiles(view, profiles)
    if lacking:
        broken = [b for b in lacking if b in problems]
        extra = f" ({', '.join(f'{b}: {problems[b][1]}' for b in broken)})" if broken else ""
        raise Refusal(f"no profile for {', '.join(lacking)}{extra}: run jk board setup {lacking[0]}")
    return view, profiles


def _link(jira) -> Callable[[str], str]:
    return lambda key: f"[{key}]({jira.browse_url(key)})"


def _status(args, jira, view, profiles, conv, today) -> Result:
    issues, cut = team.gather_open(jira, view, profiles, conv)
    report = team.status_report(issues, view, profiles)
    return Result("Estado del equipo", None, report, team_render.render_status(report, args.all), issues, cut)


def _stalled(args, jira, view, profiles, conv, today) -> Result:
    days = args.days if args.days is not None else view["stalled_days"]
    if not 1 <= days <= 365:
        raise ValueError("--days must be a whole number from 1 to 365")
    issues, cut = team.gather_open(jira, view, profiles, conv)
    report = team.stalled_report(issues, today, days)
    return Result("Estancados", None, report, team_render.render_stalled(report, args.all, _link(jira)), issues, cut)


def _blocked(args, jira, view, profiles, conv, today) -> Result:
    issues, cut = team.gather_open(jira, view, profiles, conv)
    report = team.blocked_report(issues, conv, today)
    return Result("Bloqueos", None, report, team_render.render_blocked(report, args.all, _link(jira)), issues, cut)


def _flow(args, jira, view, profiles, conv, today) -> Result:
    weeks = window.weeks(args.weeks)
    first = team.first_week(today, weeks)
    issues, cut1 = team.gather_open(jira, view, profiles, conv)
    delivered, cut2 = team.gather_closed(jira, view, profiles, conv, ("delivered",), first)
    dropped, cut3 = team.gather_closed(jira, view, profiles, conv, ("dropped",), first)
    report = team.flow_report(delivered, dropped, issues, today, weeks)
    return Result("Flujo", (first, today), report, team_render.render_flow(report, args.all, _link(jira)),
                  issues + delivered + dropped, cut1 or cut2 or cut3)


def _digest(args, jira, view, profiles, conv, today) -> Result:
    since, until = window.span(args.since, args.until, today)
    issues, cut1 = team.gather_open(jira, view, profiles, conv)
    delivered, cut2 = team.gather_closed(jira, view, profiles, conv, ("delivered",), since)
    dropped, cut3 = team.gather_closed(jira, view, profiles, conv, ("dropped",), since)
    created, cut4 = team.gather_created(jira, view, profiles, conv, since, until)
    report = team.digest_report(delivered, dropped, created, issues, conv, since, until, today, view["stalled_days"])
    return Result("Resumen del período", (since, until), report,
                  team_render.render_digest(report, args.all, _link(jira)),
                  issues + delivered + dropped, cut1 or cut2 or cut3 or cut4)


def _desk(args, jira, view, profiles, conv, today) -> Result:
    weeks = window.weeks(args.weeks)
    if not team.desk_boards(view, profiles):
        raise team.NoDesk(f"view {view['name']!r} has no help desk board: set one with jk board setup KEY --kind helpdesk")
    first = team.first_week(today, weeks)
    issues, cut1 = team.gather_open(jira, view, profiles, conv)
    delivered, cut2 = team.gather_closed(jira, view, profiles, conv, ("delivered",), first)
    report = team.desk_report(issues, delivered, view, profiles, today, weeks)
    return Result("Mesa de ayuda", (first, today), report, team_render.render_desk(report, args.all),
                  issues + delivered, cut1 or cut2)


BUILDERS = {"status": _status, "stalled": _stalled, "blocked": _blocked, "flow": _flow, "digest": _digest, "desk": _desk}


def _emit(args, verb: str, view: dict, profiles: dict, today: _dt.date, result: Result) -> None:
    notes = roles.notes(result.seen, profiles)
    if args.json:
        print(json.dumps({"view": view["name"], "boards": view["boards"], "consulted": today.isoformat(),
                          "profiles": team_render.profile_state(view, profiles), "truncated": result.truncated,
                          "notes": notes, "report": result.payload}, ensure_ascii=False, indent=2, default=str))
        return
    parts = [team_render.head(result.title, view, profiles, today, result.window)]
    alerts = ([f"La búsqueda llegó al tope de {team.CAP} issues: faltan resultados."] if result.truncated else []) + notes
    if alerts:
        parts.append("\n".join(f"> ⚠ {line}" for line in alerts))
    parts += [result.body, team_render.limits(verb)]
    print("\n\n".join(parts))


def _report(args, jira, conv: dict, today: _dt.date) -> int:
    view, profiles = _context(args.view)
    client = jira()
    _emit(args, args.verb, view, profiles, today, BUILDERS[args.verb](args, client, view, profiles, conv, today))
    return OK


def _rollup(args, jira, conv: dict, today: _dt.date) -> int:
    profiles, _ = board_profile.scan()
    client = jira()
    first = team.first_week(today, 4)
    rows, failed = [], False
    for name in args.views:
        try:
            view = views.load(name)
            lacking = team.missing_profiles(view, profiles)
            if lacking:
                raise Refusal(f"sin perfil: {', '.join(lacking)}")
        except (views.BadView, Refusal) as exc:
            rows.append({"view": name, "error": str(exc)})
            failed = True
            continue
        issues, cut1 = team.gather_open(client, view, profiles, conv)
        delivered, cut2 = team.gather_closed(client, view, profiles, conv, ("delivered",), first)
        rows.append(dict(team.rollup_row(view, issues, delivered, conv, today), truncated=cut1 or cut2))
    if args.json:
        print(json.dumps({"consulted": today.isoformat(), "rows": rows}, ensure_ascii=False, indent=2, default=str))
    else:
        cut = [r["view"] for r in rows if r.get("truncated")]
        alert = (f"\n\n> ⚠ La búsqueda llegó al tope de {team.CAP} issues en: {', '.join(cut)}." if cut else "")
        print(f"## Resumen de equipos\n**Views:** {', '.join(args.views)} · **Consultado:** {today}{alert}\n\n"
              + team_render.render_rollup(rows, args.all) + "\n\n" + team_render.limits("rollup"))
    return FINDINGS if failed else OK


def run(argv: List[str], jira: Callable[[], object], conv: dict, today: Callable[[], _dt.date]) -> int:
    """argv starts at the verb. `jira` builds the client only for the verbs that read Jira."""
    parser = argparse.ArgumentParser(prog="jk team", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)
    setup = sub.add_parser("setup", help="save the boards and the team you follow under a name")
    setup.add_argument("name", help="a short name: lower case letters, digits, - and _")
    setup.add_argument("--boards", required=True, help="Jira project keys, separated by commas, e.g. PLATE,UA")
    who = setup.add_mutually_exclusive_group()
    who.add_argument("--group", help="a Jira group whose members are the team")
    who.add_argument("--people", nargs="+", help="the team as names, emails or account ids")
    setup.add_argument("--stalled-days", type=int, default=7, help="days in the same category before work counts as stalled (default 7)")
    sub.add_parser("show", help="print a view and the state of its boards' profiles").add_argument("name")
    sub.add_parser("list", help="list the saved views")
    for verb, text in (("status", "open work by role, per board and per person"),
                       ("stalled", "active work that has not changed category for N days"),
                       ("blocked", "what is blocked and what waits for a third party"),
                       ("flow", "deliveries per week, lead time and the age of work in flight"),
                       ("digest", "delivered, dropped and new in a period, plus today's blocked and stalled"),
                       ("desk", "help desk boards: age of open work, unowned, waiting, resolution time")):
        p = sub.add_parser(verb, help=text + " (read only)")
        p.add_argument("view")
        p.add_argument("--all", action="store_true", help="do not cut tables at 20 rows")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if verb == "stalled":
            p.add_argument("--days", type=int, help="default: the view's stalled days")
        if verb in ("flow", "desk"):
            p.add_argument("--weeks", type=int, default=4, help="how many weeks, 1 to 52 (default 4)")
        if verb == "digest":
            p.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
            p.add_argument("--until", help="last day, YYYY-MM-DD (default: today)")
    roll = sub.add_parser("rollup", help="one row per view: open, blocked, stalled, delivered, lead time (read only)")
    roll.add_argument("views", nargs="+")
    roll.add_argument("--all", action="store_true")
    roll.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verb == "setup":
            return _setup(args, jira)
        if args.verb == "show":
            return _show(args)
        if args.verb == "list":
            return _list()
        if args.verb == "rollup":
            return _rollup(args, jira, conv, today())
        return _report(args, jira, conv, today())
    except ValueError as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT
```

- [ ] **Step 4: Despachar desde `cli.py`**

El `import` ya incluye `views`, que usa la Task 7.

Reemplazá en `jkan/cli.py` este texto:

```python
from . import board_cli, board_profile, config, journal, kanban, people, preview, render, roles, standup, stats, sync, window
```

por este:

```python
from . import (board_cli, board_profile, config, journal, kanban, people, preview, render, roles, standup, stats, sync,
               team_cli, views, window)
```

Reemplazá en `jkan/cli.py` este texto:

```python
    parser = argparse.ArgumentParser(prog="jk", description=__doc__)
```

por este:

```python
    if len(argv) > 1 and argv[0] == "team" and argv[1] in team_cli.VERBS:
        here = Path(".").resolve()
        team_conv = config.load_conventions(here)
        make = lambda: client(here) if client is not _client else _client(here, command="team")  # noqa: E731
        return team_cli.run(argv[1:], make, team_conv,
                            today or (lambda: window.today_in(team_conv.get("timezone"))))
    parser = argparse.ArgumentParser(prog="jk", description=__doc__)
```

- [ ] **Step 5: Correrlos y ver que pasan**

Run: `python3 -m unittest discover -s tests -p 'test_team_cli.py' 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 6: Suite completa y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
git add jkan/team_cli.py jkan/cli.py tests/test_team_cli.py
git commit -m "feat(team): jk team setup, show, list, status, stalled, blocked, flow, digest, desk and rollup"
```

---

### Task 7: `--view` en `done`, `next` y `blocked`

**Files:**
- Modify: `jkan/cli.py` (cuatro ediciones)
- Test: `tests/test_view_flag.py`

**Interfaces:**
- Consumes: `views.load` (Task 3), `queries._scope` con lista (Task 3).
- Produces: `jk done|next|blocked [--person X] --view VIEW`: las consultas van con `project in (<boards del view>)`, el encabezado nombra los boards y la persona se busca entre los asignables del primer board. `--view` junto con `--jira-project` es un error de argumentos.

- [ ] **Step 1: Escribir los tests**

```python
from __future__ import annotations

import contextlib
import io
import unittest

import team_fixtures as fx
from helpers import FakeJira, config_dir, issue, make_project
from jkan import board_profile, cli, views


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(args + ["--project", str(make_project())], client=lambda project: jira, today=lambda: fx.TODAY)
    return code, out.getvalue(), err.getvalue()


class ViewFlagTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        views.save(fx.view())

    def test_done_next_and_blocked_look_at_the_boards_of_the_view(self):
        for args in (["done", "--since", "2026-10-01"], ["next"], ["blocked"]):
            jira = FakeJira()
            code, _, _ = run(args + ["--view", "plataforma"], jira)
            self.assertEqual(code, 0, args)
            self.assertIn(" AND project in (TEAM, DESK) ", jira.jqls[0], args)

    def test_the_heading_names_the_boards_instead_of_one_project(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [issue("TEAM-1", category="done", changed="2026-10-07")]
        _, out, _ = run(["done", "--since", "2026-10-01", "--view", "plataforma"], jira)
        self.assertIn("**Proyecto:** TEAM, DESK", out)

    def test_a_person_is_looked_up_among_the_people_assignable_in_the_first_board(self):
        jira = FakeJira()
        code, _, _ = run(["next", "--person", "Ana Gómez", "--view", "plataforma"], jira)
        self.assertEqual(code, 0)
        self.assertEqual(set(jira.search_projects), {"TEAM"})

    def test_an_unknown_view_is_refused_before_asking_jira(self):
        jira = FakeJira()
        code, _, err = run(["next", "--view", "nada"], jira)
        self.assertEqual(code, 1)
        self.assertIn("jk team setup nada", err)
        self.assertEqual(jira.jqls, [])

    def test_a_view_and_a_jira_project_together_are_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["next", "--view", "plataforma", "--jira-project", "PLATE"], FakeJira())

    def test_without_the_flag_nothing_changes(self):
        jira = FakeJira()
        run(["next", "--jira-project", "PLATE"], jira)
        self.assertIn(" AND project = PLATE ", jira.jqls[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_view_flag.py' 2>&1 | tail -4`
Expected: 4 de los 6 tests fallan (`--view` todavía no existe: `unrecognized arguments`). Los dos que pasan ya (`...refused_by_the_parser` y `without_the_flag_nothing_changes`) fijan comportamiento que no debe cambiar.

- [ ] **Step 3: Implementar**

Reemplazá en `jkan/cli.py` este texto:

```python
        if name == "done":
            r.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
```

por este:

```python
        if name in ("done", "next", "blocked"):
            r.add_argument("--view", help="only the boards of this saved view (see jk team setup)")
        if name == "done":
            r.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
```

Reemplazá en `jkan/cli.py` este texto:

```python
    if getattr(args, "jira_project", None):
        conv["project"] = args.jira_project
```

por este:

```python
    if getattr(args, "jira_project", None):
        conv["project"] = args.jira_project
    if getattr(args, "view", None):
        if getattr(args, "jira_project", None):
            parser.error("--view and --jira-project cannot be used together")
        try:
            conv["project"] = views.load(args.view)["boards"]
        except views.BadView as exc:
            sys.stderr.write(f"jk: {exc}\n")
            return FINDINGS
```

Reemplazá en `jkan/cli.py` este texto:

```python
        person = people.resolve(jira, args.person, conv.get("project")) if args.person else None
```

por este:

```python
        scope = conv.get("project")  # one project key, or the boards of a view
        person = people.resolve(jira, args.person, scope[0] if isinstance(scope, list) else scope) if args.person else None
```

Reemplazá en `jkan/cli.py` este texto:

```python
        project = conv.get("project")
```

por este:

```python
        project = ", ".join(scope) if isinstance(scope, list) else scope
```

- [ ] **Step 4: Correrlos y ver que pasan, y suite completa**

Run: `python3 -m unittest discover -s tests -p 'test_view_flag.py' 2>&1 | tail -3; python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` en los dos.

- [ ] **Step 5: Commit**

```bash
git add jkan/cli.py tests/test_view_flag.py
git commit -m "feat(reports): --view scopes done, next and blocked to the boards of a view"
```

---

### Task 8: La skill `jira-em`, la instalación y los docs

**Files:**
- Create: `em/SKILL.md`, `tests/test_skills.py`
- Modify: `install.sh` (dos ediciones), `tests/test_install.py` (una), `standup/SKILL.md`, `README.md`, `docs/superpowers/specs/2026-10-09-jira-em-design.md`

**Interfaces:**
- Consumes: `team_cli.VERBS`, `board_cli.VERBS`.
- Produces: `./install.sh` instala `jira-standup` **y** `jira-em` (carpeta `em/`) por defecto; `--with-write` sigue sumando `jira-kanban`.

- [ ] **Step 1: Escribir los tests**

```python
"""The three skills that ship in this repo: each is where install.sh says, is named like its folder, can be told apart by
its description, and the commands the team skill tells the agent to run exist."""
from __future__ import annotations

import re
import unittest

from helpers import ROOT
from jkan import board_cli, team_cli

SKILLS = ((".", "jira-kanban"), ("standup", "jira-standup"), ("em", "jira-em"))


def frontmatter(folder: str) -> dict:
    text = (ROOT / folder / "SKILL.md").read_text(encoding="utf-8")
    block = text.split("---")[1]
    return dict(line.split(": ", 1) for line in block.strip().splitlines())


class SkillsTest(unittest.TestCase):
    def test_each_skill_file_is_named_like_its_skill_and_starts_with_use_when(self):
        for folder, name in SKILLS:
            fm = frontmatter(folder)
            self.assertEqual(fm["name"], name, folder)
            self.assertTrue(fm["description"].startswith("Use when"), name)

    def test_the_personal_skill_never_claims_team_questions(self):
        description = frontmatter("standup")["description"].lower()
        self.assertIsNone(re.search(r"\bteams?\b", description))  # «a teammate» is fine; «the team» is jira-em's
        self.assertNotIn("equipo", description)

    def test_the_team_skill_is_about_the_team_and_points_to_the_other_two(self):
        description = frontmatter("em")["description"]
        self.assertIn("team", description)
        self.assertIn("not about themselves", description)
        self.assertIn("jira-standup", description)
        self.assertIn("jira-kanban", description)

    def test_the_team_skill_calls_only_jk_and_never_writes_to_jira(self):
        text = (ROOT / "em" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("jk.py", text)
        self.assertNotIn("jk create", text)
        self.assertNotIn("jk push", text)
        self.assertNotIn("jk assign", text)

    def test_every_team_and_board_command_the_team_skill_mentions_exists(self):
        text = (ROOT / "em" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jk team (\w+)", text):
            self.assertIn(verb, team_cli.VERBS, verb)
        for verb in re.findall(r"jk board (\w+)", text):
            self.assertIn(verb, board_cli.VERBS, verb)

    def test_the_personal_skill_mentions_only_commands_that_exist(self):
        text = (ROOT / "standup" / "SKILL.md").read_text(encoding="utf-8")
        for verb in re.findall(r"jk board (\w+)", text):
            self.assertIn(verb, board_cli.VERBS, verb)


if __name__ == "__main__":
    unittest.main()
```

La instalación por defecto ahora incluye la skill de equipo:

Reemplazá en `tests/test_install.py` este texto:

```python
    def test_by_default_only_the_read_only_skill_is_linked_for_every_host(self):
```

por este:

```python
    def test_by_default_the_team_skill_is_linked_for_every_host_too(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-em"), str(ROOT / "em"))
        for host in (".claude", ".codex", ".cursor"):
            self.assertEqual(os.readlink(home / host / "skills/jira-em"), "../../.agents/skills/jira-em")

    def test_by_default_only_the_read_only_skills_are_linked_for_every_host(self):
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_skills.py' 2>&1 | tail -4; python3 -m unittest discover -s tests -p 'test_install.py' 2>&1 | tail -4`
Expected: `test_skills.py` falla con 4 errores (`FileNotFoundError: em/SKILL.md`); `test_install.py` falla en `test_by_default_the_team_skill_is_linked_for_every_host_too`.

- [ ] **Step 3: La skill**

````markdown
---
name: jira-em
description: Use when a manager asks about their team or their boards as a whole ("cómo viene mi equipo", "qué está bloqueado en mis boards", "qué está estancado", "resumen de la semana", "cómo andan mis equipos"), not about themselves. Read only. For "what did I do" or "what can I do" use jira-standup, and to create or sync epics use jira-kanban.
---

# jira-em

Answers questions about the **team and the boards a manager follows**, live from Jira, as tables that are read at a glance.
It never writes to Jira.

```bash
jk team <status|stalled|blocked|flow|digest|desk> VIEW ...
jk team rollup VIEW [VIEW ...]
```

| The user asks | Run |
|---|---|
| how is my team doing / how much is open, by person | `jk team status VIEW` |
| what is stuck / has not moved | `jk team stalled VIEW [--days N]` |
| what is blocked, what waits for someone else | `jk team blocked VIEW` |
| how fast do we deliver, lead time | `jk team flow VIEW [--weeks N]` |
| summary of the week / of a period | `jk team digest VIEW --since D [--until D]` |
| how is the help desk (age, unowned, resolution time) | `jk team desk VIEW [--weeks N]` |
| several teams side by side (a Sr EM) | `jk team rollup VIEW VIEW ...` |
| what did <person> do / can do / is blocked on, inside my boards | `jk done\|next\|blocked --person "<name>" --view VIEW` |

## Steps

1. **Find the view.** `jk team list` shows the saved views. If the user has none, or names boards that are not in one,
   create it: `jk team setup NAME --boards KEY,KEY --group <jira group>` (or `--people "<name>" ...`). Ask the user for
   the boards and for the group or the people; never invent them. `jk team show NAME` shows a view and the state of its
   boards' profiles.
2. **Profiles first.** A report is refused (exit 1, "no profile for KEY") until every board of the view has a profile.
   Run `jk board setup KEY` for each. It exits 3 while statuses are undecided: relay each undecided status to the user,
   ask which role it plays (`todo`, `active`, `blocked`, `waiting`, `delivered`, `dropped`), apply the answer with
   `jk board set KEY <role> "<status>"`, and never choose a role yourself. A help desk board needs
   `jk board setup KEY --kind helpdesk`. A report on a profile with undecided statuses still runs and says so.
3. **Dates.** The CLI only takes `YYYY-MM-DD`. Turn the user's words into dates in `America/Argentina/Buenos_Aires` and
   say which window you used ("la semana pasada" is Monday to Sunday of the previous week).
4. **Run it and show the output as it is.** It is already Markdown and ends with a «Límites» section: do not retell it
   unless asked, and repeat those limits if the user draws a conclusion from the numbers. A line starting with `> ⚠`
   at the top says what to distrust (a search that hit its cap, a status the profile has never seen): keep it.
5. **Another person inside the view.** Pass `--person "<name>"`. If the command exits 1 listing candidates, show them
   (name and email) and ask which one; never pick.
6. **Load verdicts.** `jk team status` gives a verdict only for boards with a WIP limit (`jk board limit KEY N`); the
   limit is the team's decision, so ask for it and never invent one.

## Rules

- Read only: never run `create`, `push`, `assign`, anything with `--apply`, or `jk board` writes other than the profile
  commands above.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- Exit code 3 of `jk board` means a person has to decide; it is not an error to retry.
- Questions about the user themselves ("qué hice", "qué puedo hacer", "en qué estoy bloqueado") are `jira-standup`, not this skill.
- Output labels are Spanish; if the user writes in English, the tables stay as they are.
````

- [ ] **Step 4: El instalador**

Reemplazá en `install.sh` este texto:

```bash
#   ./install.sh               the read-only skill: jira-standup
```

por este:

```bash
#   ./install.sh               the read-only skills: jira-standup and jira-em
```

Reemplazá en `install.sh` este texto:

```bash
SKILLS=("jira-standup:standup")
```

por este:

```bash
SKILLS=("jira-standup:standup" "jira-em:em")
```

- [ ] **Step 5: Docs**

La skill personal le avisa al agente que las preguntas de equipo son de `jira-em`:

Reemplazá en `standup/SKILL.md` este texto:

```markdown
Never choose a role yourself.
```

por este:

```markdown
Never choose a role yourself.
7. **Team questions.** If the user asks about their team or their boards as a whole
   ("cómo viene mi equipo", "qué está bloqueado en mis boards"), that is `jira-em`, not this skill. Reports about
   one person inside a saved view take `--view VIEW` here: `jk done|next|blocked --person "<name>" --view VIEW`.
```

Reemplazá en `README.md` este texto:

```markdown
## Perfiles de board
```

por este:

```markdown
## Reportes de equipo

Para quien sigue varios boards y un equipo (EM, Sr EM). Primero se guarda un **view**: los boards y el equipo.
Cada board tiene que tener su perfil (`jk board setup KEY`); sin él, `jk team` se niega y dice cuál falta. Con el perfil
sin confirmar corre y lo avisa en la primera línea.

| Comando | Responde |
|---|---|
| `jk team setup NOMBRE --boards PLATE,UA --group team` | Guarda un view. El equipo es un grupo de Jira (`--group`) o personas (`--people "Ana Gómez" …`); sin equipo, todo lo asignado |
| `jk team show NOMBRE` · `jk team list` | Ver un view y el estado de los perfiles de sus boards · listar los views |
| `jk team status VIEW` | Trabajo abierto por rol, por board y por persona; lo que nadie tiene. Con límite de WIP (`jk board limit KEY N`), un veredicto de carga |
| `jk team stalled VIEW [--days N]` | Lo `active` que lleva N días o más sin cambiar de categoría, con los días desde la última edición |
| `jk team blocked VIEW` | Bloqueado (rol, flag o link) y, aparte, lo que espera a un tercero |
| `jk team flow VIEW [--weeks N]` | Entregas por semana, lead time (mediana y p85, con su n) y edad de lo que está en curso |
| `jk team digest VIEW --since D [--until D]` | Entregado, descartado y nuevo del período, más lo bloqueado y estancado de hoy |
| `jk team desk VIEW [--weeks N]` | Boards `helpdesk`: antigüedad de lo abierto, sin asignar, esperando y tiempo de resolución. Sin SLA |
| `jk team rollup VIEW VIEW …` | Una fila por view: abiertos, bloqueados, estancados, entregados y lead time p85 |

Todos aceptan `--json` y `--all`. Cada reporte abre con el view, los boards, el equipo, la ventana y el estado de los
perfiles; muestra el `n` de cada número; corta las tablas en 20 filas con un `… y N más`; avisa si la búsqueda llegó a su
tope de 1000 issues; y cierra con **Límites**. Para un 1:1, `jk done|next|blocked --person "X" --view VIEW` mira a una
persona dentro de los boards del view.

## Perfiles de board
```

La spec describe cómo se piden las consultas (corregido con lo medido al planificar):

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
Las consultas se arman con los **roles** del perfil como `status in (<ids>)`. Varios boards salen en **una** búsqueda
(`project in (…)`).
```

por este:

```markdown
Lo abierto se pide por board como `status not in (<ids de lo cerrado>)`, así entran los estados todavía sin rol (salen como
«sin rol»); lo entregado y lo descartado, como `status in (<ids>)`. Los ids van **sin comillas**: entre comillas Jira
devuelve otra cosa (medido: 142 issues contra 240). Cada consulta es una sola búsqueda, con un bloque
`(project = X AND …)` por board. Un board sin perfil no se calcula: `jk team` se niega y pide `jk board setup`; con el
perfil sin confirmar corre y lo avisa.
```

- [ ] **Step 6: Revisión manual del enrutamiento entre las dos skills de lectura**

Los tests fijan la estructura (nombres, que la personal no reclame al equipo, que los comandos existan), pero **no pueden probar cómo el modelo elige una skill**. Leé cada frase y confirmá que su `description` es la que corresponde. Si una cae en la skill equivocada, ajustá la `description` y volvé a correr `tests/test_skills.py`.

| Frase | Skill |
|---|---|
| «qué hice ayer» · «qué puedo hacer esta semana» · «en qué estoy bloqueado» | `jira-standup` |
| «cuántos issues cerré el mes pasado» · «mis métricas de velocidad» · «¿Ana tiene lugar para tomar más trabajo?» (una persona) | `jira-standup` |
| «cómo viene mi equipo» · «qué está bloqueado en mis boards» · «qué está estancado hace más de 10 días» | `jira-em` |
| «resumen de la semana de mi equipo» · «cómo anda la mesa de ayuda» · «comparame mis tres equipos» | `jira-em` |

- [ ] **Step 7: Verificar en las dos versiones de Python y commit**

```bash
rg -n "jira-kanban/jk\.py" -g '!docs/**' .      # sin resultados
python3 -m unittest discover -s tests 2>&1 | tail -3
/usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
git add em/SKILL.md install.sh standup/SKILL.md README.md docs/superpowers/specs/2026-10-09-jira-em-design.md tests/test_skills.py tests/test_install.py
git commit -m "feat(skills): jira-em, installed by default; docs and spec for the team reports"
```

Expected: `Ran 439 tests ... OK` dos veces.

---

### Task 9: Aceptación contra el Jira real y cierre de la fase

**Files:**
- Modify: `docs/superpowers/specs/2026-10-09-jira-em-design.md` (sección nueva al final)

Todo es **solo lectura** y usa un directorio de configuración temporal, así que no toca tu `~/.config/jk`. Se usa `python3 jk.py` en vez de `jk` para no instalar nada en tu `PATH`.

- [ ] **Step 1: Perfiles y views de prueba**

```bash
export JK_CONFIG_DIR="$(mktemp -d)"
for k in PLATE UA; do python3 jk.py board setup $k >/dev/null; echo "$k exit $?"; done   # PLATE 0, UA 3
python3 jk.py board set UA waiting "ON HOLD" "AWAITING APPROVAL" >/dev/null; echo "exit $?"   # 0
python3 jk.py board setup PEHD --kind helpdesk >/dev/null; python3 jk.py board setup CDSP --kind helpdesk >/dev/null
python3 jk.py team setup plataforma --boards PLATE,UA --group team
python3 jk.py team setup ayuda --boards PEHD,CDSP
```

Expected: el primer `setup` de `UA` sale con 3 (dos estados sin decidir) y el `set` lo deja en 0; `team setup` imprime `Grupo team: 7 miembros.`.

- [ ] **Step 2: Correr los siete reportes**

```bash
python3 jk.py team status plataforma
python3 jk.py team stalled plataforma
python3 jk.py team blocked plataforma
python3 jk.py team flow plataforma --weeks 4
python3 jk.py team digest plataforma --since 2026-10-01
python3 jk.py team desk ayuda
python3 jk.py team rollup plataforma ayuda
python3 jk.py team desk plataforma; echo "exit $?"      # 1: ese view no tiene mesa de ayuda
```

Expected: todos salen con 0 salvo el último (1, «has no help desk board»). Cada uno abre con `View`, `Boards`, `Equipo`, `Consultado` y `Perfiles`, y cierra con **Límites**. Revisá a ojo que los números tengan sentido para tus boards.

- [ ] **Step 3: El invariante que no depende del día — el reporte cuenta lo que cuenta Jira**

```bash
python3 -I - <<'EOF'
import sys
sys.path.insert(0, ".")
from pathlib import Path
from jkan import board_profile, config, queries, team, views
from jkan.jira import Jira
j = Jira(*config.credentials(Path(".")))
profiles, _ = board_profile.scan()
view = views.load("plataforma")
conv = config.load_conventions(Path("."))
count = lambda jql: j._send("POST", "/rest/api/3/search/approximate-count", {"jql": jql.split(" ORDER BY")[0]})["count"]
jql = queries.team_open(view["boards"], profiles, view["team"])
issues, cut = team.gather_open(j, view, profiles, conv)
epics = count(f"({jql.split(' ORDER BY')[0]}) AND issuetype = Epic")
print(f"jira {count(jql)} == report {len(issues)} + epics {epics}: {count(jql) == len(issues) + epics} (truncated={cut})")
EOF
```

Expected: `... : True (truncated=False)`. Es el chequeo cruzado de la fase: el total del reporte más los epics excluidos a propósito tiene que ser **igual** a lo que Jira cuenta para la misma consulta. Medido el 2026-10-09 con este mismo código: `jira 179 == report 159 + epics 20`.

- [ ] **Step 4: Dejar los números en la spec**

Agregá al final de `docs/superpowers/specs/2026-10-09-jira-em-design.md` esta sección, con los números de **tu** corrida (los de abajo son los medidos el 2026-10-09 mientras se escribía el plan; el único que tiene que coincidir siempre es el del invariante):

```markdown
## Resultados de la fase 2

Medido con `jk team` sobre el Jira real el 2026-10-09 (solo lectura). Views de prueba: `plataforma` (boards PLATE y UA, grupo `team`, 7 miembros) y `ayuda` (PEHD y CDSP, sin equipo; CDSP con el perfil sin confirmar).

| Medida | Resultado |
|---|---|
| `status plataforma`: abiertos | 159 (PLATE 80, UA 79), más 20 epics excluidos a propósito |
| Cuenta de Jira para la misma consulta | 179 = 159 + 20 (el invariante se cumple) |
| Sin asignar (PLATE / UA) | 56 / 76 |
| `stalled` (7 días o más en la categoría) | 10 de 16 en curso |
| `blocked` / esperando | 3 / 1 |
| `flow` (4 semanas) | 60 entregados, 0 descartados; por semana 17 · 9 · 14 · 20; lead time mediana 1 d, p85 16 d (n=60) |
| `digest` desde 2026-10-01 | 26 entregados · 0 descartados · 163 nuevos; hoy 3 bloqueados y 10 estancados |
| `desk ayuda` (4 semanas) | PEHD: 12 abiertos, 7 sin asignar, 34 resueltos; CDSP: 8 abiertos, 136 resueltos |
| `rollup plataforma ayuda` (abiertos / bloqueados / estancados / entregados) | 159 / 3 / 10 / 60 y 20 / 0 / 3 / 170 |
| Búsquedas que llegaron al tope de 1000 issues | ninguna |
```

- [ ] **Step 5: Verificación final en las dos versiones de Python y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
/usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
git status --short
git add docs/superpowers/specs/2026-10-09-jira-em-design.md
git commit -m "docs(spec): phase 2 results"
```

Expected: `Ran 439 tests ... OK` dos veces y `git status --short` vacío antes del último `git add`. La rama `feat/jira-em-fase-2` queda lista para que la revises y la publiques vos. Después de integrarla, corré `./install.sh` una vez para que `jira-em` quede enlazada en tus agentes.

---

## Después de este plan

1. **Fase 3, `jk plan` y `jk apply`:** necesita probar si `!` entrega una terminal interactiva, **un proyecto de pruebas** para escribir de verdad y la decisión sobre los comandos `--apply` que ya existen. Reusa `views` (el plan solo toca issues de los boards del view) y los perfiles (destino por id de estado).
2. **Fase 4, cierre:** renombrar el repo y actualizar `git-guardrails.sh` y `AGENTS.md`.
3. **Pendientes que esta fase no cierra:** `jk done` y `jk stats` personales siguen pidiendo por categoría (los estados archivados en la categoría *new* no entran hasta que se les arme la consulta por rol, como se hizo acá para el equipo), y los ocho menores diferidos de la fase 1 siguen en el ledger de esa ejecución.
