# jira-em, fases 0 y 1: `jk` en el PATH, perfiles de board y roles — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `jk` quede instalado en el PATH, que cada board tenga un perfil con el rol de cada estado (confirmado por una persona una vez) y que los reportes de siempre (`done`, `next`, `blocked`, `load`, `stats`) lean esos roles en vez de la categoría de Jira, que está mal puesta en 38 proyectos.

**Architecture:** Módulos planos nuevos en `jkan/` (`roles`, `board_profile`, `board_cli`), todos del lado de lectura; el cliente de Jira suma dos lecturas y `status_id`. Los perfiles son JSON en `~/.config/jk/profiles/` (o `$JK_CONFIG_DIR`). `cli.py` carga los perfiles, `standup.search` anota el rol de cada issue y los reportes usan el rol; sin perfil, caen a la categoría como hasta hoy. Un test fija que el lado de lectura nunca importa el de escritura.

**Tech Stack:** Python 3.9 o más (solo biblioteca estándar), `unittest`, bash.

**Spec:** `docs/superpowers/specs/2026-10-09-jira-em-design.md` (secciones «Estructura de código e instalación» y «Perfiles de board y roles»; fases 0 y 1).

## Alcance de este plan

Cubre las **fases 0 y 1** de la spec. Las fases 2 (views y reportes de equipo), 3 (`jk plan` / `jk apply`) y 4 (cierre) van en planes propios, que se escriben cuando esta fase esté medida: la fase 2 depende de los números de `jk board survey` y de armar las consultas por rol, y la fase 3 de probar si hay terminal interactiva bajo `!` y de elegir un proyecto de pruebas.

## Global Constraints

- Python **3.9 o más, solo biblioteca estándar**; la suite corre igual con `python3` y con `/usr/bin/python3` (3.9).
- Pruebas con `python3 -m unittest discover -s tests` y un Jira falso (`tests/helpers.py`): nada sale a la red.
- TDD y **conventional commits, sin atribución de IA** (regla del usuario). No hay push, PR ni merge: los hace el usuario.
- Documentación para personas en castellano rioplatense; **código, skills y mensajes del CLI en inglés** (las etiquetas de los reportes siguen en castellano, como hoy).
- Las credenciales `IC_JIRA_*` no se imprimen ni se commitean.
- Los reportes y `jk board` no escriben en Jira; `jk board` escribe solo `~/.config/jk` (o `$JK_CONFIG_DIR`).
- Ningún módulo del lado de lectura importa uno del lado de escritura (`tests/test_boundaries.py`).
- Los tests nunca leen ni escriben el `~/.config/jk` real: `tests/helpers.py` apunta `JK_CONFIG_DIR` a un directorio temporal al importarse.

## Desvíos respecto de la spec (a revisar junto con este plan)

| Spec | Este plan | Por qué (medido) |
|---|---|---|
| Subpaquetes `core/ reports/ write/ profile/` | Módulos planos y `tests/test_boundaries.py` | **25 archivos de tests** hacen `from jkan import <módulo>`; mover todo reescribe esos imports sin cambiar comportamiento. La regla que importa (lectura no importa escritura) queda igual de verificada |
| «Partir `cli.py` en un módulo por skill» | No se parte; se suma `board_cli.py` | Refactor sin dependencia con esta fase |
| `jk board setup` sale con código **2** si hay decisiones abiertas | Sale con **3** | En `jk` el 2 ya significa «no se pudo» (`CANNOT`, `jkan/cli.py`); si la skill lee 2 como «hay que decidir» confundiría un error de red con una pregunta |
| Perfil con `roles` y `open` guardados | Se guarda la lista `statuses`; `roles` y `open` se calculan | Un solo lugar de verdad, sin que dos copias puedan contradecirse |
| «Los 29 proyectos mal categorizados dan lo correcto» | `jk board survey` mide los proyectos con la categoría mal puesta (38 con el diccionario actual); un `Done` en «en curso» cuenta como cerrado y no como WIP | La consulta de `done` sigue siendo por categoría y no trae los estados archivados en la categoría *new*; eso se arregla con consultas por rol en la fase 2 |
| Perfil con `access: limited` si Jira devuelve 403 | `access` queda siempre en `full` | Esta fase solo lee estados; `limited` se escribe cuando exista una lectura que pueda dar 403 (colas de JSM, fase 2) |
| `jk.py` no mencionado | `jk.py` pasa a modo `755` | Está en `644` en git; el instalador lo enlaza al PATH |

**Hallazgo para decidir (no se resuelve acá):** `jk create`, `jk push` y `jk assign --apply` escriben en Jira sin exigir terminal interactiva ni `APRUEBO`; solo los frena el hook local `git-guardrails.sh`, que los EM no tienen, y `jk` es un solo binario. Está anotado en los «Riesgos» de la spec (Task 8). La fase 3 tiene que decidir si les aplica el mismo guardia.

## Review Focus

Modos de falla que la spec implica y que ninguna tarea de lectura/escritura cubre «de oficio»; cada uno tiene su test en la tarea que es dueña del código.

1. **Un estado que existe solo para un tipo de issue** (`RELEASED` solo en `Task` de `UA`) tiene que resolver su rol → `BuildTest.test_a_status_that_exists_for_one_issue_type_only_still_gets_its_role` (Task 5).
2. **Jira contesta sin estados** para la clave → no se guarda un perfil «completo» vacío → `SetupTest.test_a_jira_answer_with_no_statuses_is_not_saved_as_a_complete_profile` (Task 6).
3. **Un perfil escrito por un `jk` más nuevo** no se lee mal en silencio → `PersistenceTest.test_a_profile_from_a_newer_jk_is_refused_by_load_and_skipped_by_load_all` y `ShowAndCheckTest.test_show_of_a_profile_from_a_newer_jk_exits_1` (Tasks 5 y 6).
4. **Un issue sin `status_id`** (respuesta vieja o recortada) con perfil presente → «estado desconocido», sin `KeyError` → `AnnotateTest.test_an_issue_without_a_status_id_is_unknown_to_the_profile_and_does_not_crash` (Task 4).
5. **Nombrar dos veces el mismo estado** en un `set` es inofensivo → `AssignTest.test_naming_a_status_twice_in_one_call_is_harmless` (Task 5).

Además quedan fijados por tests de las tareas: que re-correr `setup` no pierde decisiones humanas ni siquiera con un estado renombrado, que `set` es todo o nada, que un archivo de perfil corrupto no tira un traceback y que `jk board EPIC` (el tablero local) sigue andando (`tests/test_board.py`, ya existente).

## Estructura de archivos

| Archivo | Responsabilidad | Task |
|---|---|---|
| `tests/test_boundaries.py` (nuevo) | Fija quién puede importar a quién | 1 |
| `install.sh`, `tests/test_install.py` (reemplazo) | `jk` en el PATH; `--with-write` | 2 |
| `jkan/jira.py` (edición) | `project_statuses`, `projects`, `status_id` en las búsquedas | 3 |
| `tests/helpers.py` (edición) | Aislar la configuración; `FakeJira.project_statuses/projects` | 3 |
| `jkan/roles.py` (nuevo) | Roles, propuesta por estado, anotar issues, avisos | 4 |
| `jkan/board_profile.py` (nuevo) | Perfil: construir, asignar, guardar, cargar | 5 |
| `tests/shapes.py` (nuevo) | Formas de workflow medidas en el Jira real | 5 |
| `jkan/board_cli.py` (nuevo), `jkan/cli.py` (edición) | `jk board setup/set/show/check/survey` | 6 |
| `jkan/standup.py`, `jkan/stats.py`, `jkan/render.py`, `jkan/cli.py` (edición) | Los reportes leen roles y avisan qué perfil falta | 7 |
| `README.md`, `SKILL.md`, `standup/SKILL.md`, la spec (edición) | Docs y correcciones a la spec | 8 |

Línea base antes de empezar: **244 tests en verde** (`python3 -m unittest discover -s tests`). Al terminar: **320**.

---

### Task 1: Fijar quién puede importar a quién

**Files:**
- Create: `tests/test_boundaries.py`

**Interfaces:**
- Produces: la regla «lectura no importa escritura; el núcleo no importa ningún lado; todo módulo nuevo se clasifica» que cumplen las tareas 4 a 7.

- [ ] **Step 1: Crear la rama de trabajo**

```bash
cd Harness/jira-kanban
git switch -c feat/jira-em-fases-0-1
python3 -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 244 tests ... OK`.

- [ ] **Step 2: Escribir el test**

```python
"""The read side of jk never imports the write side, and the shared core imports neither (spec 2026-10-09, «Estructura»).

cli.py is the composition root: it wires both sides on purpose and is the only module allowed to."""
from __future__ import annotations

import ast
import unittest

from helpers import ROOT

PACKAGE = ROOT / "jkan"
CORE = {"jira", "config", "journal", "people"}
READ = {"window", "queries", "standup", "stats", "render", "roles", "board_profile", "board_cli"}
WRITE = {"sync", "spec", "description", "evidence", "kanban", "template", "preview"}
COMPOSITION_ROOT = {"cli", "__init__"}


def imports_of(source: str) -> set:
    """The sibling modules a module imports with `from . import x` or `from .x import y`."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module is None:
                found |= {alias.name for alias in node.names}
            else:
                found.add(node.module.split(".")[0])
    return found


def existing(names: set) -> list:
    return sorted(n for n in names if (PACKAGE / f"{n}.py").is_file())


def imports_in(name: str) -> set:
    return imports_of((PACKAGE / f"{name}.py").read_text(encoding="utf-8"))


class BoundariesTest(unittest.TestCase):
    def test_imports_of_reads_both_import_forms(self):
        source = "from . import sync, queries\nfrom .jira import Jira\nimport json\n"
        self.assertEqual(imports_of(source), {"sync", "queries", "jira"})

    def test_every_module_belongs_to_a_side(self):
        on_disk = {p.stem for p in PACKAGE.glob("*.py")}
        self.assertEqual(sorted(on_disk - CORE - READ - WRITE - COMPOSITION_ROOT), [],
                         "a new module must be listed in CORE, READ or WRITE in tests/test_boundaries.py")

    def test_the_read_side_never_imports_the_write_side(self):
        for name in existing(READ):
            self.assertEqual(imports_in(name) & WRITE, set(), f"{name} imports the write side")

    def test_the_core_imports_neither_side(self):
        for name in existing(CORE):
            self.assertEqual(imports_in(name) & (READ | WRITE), set(), f"{name} imports a side")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Correrlo**

Run: `python3 -m unittest discover -s tests -p 'test_boundaries.py' -v 2>&1 | tail -8`
Expected: PASS (4 tests). Este test **fija un invariante que hoy se cumple**; no impulsa código nuevo. Por eso hay que probar que puede fallar.

- [ ] **Step 4: Verificar que falla cuando se rompe la regla**

```bash
sd -F 'from . import queries' 'from . import queries, sync' jkan/standup.py
python3 -m unittest discover -s tests -p 'test_boundaries.py' 2>&1 | tail -4
git checkout jkan/standup.py
```

Expected: `FAIL: test_the_read_side_never_imports_the_write_side` con `standup imports the write side`. Después del `git checkout`, la suite vuelve a estar en verde.

- [ ] **Step 5: Commit**

```bash
git add tests/test_boundaries.py
git commit -m "test(boundaries): the read side of jk must not import the write side"
```

---

### Task 2: `jk` en el PATH e instalación con `--with-write`

**Files:**
- Replace: `install.sh`
- Replace: `tests/test_install.py`
- Mode: `jk.py` pasa a `755`

**Interfaces:**
- Produces: `~/.local/bin/jk` apuntando a `jk.py`; `./install.sh` instala `jira-standup`, `./install.sh --with-write` suma `jira-kanban`.

- [ ] **Step 1: Reemplazar los tests de instalación**

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


def install(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(["bash", str(ROOT / "install.sh"), *args], env=env, capture_output=True, text=True)


def fresh_home() -> Path:
    return Path(tempfile.mkdtemp(prefix="jk-home-"))


class InstallTest(unittest.TestCase):
    def test_by_default_only_the_read_only_skill_is_linked_for_every_host(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-standup"), str(ROOT / "standup"))
        for host in (".claude", ".codex", ".cursor"):
            self.assertEqual(os.readlink(home / host / "skills/jira-standup"), "../../.agents/skills/jira-standup")
        self.assertFalse(os.path.lexists(home / ".agents/skills/jira-kanban"))
        self.assertEqual(install(home).returncode, 0)  # re-running is safe

    def test_with_write_adds_the_skill_that_writes_to_jira(self):
        home = fresh_home()
        self.assertEqual(install(home, "--with-write").returncode, 0)
        self.assertEqual(os.readlink(home / ".agents/skills/jira-kanban"), str(ROOT))
        for host in (".claude", ".codex", ".cursor"):
            for name in ("jira-kanban", "jira-standup"):
                self.assertEqual(os.readlink(home / host / "skills" / name), f"../../.agents/skills/{name}")

    def test_running_it_again_without_the_flag_does_not_remove_a_skill_installed_before(self):
        home = fresh_home()
        install(home, "--with-write")
        install(home)
        self.assertTrue(os.path.islink(home / ".agents/skills/jira-kanban"))

    def test_jk_is_put_on_the_path_and_is_executable(self):
        home = fresh_home()
        self.assertEqual(install(home).returncode, 0)
        self.assertEqual(os.readlink(home / ".local/bin/jk"), str(ROOT / "jk.py"))
        self.assertTrue(os.access(ROOT / "jk.py", os.X_OK))

    def test_a_real_file_named_jk_is_never_replaced(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/jk").write_text("mine", encoding="utf-8")
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)
        self.assertEqual((home / ".local/bin/jk").read_text(encoding="utf-8"), "mine")

    def test_a_real_directory_is_never_replaced(self):
        home = fresh_home()
        (home / ".agents/skills/jira-standup").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to replace", result.stderr)

    def test_an_unknown_argument_is_refused(self):
        self.assertEqual(install(fresh_home(), "--wat").returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_install.py' 2>&1 | tail -15`
Expected: **4 tests fallan**: `test_by_default_only_the_read_only_skill_is_linked_for_every_host` (hoy instala las dos), `test_with_write_adds_the_skill_that_writes_to_jira` (argumento desconocido), `test_jk_is_put_on_the_path_and_is_executable` y `test_a_real_file_named_jk_is_never_replaced` (no existe `~/.local/bin/jk`).

- [ ] **Step 3: Reemplazar el instalador**

```bash
#!/usr/bin/env bash
# Install jk and its skills for Claude Code, Codex and Cursor.
#   ./install.sh               the read-only skill: jira-standup
#   ./install.sh --with-write  also the skill that writes to Jira: jira-kanban
# CLI: ~/.local/bin/jk points at jk.py; the skills call `jk`, never another skill's folder.
# Skills (same layout as WayOfWork): ~/.agents/skills/<name> points at this repo (jira-kanban) or at its standup/
# folder (jira-standup); ~/.claude/skills/<name>, ~/.codex/skills/<name> and ~/.cursor/skills/<name> point at
# ../../.agents/skills/<name> (measured: ~/.cursor/skills held only explicit links, so Cursor needs its own).
# Re-running is safe and never removes a skill installed before. A real file or directory where a link goes is
# never replaced: the script stops with exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=("jira-standup:standup")  # name:folder inside the repo ("" is the repo itself)
case "${1:-}" in
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  --with-write) SKILLS+=("jira-kanban:") ;;
  "") ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

link() {  # link <target> <path>: create or refresh a symlink, never replace a real file or directory
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "refusing to replace $2: it is not a symlink; move it away and re-run" >&2
    return 1
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
}

status=0
for entry in "${SKILLS[@]}"; do
  NAME="${entry%%:*}"
  SUB="${entry#*:}"
  TARGET="$REPO${SUB:+/$SUB}"
  link "$TARGET" "$HOME/.agents/skills/$NAME" || exit 1
  for host in .claude .codex .cursor; do
    link "../../.agents/skills/$NAME" "$HOME/$host/skills/$NAME" || status=1
  done
  echo "skill: $NAME (Claude Code, Codex, Cursor) -> $TARGET"
done
chmod +x "$REPO/jk.py"
link "$REPO/jk.py" "$HOME/.local/bin/jk" || status=1
echo "cli: jk -> $REPO/jk.py"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "note: add ~/.local/bin to PATH to use jk" >&2 ;; esac
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; jk needs it" >&2; status=1; }
exit "$status"
```

- [ ] **Step 4: Correr los tests y registrar el modo ejecutable**

```bash
python3 -m unittest discover -s tests -p 'test_install.py' 2>&1 | tail -4
git ls-files -s jk.py            # hoy: 100644
git add --chmod=+x jk.py
git ls-files -s jk.py            # debe decir 100755
```

Expected: `OK` en los 7 tests; `jk.py` pasa de `100644` a `100755`.

- [ ] **Step 5: Suite completa y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
git add install.sh tests/test_install.py jk.py
git commit -m "feat(install): put jk on the PATH; --with-write installs the skill that writes to Jira"
```

---

### Task 3: El cliente de Jira lee estados y proyectos; las búsquedas traen `status_id`

**Files:**
- Modify: `jkan/jira.py` (tres ediciones)
- Modify: `tests/test_jira.py`, `tests/test_search.py`, `tests/helpers.py`

**Interfaces:**
- Produces: `Jira.project_statuses(key) -> List[{"types": [str], "statuses": [{"id", "name", "category"}]}]` con `category` en `todo|in_progress|done`; `Jira.projects() -> List[{"key", "name", "type", "style"}]`; cada issue de `Jira.search` trae `status_id`.
- Produces (tests): `helpers.config_dir()` crea un directorio temporal y lo asigna a `JK_CONFIG_DIR`; `FakeJira.status_groups` (clave de proyecto → grupos) y `FakeJira.project_list`, con `FakeJira.project_statuses(key)` y `FakeJira.projects()`.

- [ ] **Step 1: Escribir los tests del cliente**

Reemplazá en `tests/test_jira.py` este texto:

```python
if __name__ == "__main__":
    unittest.main()
```

por este:

```python
STATUSES = [
    {"id": "10", "name": "Task", "subtask": False, "statuses": [
        {"id": "1", "name": "To Do", "statusCategory": {"key": "new"}},
        {"id": "2", "name": "Done", "statusCategory": {"key": "done"}}]},
    {"id": "11", "name": "Subtarea", "subtask": True, "statuses": [
        {"id": "2", "name": "Done", "statusCategory": {"key": "done"}},
        {"id": "1", "name": "To Do", "statusCategory": {"key": "new"}}]},
    {"id": "12", "name": "Epic", "subtask": False, "statuses": [
        {"id": "1", "name": "To Do", "statusCategory": {"key": "new"}},
        {"id": "3", "name": "ON HOLD", "statusCategory": {"key": "indeterminate"}},
        {"id": "2", "name": "Done", "statusCategory": {"key": "done"}}]},
]


class JiraProfileTest(unittest.TestCase):
    def test_project_statuses_groups_the_issue_types_that_share_a_workflow(self):
        jira, rec = client({("GET", "/rest/api/3/project/UA/statuses"): STATUSES})
        groups = jira.project_statuses("UA")
        self.assertEqual([g["types"] for g in groups], [["Task", "Subtarea"], ["Epic"]])
        self.assertEqual(groups[0]["statuses"], [{"id": "1", "name": "To Do", "category": "todo"},
                                                 {"id": "2", "name": "Done", "category": "done"}])
        self.assertEqual(groups[1]["statuses"][1], {"id": "3", "name": "ON HOLD", "category": "in_progress"})
        self.assertEqual(rec.calls[0][:2], ("GET", "/rest/api/3/project/UA/statuses"))

    def test_projects_follow_the_pages_and_keep_type_and_style(self):
        pages = [{"values": [{"key": "UA", "name": "core", "projectTypeKey": "software", "style": "next-gen"}],
                  "isLast": False},
                 {"values": [{"key": "CDSP", "name": "desk", "projectTypeKey": "service_desk", "style": "next-gen"}],
                  "isLast": True}]
        jira, rec = client({("GET", "/rest/api/3/project/search"): lambda body: pages.pop(0)})
        self.assertEqual([(p["key"], p["type"], p["style"]) for p in jira.projects()],
                         [("UA", "software", "next-gen"), ("CDSP", "service_desk", "next-gen")])
        self.assertIn("startAt=0", rec.calls[0][1])
        self.assertIn("startAt=100", rec.calls[1][1])

    def test_search_keeps_the_status_id_the_profiles_are_keyed_by(self):
        raw = {"key": "UA-1", "fields": {"summary": "S", "issuetype": {"name": "Task"},
                                         "status": {"id": "7", "name": "Review",
                                                    "statusCategory": {"key": "indeterminate"}}}}
        jira, _ = client({("GET", "/rest/api/3/field"): FIELDS, ("POST", "/rest/api/3/search/jql"): {"issues": [raw]}})
        found = jira.search("project = UA")
        self.assertEqual((found[0]["status_id"], found[0]["status"], found[0]["category"]), ("7", "Review", "in_progress"))


if __name__ == "__main__":
    unittest.main()
```

Y la igualdad exacta de `test_search_normalizes_an_issue_and_follows_the_pages` ahora incluye el `status_id`:

Reemplazá en `tests/test_search.py` este texto:

```python
"status": "PROCESANDO",
            "category": "in_progress", "parent": {"key": "PLATE-1", "summary": "Épica"
```

por este:

```python
"status": "PROCESANDO", "status_id": "",
            "category": "in_progress", "parent": {"key": "PLATE-1", "summary": "Épica"
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_jira.py' 2>&1 | tail -6; python3 -m unittest discover -s tests -p 'test_search.py' 2>&1 | tail -6`
Expected: `test_jira.py` falla con `AttributeError: 'Jira' object has no attribute 'project_statuses'` / `'projects'` y un `KeyError: 'status_id'`; `test_search.py` falla en `test_search_normalizes_an_issue_and_follows_the_pages` porque el diccionario esperado ya trae `status_id` y el real todavía no.

- [ ] **Step 3: Implementar en el cliente**

Reemplazá en `jkan/jira.py` este texto:

```python
from typing import Callable, List, Optional
```

por este:

```python
from typing import Callable, Dict, List, Optional
```

Reemplazá en `jkan/jira.py` este texto:

```python
"status": status.get("name", ""), "category": _state(status),
```

por este:

```python
"status": status.get("name", ""), "status_id": status.get("id", ""), "category": _state(status),
```

Reemplazá en `jkan/jira.py` este texto:

```python
    @staticmethod
    def _blocker(link: dict, wanted: str) -> Optional[dict]:
```

por este:

```python
    def project_statuses(self, key: str) -> List[dict]:
        """The workflows of a project: one entry per distinct set of statuses, with the issue types that share it.

        Each status is {"id", "name", "category"} with category todo, in_progress or done. Read only."""
        raw = self._send("GET", f"/rest/api/3/project/{urllib.parse.quote(key)}/statuses")
        groups: Dict[tuple, dict] = {}
        for kind in raw:
            statuses = [{"id": s["id"], "name": s["name"],
                         "category": CATEGORY.get((s.get("statusCategory") or {}).get("key", ""), "")}
                        for s in kind.get("statuses", [])]
            group = groups.setdefault(tuple(sorted(s["id"] for s in statuses)), {"types": [], "statuses": statuses})
            group["types"].append(kind["name"])
        return list(groups.values())

    def projects(self) -> List[dict]:
        """Every project the account can see, as {key, name, type, style}. Read only; follows the result pages."""
        found: List[dict] = []
        start = 0
        while True:
            page = self._send("GET", f"/rest/api/3/project/search?maxResults=100&startAt={start}")
            found += [{"key": p["key"], "name": p.get("name") or "", "type": p.get("projectTypeKey") or "",
                       "style": p.get("style") or ""} for p in page.get("values", [])]
            if page.get("isLast", True) or not page.get("values"):
                return found
            start += 100

    @staticmethod
    def _blocker(link: dict, wanted: str) -> Optional[dict]:
```

- [ ] **Step 4: Correrlos y ver que pasan**

Run: `python3 -m unittest discover -s tests -p 'test_jira.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_search.py' 2>&1 | tail -3`
Expected: `OK` en los dos.

- [ ] **Step 5: Preparar los tests de las tareas siguientes (aislar la configuración y ampliar el Jira falso)**

Reemplazá en `tests/helpers.py` este texto:

```python
import sys
import tempfile
```

por este:

```python
import os
import sys
import tempfile
```

Reemplazá en `tests/helpers.py` este texto:

```python
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
```

por este:

```python
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def config_dir() -> Path:
    """Point jk at an empty config directory, so no test reads or writes the real ~/.config/jk."""
    path = Path(tempfile.mkdtemp(prefix="jk-config-"))
    os.environ["JK_CONFIG_DIR"] = str(path)
    return path


config_dir()  # every test run starts isolated, even the tests that never ask for a profile
```

Reemplazá en `tests/helpers.py` este texto:

```python
        self.jqls: List[str] = []
```

por este:

```python
        self.jqls: List[str] = []
        self.status_groups: Dict[str, List[dict]] = {}  # project key -> what Jira.project_statuses returns
        self.project_list: List[dict] = []  # what Jira.projects returns
```

Reemplazá en `tests/helpers.py` este texto:

```python
    def update(self, key: str, fields: dict) -> None:
        for name in ("summary", "description"):
```

por este:

```python
    def project_statuses(self, key: str) -> List[dict]:
        from jkan.jira import JiraError
        if key not in self.status_groups:
            raise JiraError(f"GET /rest/api/3/project/{key}/statuses: HTTP 404")
        return [dict(g, statuses=[dict(s) for s in g["statuses"]]) for g in self.status_groups[key]]

    def projects(self) -> List[dict]:
        return [dict(p) for p in self.project_list]

    def update(self, key: str, fields: dict) -> None:
        for name in ("summary", "description"):
```

- [ ] **Step 6: Suite completa y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
git add jkan/jira.py tests/helpers.py tests/test_jira.py tests/test_search.py
git commit -m "feat(jira): read project statuses and projects; search keeps the status id"
```

Expected: `OK`.

---

### Task 4: Roles — qué significa cada estado

**Files:**
- Create: `jkan/roles.py`
- Test: `tests/test_roles.py`

**Interfaces:**
- Produces: `ROLES`, `CLOSED = ("delivered", "dropped")`, `IN_FLIGHT = ("active", "blocked", "waiting")`; `normalize(text) -> str`; `propose(status) -> {"role", "confidence", "why", "suggest", "mismatch"}`; `project_of(key) -> str`; `role_of(issue) -> Optional[str]`; `source_of(issue) -> "profile"|"category"`; `annotate(issues, profiles) -> issues`; `notes(issues, profiles) -> List[str]`.
- Consumes: `status = {"id", "name", "category"}` con `category` en `todo|in_progress|done`; `profiles = {KEY: {"statuses": [{"id", "name", "role"}]}}`.

- [ ] **Step 1: Escribir los tests**

```python
from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts the skill on sys.path)
from jkan import roles


def status(name, category, ident="1"):
    return {"id": ident, "name": name, "category": category}


PROFILES = {"GDNC": {"statuses": [{"id": "22", "name": "Done", "role": "delivered"},
                                  {"id": "25", "name": "ON HOLD", "role": None}]}}


class NormalizeTest(unittest.TestCase):
    def test_accents_case_and_punctuation_do_not_matter(self):
        self.assertEqual(roles.normalize("  Pend. Finalización "), "pend finalizacion")
        self.assertEqual(roles.normalize("NOT-APPROVED"), "not approved")
        self.assertEqual(roles.normalize(None), "")


class ProposeTest(unittest.TestCase):
    def test_a_known_name_in_the_category_it_belongs_to_is_proposed_with_confidence(self):
        cases = [("Done", "done", "delivered"), ("FINALIZADO", "done", "delivered"),
                 ("Completado", "done", "delivered"), ("Resuelto", "done", "delivered"),
                 ("RELEASED", "done", "delivered"), ("Cancelado", "done", "dropped"),
                 ("NOT APPROVED", "done", "dropped"), ("No aplica", "done", "dropped"),
                 ("Blocked", "in_progress", "blocked"), ("Backlog", "todo", "todo"),
                 ("PROCESANDO", "in_progress", "active"), ("Verificación solicitante", "in_progress", "active")]
        for name, category, role in cases:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"], p["mismatch"]), (role, "alta", False), name)

    def test_a_known_name_in_the_wrong_category_needs_a_person(self):
        cases = [("Done", "in_progress", "delivered"), ("Finalizado", "todo", "delivered"),
                 ("Resuelto", "in_progress", "delivered"), ("Blocked", "done", "blocked")]
        for name, category, guess in cases:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"], p["suggest"], p["mismatch"]),
                             (None, "decidir", guess, True), name)

    def test_a_name_with_extra_words_is_never_decided_by_the_dictionary(self):
        for name, category in [("Finalizado con error", "done"), ("Finalizado sin completar", "done"),
                               ("FINALIZADO POR TIEMPO EXCEDIDO", "done"), ("Listo para entrega", "in_progress")]:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"], p["mismatch"]), (None, "decidir", False), name)

    def test_waiting_and_unknown_done_names_need_a_person(self):
        for name, category in [("ON HOLD", "in_progress"), ("Esperando por el cliente", "in_progress"),
                               ("AWAITING APPROVAL", "in_progress"), ("Pend. de firma", "in_progress"),
                               ("Ready to deploy", "done"), ("PRODUCCION", "done"), ("Implementado", "done")]:
            p = roles.propose(status(name, category))
            self.assertEqual((p["role"], p["confidence"]), (None, "decidir"), name)

    def test_every_proposal_says_why(self):
        for name, category in [("Done", "done"), ("ON HOLD", "in_progress"), ("Backlog", "todo"), ("?", "weird")]:
            self.assertTrue(roles.propose(status(name, category))["why"], name)


class AnnotateTest(unittest.TestCase):
    def test_without_a_profile_the_category_decides(self):
        issues = roles.annotate([{"key": "PLATE-1", "category": "done"}, {"key": "PLATE-2", "category": "in_progress"},
                                 {"key": "PLATE-3", "category": "todo"}], {})
        self.assertEqual([(i["role"], i["role_source"]) for i in issues],
                         [("delivered", "category"), ("active", "category"), ("todo", "category")])

    def test_with_a_profile_the_status_id_decides_whatever_the_category_says(self):
        issue = {"key": "GDNC-1", "status": "Done", "status_id": "22", "category": "in_progress"}
        roles.annotate([issue], PROFILES)
        self.assertEqual((issue["role"], issue["role_source"]), ("delivered", "profile"))

    def test_an_undecided_or_unknown_status_has_no_role(self):
        undecided = {"key": "GDNC-2", "status_id": "25", "category": "in_progress"}
        unknown = {"key": "GDNC-3", "status_id": "99", "category": "done"}
        roles.annotate([undecided, unknown], PROFILES)
        self.assertEqual((undecided["role"], unknown["role"]), (None, None))

    def test_an_issue_without_a_status_id_is_unknown_to_the_profile_and_does_not_crash(self):
        issue = {"key": "GDNC-4", "status": "Nuevo", "category": "todo"}
        roles.annotate([issue], PROFILES)
        self.assertIsNone(issue["role"])
        self.assertEqual(roles.notes([issue], PROFILES),
                         ["Estado desconocido: Nuevo (GDNC). El workflow cambió; corré `jk board check GDNC`."])

    def test_role_of_falls_back_to_the_category_for_an_issue_nobody_annotated(self):
        self.assertEqual(roles.role_of({"category": "done"}), "delivered")
        self.assertIsNone(roles.role_of({"category": ""}))
        self.assertEqual(roles.source_of({}), "category")

    def test_the_project_is_what_comes_before_the_number(self):
        self.assertEqual(roles.project_of("PLATE-12"), "PLATE")
        self.assertEqual(roles.project_of("AE_X-3"), "AE_X")


class NotesTest(unittest.TestCase):
    def test_a_clean_report_has_no_notes(self):
        self.assertEqual(roles.notes([{"key": "GDNC-1", "status_id": "22", "status": "Done"}], PROFILES), [])

    def test_projects_without_a_profile_are_named_once(self):
        issues = [{"key": "PLATE-1"}, {"key": "PLATE-2"}, {"key": "UA-1"}]
        self.assertEqual(roles.notes(issues, {}),
                         ["Sin perfil: PLATE, UA. Se usa la categoría de Jira; corré `jk board setup KEY`."])

    def test_undecided_statuses_are_listed_by_project(self):
        notes = roles.notes([{"key": "GDNC-2", "status_id": "25", "status": "ON HOLD"}], PROFILES)
        self.assertEqual(notes, ["Perfil sin confirmar en GDNC: faltan decidir ON HOLD."])

    def test_a_status_the_profile_never_saw_is_reported_as_unknown(self):
        notes = roles.notes([{"key": "GDNC-3", "status_id": "99", "status": "Nuevo"}], PROFILES)
        self.assertEqual(notes, ["Estado desconocido: Nuevo (GDNC). El workflow cambió; corré `jk board check GDNC`."])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_roles.py' 2>&1 | tail -6`
Expected: FAIL con `ImportError: cannot import name 'roles' from 'jkan'`.

- [ ] **Step 3: Implementar**

```python
"""What a status means to a board: six roles, a proposal for each status, and the rules that turn issues into roles."""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

ROLES = ("todo", "active", "blocked", "waiting", "delivered", "dropped")
CLOSED = ("delivered", "dropped")
IN_FLIGHT = ("active", "blocked", "waiting")
LEGACY = {"todo": "todo", "in_progress": "active", "done": "delivered"}  # Jira category -> role, for a project without profile

DICTIONARY = {
    "delivered": ("done", "finalizado", "finalizada", "completado", "completada", "completo", "completa", "resuelto",
                  "resuelta", "cerrado", "cerrada", "closed", "resolved", "listo", "lista", "released"),
    "dropped": ("cancelado", "cancelada", "cancelled", "canceled", "rechazado", "rechazada", "descartado", "descartada",
                "discarded", "no aplica", "not approved"),
    "blocked": ("blocked", "bloqueado", "bloqueada"),
}
BY_NAME = {name: role for role, names in DICTIONARY.items() for name in names}
SINGLE_WORDS = {name for name in BY_NAME if " " not in name}
EXPECTED_CATEGORY = {"delivered": "done", "dropped": "done", "blocked": "in_progress"}
HINTS = re.compile(r"\b(hold|espera\w*|waiting|paus\w*|bloque\w*|pend\w*|pending|approval|aprobaci\w*)\b")


def normalize(text: str) -> str:
    """Lower case, no accents, no punctuation, single spaces: «Pend. Finalización» -> «pend finalizacion»."""
    folded = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def _proposal(role: Optional[str], confidence: str, why: str, suggest: Optional[str] = None,
              mismatch: bool = False) -> dict:
    return {"role": role, "confidence": confidence, "why": why, "suggest": suggest or role, "mismatch": mismatch}


def propose(status: dict) -> dict:
    """The role a status probably plays. `alta` means the name and Jira's category agree; `decidir` leaves the role
    empty for a person to set, and `suggest` carries the guess. `mismatch` marks a name Jira files in the wrong
    category. status: {"id", "name", "category"} with category todo, in_progress or done."""
    name, category = normalize(status["name"]), status["category"]
    exact = BY_NAME.get(name)
    if exact:
        if category == EXPECTED_CATEGORY[exact]:
            return _proposal(exact, "alta", "nombre conocido y categoría coherente")
        return _proposal(None, "decidir", f"el nombre sugiere {exact} pero Jira lo tiene en la categoría {category}",
                         exact, mismatch=True)
    known = sorted(set(name.split()) & SINGLE_WORDS)
    if known:
        return _proposal(None, "decidir", f"trae «{known[0]}» con más palabras: puede no significar lo mismo",
                         BY_NAME[known[0]])
    if category == "in_progress" and HINTS.search(name):
        return _proposal(None, "decidir", "parece una espera o un bloqueo")
    if category == "done":
        return _proposal(None, "decidir", "categoría done con un nombre que no conozco: ¿entregado o descartado?")
    if category == "todo":
        return _proposal("todo", "alta", "categoría por hacer")
    if category == "in_progress":
        return _proposal("active", "alta", "categoría en curso")
    return _proposal(None, "decidir", f"categoría desconocida {category!r}")


def project_of(key: str) -> str:
    return key.rpartition("-")[0]


def role_of(issue: dict) -> Optional[str]:
    """The role annotate() gave the issue; an issue nobody annotated falls back to Jira's category."""
    return issue["role"] if "role" in issue else LEGACY.get(issue.get("category", ""))


def source_of(issue: dict) -> str:
    return issue.get("role_source", "category")


def annotate(issues: List[dict], profiles: Dict[str, dict]) -> List[dict]:
    """Set issue['role'] (None while the status has no role) and issue['role_source'] ('profile' or 'category')."""
    for issue in issues:
        profile = profiles.get(project_of(issue["key"]))
        if profile is None:
            issue["role"], issue["role_source"] = LEGACY.get(issue.get("category", "")), "category"
            continue
        by_id = {s["id"]: s["role"] for s in profile["statuses"]}
        issue["role"], issue["role_source"] = by_id.get(issue.get("status_id", "")), "profile"
    return issues


def notes(issues: List[dict], profiles: Dict[str, dict]) -> List[str]:
    """What a reader must know before trusting a report: projects without profile, statuses still undecided, statuses
    the profile has never seen."""
    missing: set = set()
    undecided: Dict[str, set] = {}
    unknown: set = set()
    for issue in issues:
        project = project_of(issue["key"])
        profile = profiles.get(project)
        if profile is None:
            missing.add(project)
            continue
        entry = {s["id"]: s for s in profile["statuses"]}.get(issue.get("status_id", ""))
        if entry is None:
            unknown.add((project, issue.get("status", "")))
        elif entry["role"] is None:
            undecided.setdefault(project, set()).add(entry["name"])
    lines = []
    if missing:
        lines.append("Sin perfil: " + ", ".join(sorted(missing)) + ". Se usa la categoría de Jira; corré `jk board setup KEY`.")
    for project in sorted(undecided):
        lines.append(f"Perfil sin confirmar en {project}: faltan decidir {', '.join(sorted(undecided[project]))}.")
    for project, status in sorted(unknown):
        lines.append(f"Estado desconocido: {status} ({project}). El workflow cambió; corré `jk board check {project}`.")
    return lines
```

- [ ] **Step 4: Correrlos y ver que pasan**

Run: `python3 -m unittest discover -s tests -p 'test_roles.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_boundaries.py' 2>&1 | tail -3`
Expected: `OK` en los dos (`roles` ya está clasificado como lado de lectura en el test de fronteras).

- [ ] **Step 5: Commit**

```bash
git add jkan/roles.py tests/test_roles.py
git commit -m "feat(roles): propose a role for each status and annotate issues with it"
```

---

### Task 5: Perfiles de board

**Files:**
- Create: `jkan/board_profile.py`, `tests/shapes.py`
- Test: `tests/test_board_profile.py`

**Interfaces:**
- Consumes: `roles.propose`, `roles.normalize`, `roles.ROLES`; `Jira.project_statuses` (Task 3) como forma de entrada: `groups = [{"types", "statuses"}]`.
- Produces: `config_dir()`, `path_of(project, base=None)`, `fingerprint(statuses)`, `build(project, groups, kind, existing=None) -> profile`, `open_statuses(profile)`, `assign(profile, role, tokens)`, `save(profile, base=None)`, `load(project, base=None)`, `load_all(base=None)`, `class BadSelection(ValueError)`, `KINDS`, `VERSION`.
- Forma del perfil: `{"version", "project", "kind", "access", "wip_limit", "fingerprint", "workflows": [{"types", "status_ids"}], "statuses": [{"id", "name", "category", "role", "by", "suggest", "why"}]}`; `by` es `"proposal"`, `"human"` o `None`.

- [ ] **Step 1: Crear las formas de workflow y los tests**

```python
"""Workflow shapes for the board-profile tests, in the form Jira.project_statuses returns them.

The status names and Jira categories come from the 2026-10-09 survey of the real Jira: GDNC and OYP file a «Done» under
in progress, BDBDESK has four «done» statuses, FDQ has a «Finalizado con error», UA's Task has its own workflow, and
a few projects hold two statuses with the same name. The groupings are simplified and every id is made up."""
from __future__ import annotations


def status(ident, name, category) -> dict:
    return {"id": str(ident), "name": name, "category": category}


GDNC = [{"types": ["Hallazgo"], "statuses": [
    status(20, "Abierto", "todo"), status(21, "En análisis", "in_progress"), status(22, "Done", "in_progress"),
    status(23, "Descartado", "done"), status(24, "Bloqueado", "in_progress"), status(25, "ON HOLD", "in_progress")]}]

BDBDESK = [{"types": ["Solicitud"], "statuses": [
    status(30, "Pendiente", "todo"), status(31, "En curso", "in_progress"), status(32, "Finalizado", "done"),
    status(33, "Resuelto", "done"), status(34, "Cancelado", "done"), status(35, "Implementado", "done")]}]

FDQ = [{"types": ["Task"], "statuses": [
    status(40, "To Do", "todo"), status(41, "Done", "done"), status(42, "Finalizado", "done"),
    status(43, "Finalizado con error", "done"), status(44, "Listo para entrega", "in_progress")]}]

UA = [{"types": ["Historia", "Error", "Epic", "Subtask"], "statuses": [
    status(1, "To Do", "todo"), status(2, "In Progress", "in_progress"), status(3, "ON HOLD", "in_progress"),
    status(4, "Done", "done")]},
    {"types": ["Task"], "statuses": [
        status(1, "To Do", "todo"), status(2, "In Progress", "in_progress"), status(5, "AWAITING APPROVAL", "in_progress"),
        status(6, "Approved", "in_progress"), status(7, "RELEASED", "done"), status(8, "NOT APPROVED", "done")]}]

PEHD = [{"types": ["Epic", "Task", "Story", "Solicitud"], "statuses": [
    status(50, "To Do", "todo"), status(51, "In Progress", "in_progress"), status(52, "Done", "done")]}]

SAME_NAME = [{"types": ["Task"], "statuses": [
    status(60, "To Do", "todo"), status(61, "en ejecucion", "in_progress"), status(62, "En ejecución", "in_progress"),
    status(63, "Done", "done")]}]
```

```python
from __future__ import annotations

import json
import unittest

import shapes
from helpers import config_dir
from jkan import board_profile as bp
from jkan import roles


class BuildTest(unittest.TestCase):
    def test_every_status_gets_a_proposal_and_the_hard_ones_stay_open(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        self.assertEqual({s["name"]: s["role"] for s in profile["statuses"]},
                         {"Abierto": "todo", "En análisis": "active", "Done": None, "Descartado": "dropped",
                          "Bloqueado": "blocked", "ON HOLD": None})
        self.assertEqual([s["name"] for s in bp.open_statuses(profile)], ["Done", "ON HOLD"])
        self.assertEqual(profile["kind"], "flow")

    def test_a_status_shared_by_several_issue_types_appears_once(self):
        profile = bp.build("UA", shapes.UA, None)
        self.assertEqual(sorted(s["id"] for s in profile["statuses"]), ["1", "2", "3", "4", "5", "6", "7", "8"])
        self.assertEqual([w["types"] for w in profile["workflows"]], [["Historia", "Error", "Epic", "Subtask"], ["Task"]])

    def test_a_status_that_exists_for_one_issue_type_only_still_gets_its_role(self):
        profile = bp.build("UA", shapes.UA, None)
        issue = {"key": "UA-9", "status": "RELEASED", "status_id": "7", "category": "done"}  # only Task has it
        roles.annotate([issue], {"UA": profile})
        self.assertEqual(issue["role"], "delivered")

    def test_a_clean_board_needs_no_decision(self):
        profile = bp.build("PEHD", shapes.PEHD, "helpdesk")
        self.assertEqual((bp.open_statuses(profile), profile["kind"]), ([], "helpdesk"))

    def test_a_kind_that_does_not_exist_is_refused(self):
        with self.assertRaises(ValueError):
            bp.build("PEHD", shapes.PEHD, "kanban")

    def test_the_fingerprint_follows_the_set_of_status_ids(self):
        first = bp.build("UA", shapes.UA, None)["fingerprint"]
        reversed_groups = [dict(g, statuses=list(reversed(g["statuses"]))) for g in shapes.UA]
        self.assertEqual(bp.build("UA", reversed_groups, None)["fingerprint"], first)
        self.assertNotEqual(bp.build("PEHD", shapes.PEHD, None)["fingerprint"], first)


class RebuildTest(unittest.TestCase):
    def test_a_decision_survives_a_new_setup_and_a_rename(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        bp.assign(profile, "delivered", ["Done"])
        renamed = [dict(g, statuses=[dict(s, name="Hecho") if s["id"] == "22" else s for s in g["statuses"]])
                   for g in shapes.GDNC]
        again = bp.build("GDNC", renamed, None, profile)
        done = next(s for s in again["statuses"] if s["id"] == "22")
        self.assertEqual((done["name"], done["role"], done["by"]), ("Hecho", "delivered", "human"))

    def test_statuses_jira_no_longer_has_are_dropped_and_kind_and_wip_limit_are_kept(self):
        profile = bp.build("GDNC", shapes.GDNC, "scrum")
        profile["wip_limit"] = 6
        smaller = [dict(shapes.GDNC[0], statuses=shapes.GDNC[0]["statuses"][:2])]
        again = bp.build("GDNC", smaller, None, profile)
        self.assertEqual(([s["id"] for s in again["statuses"]], again["kind"], again["wip_limit"]),
                         (["20", "21"], "scrum", 6))


class AssignTest(unittest.TestCase):
    def setUp(self):
        self.profile = bp.build("BDBDESK", shapes.BDBDESK, None)

    def roles_by_id(self):
        return {s["id"]: (s["role"], s["by"]) for s in self.profile["statuses"]}

    def test_names_match_whatever_the_case_or_the_accents(self):
        bp.assign(self.profile, "delivered", ["FINALIZADO", "resuelto"])
        self.assertEqual(self.roles_by_id()["32"], ("delivered", "human"))
        self.assertEqual(self.roles_by_id()["33"], ("delivered", "human"))

    def test_two_statuses_with_the_same_name_need_an_id(self):
        profile = bp.build("SAME", shapes.SAME_NAME, None)
        with self.assertRaisesRegex(bp.BadSelection, r"id:61, id:62"):
            bp.assign(profile, "active", ["en ejecucion"])
        bp.assign(profile, "active", ["id:61", "id:62"])
        self.assertEqual([s["role"] for s in profile["statuses"] if s["id"] in ("61", "62")], ["active", "active"])

    def test_one_bad_token_changes_nothing(self):
        before = json.dumps(self.profile, sort_keys=True)
        with self.assertRaisesRegex(bp.BadSelection, "no status 'No existe' in BDBDESK"):
            bp.assign(self.profile, "delivered", ["Finalizado", "No existe"])
        self.assertEqual(json.dumps(self.profile, sort_keys=True), before)

    def test_naming_a_status_twice_in_one_call_is_harmless(self):
        bp.assign(self.profile, "delivered", ["Finalizado", "finalizado", "id:32"])
        self.assertEqual(self.roles_by_id()["32"], ("delivered", "human"))

    def test_a_role_that_does_not_exist_is_refused(self):
        with self.assertRaisesRegex(bp.BadSelection, "unknown role 'hecho'"):
            bp.assign(self.profile, "hecho", ["Finalizado"])


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_save_then_load_gives_back_the_same_profile_and_leaves_no_temporary_file(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        path = bp.save(profile)
        self.assertEqual(path, self.base / "profiles" / "GDNC.json")
        self.assertEqual(bp.load("GDNC"), profile)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["GDNC.json"])

    def test_a_missing_profile_is_none(self):
        self.assertIsNone(bp.load("NOPE"))

    def test_a_project_key_cannot_point_outside_the_folder(self):
        for bad in ("../x", "a/b", "lower", ""):
            with self.assertRaises(ValueError, msg=bad):
                bp.path_of(bad)

    def test_load_all_skips_a_file_it_cannot_read(self):
        bp.save(bp.build("GDNC", shapes.GDNC, None))
        (self.base / "profiles" / "BAD.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(list(bp.load_all()), ["GDNC"])

    def test_a_profile_from_a_newer_jk_is_refused_by_load_and_skipped_by_load_all(self):
        profile = bp.build("GDNC", shapes.GDNC, None)
        profile["version"] = bp.VERSION + 1
        bp.save(profile)
        with self.assertRaisesRegex(ValueError, "newer jk"):
            bp.load("GDNC")
        self.assertEqual(bp.load_all(), {})

    def test_a_json_file_that_is_not_an_object_is_not_a_profile(self):
        (self.base / "profiles").mkdir()
        (self.base / "profiles" / "UA.json").write_text("[1, 2]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not a profile"):
            bp.load("UA")

    def test_the_config_directory_follows_the_environment(self):
        self.assertEqual(bp.config_dir(), self.base)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_board_profile.py' 2>&1 | tail -6`
Expected: FAIL con `ImportError: cannot import name 'board_profile' from 'jkan'`.

- [ ] **Step 3: Implementar**

```python
"""Per-board profiles: which role each status plays. One JSON per Jira project under ~/.config/jk/profiles/
(or $JK_CONFIG_DIR/profiles/). Written only by `jk board setup` and `jk board set`; nobody edits them by hand."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from . import roles

VERSION = 1
KINDS = ("flow", "scrum", "helpdesk")
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


class BadSelection(ValueError):
    pass


def config_dir() -> Path:
    return Path(os.environ.get("JK_CONFIG_DIR") or Path.home() / ".config" / "jk")


def path_of(project: str, base: Optional[Path] = None) -> Path:
    if not KEY.match(project):
        raise ValueError(f"not a project key: {project!r}")
    return (base or config_dir()) / "profiles" / f"{project}.json"


def fingerprint(statuses: List[dict]) -> str:
    return "sha256:" + hashlib.sha256(",".join(sorted({s["id"] for s in statuses})).encode()).hexdigest()


def build(project: str, groups: List[dict], kind: Optional[str], existing: Optional[dict] = None) -> dict:
    """A profile for what Jira says now. A status a person decided keeps that role (matched by id, so a rename does
    not lose it); every other status is proposed again. Statuses Jira no longer has are dropped."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    decided = {s["id"]: s for s in (existing or {}).get("statuses", []) if s.get("by") == "human"}
    statuses: List[dict] = []
    seen: set = set()
    for group in groups:
        for status in group["statuses"]:
            if status["id"] in seen:
                continue
            seen.add(status["id"])
            if status["id"] in decided:
                statuses.append(dict(decided[status["id"]], name=status["name"], category=status["category"]))
                continue
            p = roles.propose(status)
            statuses.append({"id": status["id"], "name": status["name"], "category": status["category"],
                             "role": p["role"], "by": "proposal" if p["role"] else None,
                             "suggest": p["suggest"], "why": p["why"]})
    return {"version": VERSION, "project": project, "kind": kind or (existing or {}).get("kind") or "flow",
            "access": "full", "wip_limit": (existing or {}).get("wip_limit"), "fingerprint": fingerprint(statuses),
            "workflows": [{"types": g["types"], "status_ids": [s["id"] for s in g["statuses"]]} for g in groups],
            "statuses": statuses}


def open_statuses(profile: dict) -> List[dict]:
    return [s for s in profile["statuses"] if not s["role"]]


def _select(profile: dict, token: str) -> List[dict]:
    if token.startswith("id:"):
        return [s for s in profile["statuses"] if s["id"] == token[3:]]
    wanted = roles.normalize(token)
    return [s for s in profile["statuses"] if roles.normalize(s["name"]) == wanted]


def assign(profile: dict, role: str, tokens: List[str]) -> dict:
    """Give `role` to the statuses named by `tokens` (a name, or id:<id> when two statuses share a name). All or
    nothing: one bad token changes no status."""
    if role not in roles.ROLES:
        raise BadSelection(f"unknown role {role!r}; one of {', '.join(roles.ROLES)}")
    chosen: List[dict] = []
    for token in tokens:
        found = _select(profile, token)
        if not found:
            raise BadSelection(f"no status {token!r} in {profile['project']}")
        if len(found) > 1:
            ids = ", ".join(f"id:{s['id']}" for s in found)
            raise BadSelection(f"{token!r} matches {len(found)} statuses ({ids}); use id:<id>")
        chosen.append(found[0])
    for status in chosen:
        status["role"], status["by"] = role, "human"
    return profile


def save(profile: dict, base: Optional[Path] = None) -> Path:
    path = path_of(profile["project"], base)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a profile")
    if data.get("version", 0) > VERSION:
        raise ValueError(f"{path.name} was written by a newer jk (profile version {data['version']}); update jk")
    return data


def load(project: str, base: Optional[Path] = None) -> Optional[dict]:
    path = path_of(project, base)
    return _read(path) if path.is_file() else None


def load_all(base: Optional[Path] = None) -> Dict[str, dict]:
    """Every readable profile by project key; a file that cannot be read is skipped (its project reads as 'Sin perfil')."""
    folder = (base or config_dir()) / "profiles"
    found: Dict[str, dict] = {}
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                found[path.stem] = _read(path)
            except (OSError, ValueError):
                continue
    return found
```

- [ ] **Step 4: Correrlos y ver que pasan**

Run: `python3 -m unittest discover -s tests -p 'test_board_profile.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_boundaries.py' 2>&1 | tail -3`
Expected: `OK` en los dos.

- [ ] **Step 5: Commit**

```bash
git add jkan/board_profile.py tests/shapes.py tests/test_board_profile.py
git commit -m "feat(profile): per-board profiles; a person's decision survives a new setup and a rename"
```

---

### Task 6: `jk board setup | set | show | check | survey`

**Files:**
- Create: `jkan/board_cli.py`
- Modify: `jkan/cli.py` (tres ediciones: docstring, imports, despacho)
- Test: `tests/test_board_cli.py`

**Interfaces:**
- Consumes: `board_profile.*` (Task 5), `roles.propose/ROLES` (Task 4), `Jira.project_statuses/projects` (Task 3), `render.table`.
- Produces: `board_cli.run(argv, jira) -> int` con `argv` empezando en el verbo y `jira` una función que arma el cliente (solo se llama en los verbos que leen Jira); `board_cli.VERBS`; códigos de salida `0 OK`, `1 FINDINGS`, `2 CANNOT`, `3 NEEDS_DECISION`.
- Produces: `jk board <verbo>` despacha a `board_cli` **solo** si el segundo argumento es uno de los verbos; `jk board EPIC` sigue siendo el tablero local.

- [ ] **Step 1: Escribir los tests**

```python
from __future__ import annotations

import contextlib
import io
import json
import unittest

import shapes
from helpers import FakeJira, config_dir
from jkan import board_profile, cli


def run(args, jira):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["board"] + args, client=lambda project: jira)
    return code, out.getvalue(), err.getvalue()


def fake(**groups):
    jira = FakeJira()
    jira.status_groups = dict(groups)
    return jira


def status_named(project, name):
    return next(s for s in board_profile.load(project)["statuses"] if s["name"] == name)


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_setup_prints_what_it_understands_saves_it_and_exits_3_while_decisions_are_open(self):
        code, out, _ = run(["setup", "GDNC"], fake(GDNC=shapes.GDNC))
        self.assertEqual(code, 3)
        self.assertIn("## Perfil GDNC", out)
        self.assertIn("| Done | 22 | en curso | ¿delivered? | decidir |", out)
        self.assertIn("| ON HOLD | 25 | en curso | ¿? | decidir |", out)  # no guess to offer
        self.assertIn("**Faltan 2 decisiones.**", out)
        self.assertEqual(len(board_profile.open_statuses(board_profile.load("GDNC"))), 2)

    def test_a_board_with_nothing_to_decide_exits_0(self):
        code, out, _ = run(["setup", "PEHD", "--kind", "helpdesk"], fake(PEHD=shapes.PEHD))
        self.assertEqual(code, 0)
        self.assertIn("**Perfil completo.**", out)
        self.assertEqual(board_profile.load("PEHD")["kind"], "helpdesk")

    def test_setup_again_keeps_what_a_person_decided(self):
        jira = fake(GDNC=shapes.GDNC)
        run(["setup", "GDNC"], jira)
        run(["set", "GDNC", "delivered", "Done"], jira)
        code, _, _ = run(["setup", "GDNC"], jira)
        done = status_named("GDNC", "Done")
        self.assertEqual((done["role"], done["by"], code), ("delivered", "human", 3))  # ON HOLD is still open

    def test_statuses_that_disappeared_from_jira_are_reported(self):
        jira = fake(GDNC=shapes.GDNC)
        run(["setup", "GDNC"], jira)
        jira.status_groups["GDNC"] = [dict(shapes.GDNC[0], statuses=shapes.GDNC[0]["statuses"][:2])]
        _, out, _ = run(["setup", "GDNC"], jira)
        self.assertIn("Ya no existen en Jira: Done, Descartado, Bloqueado, ON HOLD.", out)

    def test_a_project_jira_does_not_know_exits_2_and_saves_nothing(self):
        code, _, err = run(["setup", "NOPE"], fake())
        self.assertEqual(code, 2)
        self.assertIn("jk:", err)
        self.assertIsNone(board_profile.load("NOPE"))

    def test_a_jira_answer_with_no_statuses_is_not_saved_as_a_complete_profile(self):
        code, _, err = run(["setup", "EMPTY"], fake(EMPTY=[]))
        self.assertEqual(code, 1)
        self.assertIn("no statuses for EMPTY", err)
        self.assertIsNone(board_profile.load("EMPTY"))

    def test_a_key_that_is_not_a_project_key_is_refused(self):
        code, _, err = run(["setup", "ua"], fake())
        self.assertEqual(code, 1)
        self.assertIn("not a project key", err)


class SetTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        self.jira = fake(GDNC=shapes.GDNC)
        run(["setup", "GDNC"], self.jira)

    def test_set_exits_3_until_the_last_decision_and_then_0(self):
        code, _, _ = run(["set", "GDNC", "delivered", "Done"], self.jira)
        self.assertEqual(code, 3)
        code, out, _ = run(["set", "GDNC", "waiting", "ON HOLD"], self.jira)
        self.assertEqual(code, 0)
        self.assertIn("**Perfil completo.**", out)

    def test_one_bad_name_changes_nothing_and_exits_1(self):
        code, _, err = run(["set", "GDNC", "delivered", "Done", "Nope"], self.jira)
        self.assertEqual(code, 1)
        self.assertIn("no status 'Nope' in GDNC", err)
        self.assertIsNone(status_named("GDNC", "Done")["role"])

    def test_set_without_a_profile_says_how_to_make_one(self):
        code, _, err = run(["set", "UA", "active", "Done"], fake())
        self.assertEqual(code, 1)
        self.assertIn("run jk board setup UA", err)

    def test_a_role_that_does_not_exist_is_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(["set", "GDNC", "hecho", "Done"], self.jira)


class ShowAndCheckTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()

    def test_show_prints_the_saved_profile_with_the_same_exit_codes(self):
        jira = fake(PEHD=shapes.PEHD, GDNC=shapes.GDNC)
        run(["setup", "PEHD"], jira)
        run(["setup", "GDNC"], jira)
        self.assertEqual(run(["show", "PEHD"], jira)[0], 0)
        self.assertEqual(run(["show", "GDNC"], jira)[0], 3)

    def test_show_of_a_profile_from_a_newer_jk_exits_1(self):
        profile = board_profile.build("PEHD", shapes.PEHD, None)
        profile["version"] = board_profile.VERSION + 1
        board_profile.save(profile)
        code, _, err = run(["show", "PEHD"], fake())
        self.assertEqual(code, 1)
        self.assertIn("newer jk", err)

    def test_show_of_a_missing_profile_exits_1(self):
        self.assertEqual(run(["show", "UA"], fake())[0], 1)

    def test_show_of_a_corrupt_file_exits_1_instead_of_a_traceback(self):
        (self.base / "profiles").mkdir()
        (self.base / "profiles" / "UA.json").write_text("{not json", encoding="utf-8")
        code, _, err = run(["show", "UA"], fake())
        self.assertEqual(code, 1)
        self.assertIn("jk:", err)

    def test_check_says_nothing_changed_or_what_did(self):
        jira = fake(UA=shapes.UA)
        run(["setup", "UA"], jira)
        code, out, _ = run(["check", "UA"], jira)
        self.assertEqual(code, 0)
        self.assertIn("sin cambios", out)
        grown = [dict(shapes.UA[0], statuses=shapes.UA[0]["statuses"] + [shapes.status(9, "QA", "in_progress")]),
                 shapes.UA[1]]
        jira.status_groups["UA"] = grown
        code, out, _ = run(["check", "UA"], jira)
        self.assertEqual(code, 1)
        self.assertIn("Nuevos: QA", out)
        self.assertIn("jk board setup UA", out)


class SurveyTest(unittest.TestCase):
    def setUp(self):
        self.base = config_dir()
        self.jira = fake(GDNC=shapes.GDNC, PEHD=shapes.PEHD, FDQ=shapes.FDQ)
        self.jira.project_list = [{"key": k, "name": "", "type": t, "style": ""} for k, t in
                                  (("GDNC", "software"), ("PEHD", "software"), ("FDQ", "service_desk"),
                                   ("SECRET", "software"))]

    def test_survey_counts_what_needs_a_decision_and_the_projects_it_could_not_read(self):
        code, out, _ = run(["survey", "--json"], self.jira)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"], {
            "projects_read": 3, "projects_denied": 1, "statuses": 14, "alta": 10, "decidir": 4,
            "projects_needing_decisions": 2, "mismatch_statuses": 1, "mismatch_projects": 1})

    def test_survey_text_ends_with_the_totals(self):
        _, out, _ = run(["survey"], self.jira)
        self.assertIn("3 proyectos leídos · 1 sin acceso · 14 estados · alta 10 (71%) · decidir 4 (29%)", out)

    def test_survey_can_be_limited_to_one_project_type(self):
        _, out, _ = run(["survey", "--json", "--type", "service_desk"], self.jira)
        self.assertEqual([p["project"] for p in json.loads(out)["projects"]], ["FDQ"])

    def test_survey_saves_nothing(self):
        run(["survey"], self.jira)
        self.assertFalse((self.base / "profiles").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_board_cli.py' 2>&1 | tail -6`
Expected: FAIL: `jk board setup` todavía se interpreta como el tablero local (`error: unrecognized arguments` o `KeyError`).

- [ ] **Step 3: Crear el módulo**

```python
"""jk board setup | set | show | check | survey: what each status of a Jira board means to its team.

Reads Jira; the only thing it writes is the local profile (see board_profile.py). Exit codes: 0 done, 1 findings or
a refused input, 2 could not do it (Jira, disk), 3 the profile still has statuses without a role."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, List, Optional

from . import board_profile, render, roles
from .jira import JiraError

OK, FINDINGS, CANNOT, NEEDS_DECISION = 0, 1, 2, 3
VERBS = ("setup", "set", "show", "check", "survey")
CATEGORY = {"todo": "por hacer", "in_progress": "en curso", "done": "hecho"}


def _render(profile: dict) -> str:
    rows = []
    for s in profile["statuses"]:
        confidence = "confirmado" if s.get("by") == "human" else ("alta" if s["role"] else "decidir")
        rows.append([s["name"], s["id"], CATEGORY.get(s["category"], s["category"]),
                     s["role"] or (f"¿{s['suggest']}?" if s.get("suggest") else "¿?"), confidence, s.get("why") or ""])
    pending = board_profile.open_statuses(profile)
    head = (f"## Perfil {profile['project']}\n**Tipo:** {profile['kind']} · **Estados:** {len(profile['statuses'])} · "
            f"**Sin decidir:** {len(pending)} · **Grupos de tipos:** {len(profile['workflows'])}")
    groups = "\n".join(f"- {', '.join(w['types'])}: {len(w['status_ids'])} estados" for w in profile["workflows"])
    table = render.table(["Estado", "Id", "Categoría de Jira", "Rol", "Confianza", "Por qué"], rows)
    tail = (f"**Faltan {len(pending)} decisiones.** Para cada una: `jk board set {profile['project']} <rol> \"<estado>\"` "
            f"(roles: {', '.join(roles.ROLES)}; si dos estados se llaman igual, `id:<id>`).") if pending \
        else "**Perfil completo.**"
    return "\n\n".join([head, groups, table, tail])


def _needs_profile(key: str) -> Optional[dict]:
    profile = board_profile.load(key)
    if profile is None:
        sys.stderr.write(f"no profile for {key}: run jk board setup {key}\n")
    return profile


def _verdict(profile: dict) -> int:
    return NEEDS_DECISION if board_profile.open_statuses(profile) else OK


def _setup(jira, args) -> int:
    existing = board_profile.load(args.key)
    groups = jira.project_statuses(args.key)
    if not groups:
        raise ValueError(f"Jira returned no statuses for {args.key}: wrong key, or the account cannot see it")
    profile = board_profile.build(args.key, groups, args.kind, existing)
    current = {s["id"] for s in profile["statuses"]}
    gone = [s["name"] for s in (existing or {}).get("statuses", []) if s["id"] not in current]
    path = board_profile.save(profile)
    print(_render(profile))
    if gone:
        print(f"\nYa no existen en Jira: {', '.join(gone)}.")
    print(f"\nPerfil guardado en {path}")
    return _verdict(profile)


def _set(args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    try:
        board_profile.assign(profile, args.role, args.status)
    except board_profile.BadSelection as exc:
        sys.stderr.write(f"{exc}\n")
        return FINDINGS
    board_profile.save(profile)
    print(_render(profile))
    return _verdict(profile)


def _show(args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    print(_render(profile))
    return _verdict(profile)


def _check(jira, args) -> int:
    profile = _needs_profile(args.key)
    if profile is None:
        return FINDINGS
    fresh = {s["id"]: s for g in jira.project_statuses(args.key) for s in g["statuses"]}
    if board_profile.fingerprint(list(fresh.values())) == profile["fingerprint"]:
        print(f"{args.key}: sin cambios en los estados.")
        return OK
    known = {s["id"]: s for s in profile["statuses"]}
    added = sorted(s["name"] for i, s in fresh.items() if i not in known)
    removed = sorted(s["name"] for i, s in known.items() if i not in fresh)
    print(f"{args.key}: el workflow cambió. Nuevos: {', '.join(added) or '–'}. Ya no están: {', '.join(removed) or '–'}.")
    print(f"Corré `jk board setup {args.key}` para actualizar; las decisiones que tomaste se conservan.")
    return FINDINGS


def _survey(jira, args) -> int:
    projects = [p for p in jira.projects() if not args.type or p["type"] == args.type]
    if args.limit:
        projects = projects[:args.limit]
    rows, denied = [], 0
    for project in projects:
        try:
            groups = jira.project_statuses(project["key"])
        except JiraError:
            denied += 1
            continue
        unique = {s["id"]: s for g in groups for s in g["statuses"]}
        proposals = [roles.propose(s) for s in unique.values()]
        rows.append({"project": project["key"], "type": project["type"], "statuses": len(unique),
                     "alta": sum(1 for p in proposals if p["confidence"] == "alta"),
                     "decidir": sum(1 for p in proposals if p["confidence"] == "decidir"),
                     "mismatch": sum(1 for p in proposals if p["mismatch"])})
    statuses = sum(r["statuses"] for r in rows)
    summary = {"projects_read": len(rows), "projects_denied": denied, "statuses": statuses,
               "alta": sum(r["alta"] for r in rows), "decidir": sum(r["decidir"] for r in rows),
               "projects_needing_decisions": sum(1 for r in rows if r["decidir"]),
               "mismatch_statuses": sum(r["mismatch"] for r in rows),
               "mismatch_projects": sum(1 for r in rows if r["mismatch"])}
    if args.json:
        print(json.dumps({"summary": summary, "projects": rows}, ensure_ascii=False, indent=2))
        return OK
    print(render.table(["Proyecto", "Tipo", "Estados", "Alta", "Decidir", "Categoría mal puesta"],
                       [[r["project"], r["type"], r["statuses"], r["alta"], r["decidir"], r["mismatch"]] for r in rows],
                       "_Ningún proyecto._"))
    pct = (lambda n: f"{round(100 * n / statuses)}%") if statuses else (lambda n: "–")
    print(f"\n{summary['projects_read']} proyectos leídos · {denied} sin acceso · {statuses} estados · "
          f"alta {summary['alta']} ({pct(summary['alta'])}) · decidir {summary['decidir']} ({pct(summary['decidir'])}) · "
          f"{summary['projects_needing_decisions']} proyectos con decisiones pendientes · "
          f"{summary['mismatch_statuses']} estados con la categoría mal puesta en {summary['mismatch_projects']} proyectos")
    return OK


def run(argv: List[str], jira: Callable[[], object]) -> int:
    """argv starts at the verb. `jira` builds the client only for the verbs that read Jira."""
    parser = argparse.ArgumentParser(prog="jk board", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)
    setup = sub.add_parser("setup", help="read a project's statuses from Jira, propose a role for each, save the profile")
    setup.add_argument("key", help="Jira project key, e.g. UA")
    setup.add_argument("--kind", choices=board_profile.KINDS, help="how the board works (default: flow, or what the profile says)")
    give = sub.add_parser("set", help="give a role to statuses, by name or id:<id>")
    give.add_argument("key")
    give.add_argument("role", choices=roles.ROLES)
    give.add_argument("status", nargs="+")
    for name, text in (("show", "print the saved profile"), ("check", "compare the profile with Jira's statuses now")):
        sub.add_parser(name, help=text).add_argument("key")
    survey = sub.add_parser("survey", help="propose roles for many projects and count what needs a decision; saves nothing")
    survey.add_argument("--type", help="only projects of this type, e.g. software or service_desk")
    survey.add_argument("--limit", type=int, help="only the first N projects")
    survey.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    try:
        if args.verb == "setup":
            return _setup(jira(), args)
        if args.verb == "set":
            return _set(args)
        if args.verb == "show":
            return _show(args)
        if args.verb == "check":
            return _check(jira(), args)
        return _survey(jira(), args)
    except ValueError as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return FINDINGS
    except (JiraError, OSError) as exc:
        sys.stderr.write(f"jk: {exc}\n")
        return CANNOT
```

- [ ] **Step 4: Despachar desde `cli.py`**

Los imports incluyen `board_profile` y `roles`, que usa la Task 7.

Reemplazá en `jkan/cli.py` este texto:

```python
"""jk: create | pull | push | show | board | who | assign | done | next | blocked | load | stats. Every Jira write is a dry run unless --apply is passed; the reports only read."""
```

por este:

```python
"""jk: create | pull | push | show | board | who | assign | done | next | blocked | load | stats | board setup|set|show|check|survey. Every Jira write is a dry run unless --apply is passed; the reports only read."""
```

Reemplazá en `jkan/cli.py` este texto:

```python
from . import config, journal, kanban, people, preview, render, standup, stats, sync, window
```

por este:

```python
from . import board_cli, board_profile, config, journal, kanban, people, preview, render, roles, standup, stats, sync, window
```

Reemplazá en `jkan/cli.py` este texto:

```python
    parser = argparse.ArgumentParser(prog="jk", description=__doc__)
```

por este:

```python
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) > 1 and argv[0] == "board" and argv[1] in board_cli.VERBS:  # `jk board EPIC` stays the local kanban
        here = Path(".").resolve()
        return board_cli.run(argv[1:], lambda: client(here) if client is not _client else _client(here, command="board"))
    parser = argparse.ArgumentParser(prog="jk", description=__doc__)
```

- [ ] **Step 5: Correrlos y ver que pasan, y que el tablero local sigue andando**

Run: `python3 -m unittest discover -s tests -p 'test_board_cli.py' 2>&1 | tail -3; python3 -m unittest discover -s tests -p 'test_board.py' 2>&1 | tail -3`
Expected: `OK` en los dos. `tests/test_board.py` es la prueba de regresión de `jk board EPIC`.

- [ ] **Step 6: Suite completa y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
git add jkan/board_cli.py jkan/cli.py tests/test_board_cli.py
git commit -m "feat(board): jk board setup, set, show, check and survey"
```

---

### Task 7: Los reportes leen roles y avisan qué perfil falta

**Files:**
- Modify: `jkan/standup.py` (siete ediciones), `jkan/stats.py` (cuatro), `jkan/render.py` (una), `jkan/cli.py` (dos más y un `sd`)
- Modify: `tests/test_done_tree.py`, `tests/test_stats.py` (dos expectativas que cambian a propósito)
- Test: `tests/test_report_roles.py`

**Interfaces:**
- Consumes: `roles.annotate/role_of/source_of/notes/CLOSED/IN_FLIGHT` (Task 4), `board_profile.load_all` (Task 5), `issue["status_id"]` (Task 3).
- Produces: `standup.search` anota `role` y `role_source` en cada issue y, si `conv` trae `"_seen"`, acumula lo leído; `gather_done` devuelve además `"dropped"`; los reportes imprimen arriba una línea `> ⚠ …` por cada aviso, y con `--json` agregan la clave `profile_notes`.
- Comportamiento sin perfil: idéntico al de hoy (rol por categoría), más el aviso `Sin perfil: KEY`.

- [ ] **Step 1: Escribir los tests de integración**

```python
from __future__ import annotations

import json
import unittest

import shapes
from helpers import FakeJira, config_dir, issue
from jkan import board_profile
from test_report_cli import run


def save_profile(project, groups, decisions):
    profile = board_profile.build(project, groups, None)
    for role, names in decisions.items():
        board_profile.assign(profile, role, names)
    board_profile.save(profile)


def closed(key):  # the «Done» GDNC files under in progress
    return issue(key, status="Done", status_id="22", category="in_progress", changed="2026-10-07")


def dropped(key):
    return issue(key, status="Descartado", status_id="23", category="done", changed="2026-10-07")


def active(key):
    return issue(key, status="En análisis", status_id="21", category="in_progress", changed="2026-09-01")


def holding(key):
    return issue(key, status="ON HOLD", status_id="25", category="in_progress", changed="2026-09-01")


def blocked(key):
    return issue(key, status="Bloqueado", status_id="24", category="in_progress", changed="2026-09-01")


class RoleReportsTest(unittest.TestCase):
    def setUp(self):
        config_dir()
        save_profile("GDNC", shapes.GDNC, {"delivered": ["Done"], "waiting": ["ON HOLD"]})

    def answer(self, *issues):
        jira = FakeJira()
        jira.search_answer = lambda jql: list(issues)
        return jira

    def test_done_counts_a_done_filed_under_in_progress_as_closed_and_keeps_dropped_apart(self):
        jira = self.answer(closed("GDNC-1"), dropped("GDNC-2"), active("GDNC-3"))
        code, out, _ = run(["done", "--since", "2026-10-01", "--until", "2026-10-07"], jira)
        self.assertEqual(code, 0)
        self.assertIn("**1 cerradas · 1 en curso** · 1 descartadas", out)
        self.assertNotIn("⚠", out)

    def test_next_offers_neither_a_done_nor_work_that_is_waiting_on_someone(self):
        jira = self.answer(closed("GDNC-1"), active("GDNC-3"), holding("GDNC-4"))
        _, out, _ = run(["next"], jira)
        self.assertIn("GDNC-3", out)
        self.assertNotIn("GDNC-1", out)
        self.assertNotIn("GDNC-4", out)

    def test_blocked_comes_from_the_role_not_from_the_conventions_list(self):
        jira = self.answer(blocked("GDNC-5"), closed("GDNC-1"), holding("GDNC-4"))
        _, out, _ = run(["blocked"], jira)
        self.assertIn("Estado Bloqueado, sin link", out)  # conventions.json only lists «Blocked»
        self.assertNotIn("GDNC-1", out)
        self.assertNotIn("GDNC-4", out)

    def test_stats_counts_the_done_as_delivered_and_not_as_work_in_progress(self):
        jira = FakeJira()
        jira.search_answer = lambda jql: [] if "statusCategory = Done" in jql else [closed("GDNC-1"), active("GDNC-3")]
        _, out, _ = run(["stats"], jira)
        self.assertIn("| 2026-10-05 | 1 (en curso) |", out)
        self.assertIn("GDNC-3", out)
        self.assertNotIn("GDNC-1", out)

    def test_a_project_without_a_profile_says_so_and_still_reports_by_category(self):
        jira = self.answer(issue("PLATE-9", status="Done", category="done", changed="2026-10-07"))
        _, out, _ = run(["done", "--since", "2026-10-01"], jira)
        self.assertIn("> ⚠ Sin perfil: PLATE.", out)
        self.assertIn("**1 cerradas · 0 en curso**", out)

    def test_an_undecided_status_is_reported_and_never_counted_as_closed(self):
        save_profile("OYP", shapes.GDNC, {})
        jira = self.answer(issue("OYP-1", status="Done", status_id="22", category="in_progress", changed="2026-10-07"))
        _, out, _ = run(["done", "--since", "2026-10-01"], jira)
        self.assertIn("**0 cerradas · 0 en curso**", out)
        self.assertIn("> ⚠ Perfil sin confirmar en OYP: faltan decidir Done.", out)

    def test_a_status_the_profile_never_saw_is_reported_and_does_not_crash(self):
        jira = self.answer(issue("GDNC-7", status="Nuevo", status_id="99", category="todo"))
        code, out, _ = run(["next"], jira)
        self.assertEqual(code, 0)
        self.assertIn("> ⚠ Estado desconocido: Nuevo (GDNC).", out)

    def test_json_carries_the_notes_instead_of_a_banner(self):
        _, clean, _ = run(["done", "--since", "2026-10-01", "--json"], self.answer(closed("GDNC-1")))
        self.assertEqual(json.loads(clean)["profile_notes"], [])
        _, noisy, _ = run(["done", "--since", "2026-10-01", "--json"], self.answer(issue("PLATE-9", category="done")))
        self.assertEqual(len(json.loads(noisy)["profile_notes"]), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correrlos y ver que fallan**

Run: `python3 -m unittest discover -s tests -p 'test_report_roles.py' 2>&1 | tail -8`
Expected: FAIL: los reportes todavía cuentan por categoría y no imprimen avisos.

- [ ] **Step 3: Anotar roles en la búsqueda y usarlos en los reportes de standup**

Reemplazá en `jkan/standup.py` este texto:

```python
from . import queries
```

por este:

```python
from . import queries, roles
```

Reemplazá en `jkan/standup.py` este texto:

```python
def search(jira, jql: str, conv: dict) -> List[dict]:
    return jira.search(jql, blocked_link=conv.get("blocked_link") or "is blocked by")
```

por este:

```python
def search(jira, jql: str, conv: dict) -> List[dict]:
    """Jira's answer with each issue's role set from the board profiles in conv["profiles"]."""
    found = jira.search(jql, blocked_link=conv.get("blocked_link") or "is blocked by")
    roles.annotate(found, conv.get("profiles") or {})
    if "_seen" in conv:  # the CLI collects what the report read, to tell the reader which profiles it lacked
        conv["_seen"].extend(found)
    return found
```

Reemplazá en `jkan/standup.py` este texto:

```python
    if issue["category"] == "done":
        return []
```

por este:

```python
    role = roles.role_of(issue)
    if role in roles.CLOSED:
        return []
```

Reemplazá en `jkan/standup.py` este texto:

```python
    if issue["status"].lower() in {name.lower() for name in blocked_statuses}:
```

por este:

```python
    if roles.source_of(issue) == "profile":
        by_status = role == "blocked"
    else:
        by_status = issue["status"].lower() in {name.lower() for name in blocked_statuses}
    if by_status:
```

Reemplazá en `jkan/standup.py` este texto:

```python
    ready = sorted((i for i in open_issues if not blockers(i, statuses)), key=by_priority)
```

por este:

```python
    ready = sorted((i for i in open_issues if not blockers(i, statuses) and roles.role_of(i) != "waiting"),
                   key=by_priority)
```

Reemplazá en `jkan/standup.py` este texto:

```python
    found = search(jira, queries.open_of(person, conv.get("project")), conv)
```

por este:

```python
    found = [i for i in search(jira, queries.open_of(person, conv.get("project")), conv)
             if roles.role_of(i) not in roles.CLOSED]  # a «Done» filed under in progress is not open work
```

Reemplazá en `jkan/standup.py` este texto:

```python
    return {"done": sum(1 for i in work if i["category"] == "done"),
            "in_progress": sum(1 for i in work if i["category"] == "in_progress"),
```

por este:

```python
    return {"done": sum(1 for i in work if roles.role_of(i) == "delivered"),
            "dropped": sum(1 for i in work if roles.role_of(i) == "dropped"),
            "in_progress": sum(1 for i in work if roles.role_of(i) in roles.IN_FLIGHT),
```

- [ ] **Step 4: Usar roles en las métricas**

Reemplazá en `jkan/stats.py` este texto:

```python
from . import queries, standup
```

por este:

```python
from . import queries, roles, standup
```

Reemplazá en `jkan/stats.py` este texto:

```python
for i in open_issues if i["category"] == "in_progress" and i["changed"]]
```

por este:

```python
for i in open_issues if roles.role_of(i) in roles.IN_FLIGHT and i["changed"]]
```

Reemplazá en `jkan/stats.py` este texto:

```python
"in_progress": sum(1 for i in open_issues if i["category"] == "in_progress"),
```

por este:

```python
"in_progress": sum(1 for i in open_issues if roles.role_of(i) in roles.IN_FLIGHT),
```

Reemplazá en `jkan/stats.py` este texto:

```python
    done = standup.search(jira, queries.done_since(person, first, project), conv)
    open_issues = standup.search(jira, queries.open_of(person, project), conv)
    return ([i for i in done if i["issuetype"] != epic_type], [i for i in open_issues if i["issuetype"] != epic_type])
```

por este:

```python
    closed = standup.search(jira, queries.done_since(person, first, project), conv)
    found = standup.search(jira, queries.open_of(person, project), conv)
    delivered = [i for i in closed if roles.role_of(i) == "delivered"]  # «dropped» is not delivery
    have = {i["key"] for i in delivered}
    # A «Done» filed outside Jira's done category comes back from the open search; it is delivered work too.
    delivered += [i for i in found if roles.role_of(i) == "delivered" and i["key"] not in have
                  and i["changed"] and i["changed"] >= first.isoformat()]
    open_now = [i for i in found if roles.role_of(i) not in roles.CLOSED]
    return ([i for i in delivered if i["issuetype"] != epic_type], [i for i in open_now if i["issuetype"] != epic_type])
```

- [ ] **Step 5: Mostrar los descartados en «Hecho»**

Reemplazá en `jkan/render.py` este texto:

```python
    totals = f"**{result['done']} cerradas · {result['in_progress']} en curso**"
```

por este:

```python
    totals = f"**{result['done']} cerradas · {result['in_progress']} en curso**"
    if result.get("dropped"):
        totals += f" · {result['dropped']} descartadas"
```

- [ ] **Step 6: Cargar los perfiles y anteponer los avisos en `cli.py`**

Reemplazá en `jkan/cli.py` este texto:

```python
def _emit(args, payload, text: str) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str) if args.json else text)
```

por este:

```python
def _emit(args, conv: dict, payload, text: str) -> None:
    """Print a report, led by what the reader must know about the profiles it was computed with."""
    notes = roles.notes(conv.get("_seen", []), conv.get("profiles") or {})
    if args.json:
        print(json.dumps({**payload, "profile_notes": notes}, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n".join(f"> ⚠ {n}" for n in notes) + "\n\n" + text if notes else text)
```

Reemplazá en `jkan/cli.py` este texto:

```python
    """done | next | blocked | load | stats: read only, for the user or, with --person, for a teammate."""
    try:
```

por este:

```python
    """done | next | blocked | load | stats: read only, for the user or, with --person, for a teammate."""
    conv["profiles"] = board_profile.load_all()
    conv["_seen"] = []
    try:
```

Cada llamada a `_emit` pasa ahora `conv`. Los cinco llamados están dentro de `_report`; el `def` no empieza con espacios, por eso la expresión no lo toca:

```bash
sd -f m '^(\s+)_emit\(args, ' '${1}_emit(args, conv, ' jkan/cli.py
rg -n "_emit\(" jkan/cli.py
```

Expected: una línea `def _emit(args, conv: dict, payload, text: str)` y cinco llamadas, todas con `conv`.

- [ ] **Step 7: Correr los tests nuevos**

Run: `python3 -m unittest discover -s tests -p 'test_report_roles.py' 2>&1 | tail -4`
Expected: `OK`.

- [ ] **Step 8: Ver qué tests viejos cambian a propósito**

Run: `python3 -m unittest discover -s tests 2>&1 | rg "^(FAIL|ERROR)"`
Expected: exactamente dos fallas, las dos esperadas:
- `test_done_tree...test_empty_window`: el resultado de `gather_done` ahora trae `"dropped": 0`.
- `test_stats...test_gather_history_drops_epics_and_starts_at_the_first_week`: el fixture devolvía como «cerrado» un issue con categoría `todo` (el helper `issue()` pone `todo` por defecto); ahora se cuenta como entregado solo lo que tiene rol `delivered`.

Si falla algo más, **no lo ajustes para que pase**: es un cambio de comportamiento no previsto; pará y mirá por qué.

- [ ] **Step 9: Corregir esas dos expectativas**

Reemplazá en `tests/test_done_tree.py` este texto:

```python
self.assertEqual(result, {"done": 0, "in_progress": 0, "tree": []})
```

por este:

```python
self.assertEqual(result, {"done": 0, "dropped": 0, "in_progress": 0, "tree": []})
```

Reemplazá en `tests/test_stats.py` este texto:

```python
issue("D", changed="2026-10-06"), issue("E", issuetype="Epic")]
```

por este:

```python
issue("D", category="done", changed="2026-10-06"), issue("E", issuetype="Epic")]
```

- [ ] **Step 10: Suite completa en las dos versiones de Python y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
/usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
git add jkan/standup.py jkan/stats.py jkan/render.py jkan/cli.py tests/test_report_roles.py tests/test_done_tree.py tests/test_stats.py
git commit -m "feat(reports): read roles instead of Jira's category and say which profile is missing"
```

Expected: `Ran 320 tests ... OK` dos veces.

---

### Task 8: Docs y correcciones a la spec

**Files:**
- Modify: `SKILL.md`, `standup/SKILL.md`, `README.md`, `docs/superpowers/specs/2026-10-09-jira-em-design.md`

**Interfaces:**
- Consumes: todo lo anterior. Produces: docs que describen `jk` en el PATH, los perfiles y el código de salida 3.

- [ ] **Step 1: Las skills llaman a `jk`, no a la carpeta de otra skill**

Reemplazá en `SKILL.md` este texto:

```markdown
python3 ~/.agents/skills/jira-kanban/jk.py <create|pull|push|show|board> ... --project .
```

por este:

```markdown
jk <create|pull|push|show|board> ... --project .
```

Reemplazá en `standup/SKILL.md` este texto:

```markdown
python3 ~/.agents/skills/jira-kanban/jk.py <done|next|blocked|load|stats> ... --project .
```

por este:

```markdown
jk <done|next|blocked|load|stats> ... --project .
```

Reemplazá en `standup/SKILL.md` este texto:

```markdown
   the user draws a conclusion from them.

## Rules
```

por este:

```markdown
   the user draws a conclusion from them.
6. **Profiles.** Reports read each status through a role (`todo`, `active`, `blocked`, `waiting`, `delivered`,
   `dropped`) that a person confirmed once per project. A line starting with `> ⚠` at the top of the output says what
   is missing: a project without profile (the report falls back to Jira's category), statuses nobody decided, or a
   status the profile has never seen. Show it as it is. To fix it run `jk board setup KEY`: it prints what it
   understood and exits 3 while statuses are undecided. Relay each undecided status to the user, ask which role it
   plays, and apply the answer with `jk board set KEY <role> "<status>"`. Never choose a role yourself.

## Rules
```

Reemplazá en `standup/SKILL.md` este texto:

```markdown
- Never print or ask for Jira credentials (`IC_JIRA_*`).
```

por este:

```markdown
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- `jk board setup|set` write only the local profile in `~/.config/jk`, never Jira.
```

- [ ] **Step 2: README**

Reemplazá en `README.md` este texto:

```markdown
Instala las dos skills, `jira-kanban` (crear y sincronizar épicas) y `jira-standup` (reportes de solo lectura). Sigue el
```

por este:

```markdown
Por defecto instala `jira-standup` (reportes de solo lectura) y deja `jk` en `~/.local/bin/jk`; con
`./install.sh --with-write` suma `jira-kanban` (crear y sincronizar épicas). Volver a correrlo nunca quita una skill
ya instalada. Sigue el
```

Reemplazá en `README.md` este texto:

```markdown
`jk` es `python3 ~/.agents/skills/jira-kanban/jk.py`.
```

por este:

```markdown
`jk` queda en `~/.local/bin/jk` (lo crea `install.sh`; hace falta `~/.local/bin` en el PATH).
```

Reemplazá en `README.md` este texto:

```markdown
## Kanban local
```

por este:

```markdown
## Perfiles de board

Cada board dice «hecho» a su manera (`Done`, `Finalizado`, `Resuelto`) y Jira a veces archiva mal un estado: medido el
2026-10-09 en el Jira de la compañía, hay estados con nombre de «hecho» fuera de la categoría *done* en 29 proyectos.
Por eso los reportes no se fían de la categoría: leen un **rol por estado** que una persona confirma una vez por proyecto.

Roles: `todo`, `active`, `blocked`, `waiting` (frenado por un tercero), `delivered` y `dropped` (cancelado, rechazado,
no aplica). Varios estados pueden tener el mismo rol (`Finalizado` y `Resuelto` → `delivered`). Los perfiles viven en
`~/.config/jk/profiles/<KEY>.json` (o en `$JK_CONFIG_DIR`) y no se editan a mano.

| Comando | Qué hace |
|---|---|
| `jk board setup KEY [--kind flow\|scrum\|helpdesk]` | Lee los estados de Jira, propone un rol por estado y guarda el borrador; correrlo de nuevo no pierde tus decisiones |
| `jk board set KEY ROL "ESTADO"…` | Asigna un rol por nombre (o `id:<id>` si dos estados se llaman igual); todo o nada |
| `jk board show KEY` · `jk board check KEY` | Muestra el perfil · lo compara con los estados de Jira ahora |
| `jk board survey [--type T] [--json]` | Propone roles para todos los proyectos y cuenta qué necesita una decisión; no guarda nada |

Salida: `0` listo, `1` entrada rechazada, `2` no se pudo (Jira o disco) y **`3` el perfil tiene estados sin rol**: una
persona tiene que decidir. Un reporte de un proyecto sin perfil usa la categoría de Jira y lo avisa arriba con `> ⚠`.
`jk board EPIC` sigue siendo el tablero local de una épica.

## Kanban local
```

- [ ] **Step 3: Corregir la spec con lo que se midió al planificar**

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

````markdown
```
jkan/
  core/      jira (cliente), config, journal, people
  reports/   window, queries, standup, stats, render, team  (lectura)
  write/     sync, spec, description, evidence, kanban, template, preview, plan, apply  (escritura)
  profile/   board setup, roles, views
  cli.py     parte en un módulo de comandos por skill
```
````

por este:

````markdown
```
jkan/                  (módulos planos: 25 archivos de tests hacen `from jkan import <módulo>`)
  núcleo     jira, config, journal, people
  lectura    window, queries, standup, stats, render, roles, board_profile, board_cli, team
  escritura  sync, spec, description, evidence, kanban, template, preview, plan, apply
  cli.py     raíz de composición: el único que importa los dos lados
```
````

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
- Regla verificada por test: **`reports/` y `profile/` no importan `write/`**. La skill de lectura no puede escribir por
  construcción.
```

por este:

```markdown
- Regla verificada por `tests/test_boundaries.py`: **ningún módulo de lectura importa uno de escritura**, el núcleo no
  importa ninguno de los dos lados y todo módulo nuevo tiene que figurar en un lado. Ordena el código, pero `jk` es un
  solo binario: no quita `create|push|assign --apply` de una instalación de solo lectura (ver «Riesgos»).
```

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
`open` lista los estados sin decidir.
```

por este:

```markdown
`open` y `roles` se calculan a partir de `statuses`, la lista que se guarda con `id, name, category, role, by,
suggest, why` por estado.
```

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
Termina con **código 2** mientras
```

por este:

```markdown
Termina con **código 3** (el 2 ya es «no se pudo») mientras
```

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
y código de salida 2 significa "falta una decisión humana"
```

por este:

```markdown
y el código 3 de `jk board` significa "falta una decisión humana"
```

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
`setup` corrido sobre los 253 proyectos, con el porcentaje `alta` vs `decidir` medido; los 29 proyectos mal categorizados dan lo correcto |
```

por este:

```markdown
`jk board survey` sobre todos los proyectos, con el porcentaje `alta` vs `decidir` y los proyectos con la categoría mal puesta medidos; un `Done` archivado en «en curso» cuenta como cerrado y no como WIP. Los estados en la categoría *new* no los trae la consulta por categoría: se resuelven con consultas por rol en la fase 2 |
```

Reemplazá en `docs/superpowers/specs/2026-10-09-jira-em-design.md` este texto:

```markdown
- **Scrum y sprints:** 3 de 50 boards y sin API Agile; fuera de la versión 1.
```

por este:

```markdown
- **Scrum y sprints:** 3 de 50 boards y sin API Agile; fuera de la versión 1.
- **Escritura que ya existe sin guardia:** `jk create|push|assign --apply` no exige terminal interactiva ni `APRUEBO`; solo
  los frena el hook local `git-guardrails.sh`, que los EM no tienen, y `jk` es un solo binario, así que una instalación de
  solo lectura también los contiene. Decisión pendiente: aplicar el mismo guardia a esos tres comandos, o dejarlos
  fuera de la instalación por defecto.
```

- [ ] **Step 4: Verificar**

```bash
rg -n "jira-kanban/jk\.py" -g '!docs/**' .      # sin resultados
rg -n "código 2|código de salida 2" docs/superpowers/specs/2026-10-09-jira-em-design.md   # sin resultados
python3 -m unittest discover -s tests 2>&1 | tail -3
```

Expected: las dos búsquedas no devuelven nada y la suite sigue en verde.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md standup/SKILL.md README.md docs/superpowers/specs/2026-10-09-jira-em-design.md
git commit -m "docs: board profiles, jk on the PATH and the spec corrections found while planning"
```

---

### Task 9: Aceptación contra el Jira real y cierre de la fase

**Files:**
- Modify: `docs/superpowers/specs/2026-10-09-jira-em-design.md` (sección nueva al final)

Todo es **solo lectura** y usa un directorio de configuración temporal, así que no toca tu `~/.config/jk`.

- [ ] **Step 1: Medir el diccionario sobre todos los proyectos**

```bash
export JK_CONFIG_DIR="$(mktemp -d)"
jk board survey --json > /tmp/jk-survey.json
python3 -I -c "import json; print(json.load(open('/tmp/jk-survey.json'))['summary'])"
```

Medido el 2026-10-09 con este mismo código, mientras se escribía el plan:
`{'projects_read': 253, 'projects_denied': 0, 'statuses': 2256, 'alta': 1785, 'decidir': 471, 'projects_needing_decisions': 157, 'mismatch_statuses': 42, 'mismatch_projects': 38}`.
Es decir: **79% de las propuestas con confianza alta, 21% a decidir; 96 de 253 proyectos no necesitan ninguna decisión.** Pegá lo que imprima tu corrida; si difiere mucho (por ejemplo más de 5 puntos de porcentaje), pará y mirá por qué antes de seguir.

- [ ] **Step 2: Probar el flujo completo sobre un board real**

```bash
jk board setup UA; echo "exit $?"          # 3 mientras queden estados sin decidir
jk board set UA waiting "ON HOLD"
jk board set UA waiting "AWAITING APPROVAL"; echo "exit $?"   # 0 al decidir el último
jk board show UA | head -5
jk done --since 2026-10-01 --jira-project UA
```

Expected: el primer `setup` sale con 3 y propone `waiting`/`blocked` solo como pregunta (`¿?`); tras los dos `set` sale con 0 y dice `**Perfil completo.**`. El reporte `jk done` funciona; si ese proyecto tuvo issues en la ventana y algún proyecto no tiene perfil, la primera línea es `> ⚠ Sin perfil: …`.

- [ ] **Step 3: El tablero local de siempre sigue andando**

Run: `jk board PLATE-596 --project /tmp; echo "exit $?"`
Expected: imprime `PLATE-596: 0 issues` (no hay kanban local en `/tmp`) y sale con 0. Si en cambio falla con un error de argumentos, el despacho de `board` en `cli.py` está mal.

- [ ] **Step 4: Dejar los números en la spec**

Agregá al final de `docs/superpowers/specs/2026-10-09-jira-em-design.md` esta sección, con los números de **tu** corrida del Step 1:

```markdown
## Resultados de la fase 1

Medido con `jk board survey` sobre el Jira real el 2026-10-09 (solo lectura).

| Medida | Resultado |
|---|---|
| Proyectos leídos / sin acceso | 253 / 0 |
| Estados (ids únicos por proyecto) | 2256 |
| Propuestas con confianza `alta` | 1785 (79%) |
| Estados que necesitan una persona (`decidir`) | 471 (21%) |
| Proyectos sin ninguna decisión pendiente | 96 de 253 |
| Proyectos con al menos una decisión | 157 |
| Estados con la categoría de Jira mal puesta | 42 en 38 proyectos |

En promedio sobre todos los proyectos son 1,9 estados a decidir por board (471 / 253), así que seguir 5 boards son unos 9. Es una cuenta, no una medición sobre los boards de un EM real.
```

(La última línea es aritmética sobre esos mismos números; si tu corrida da otros, recalculala.)

- [ ] **Step 5: Verificación final en las dos versiones de Python y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3
/usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
git status --short
git add docs/superpowers/specs/2026-10-09-jira-em-design.md
git commit -m "docs(spec): phase 1 survey results"
```

Expected: `Ran 320 tests ... OK` dos veces y `git status --short` vacío salvo lo recién agregado. La rama `feat/jira-em-fases-0-1` queda lista para que la revises y la publiques vos.

---

## Después de este plan

Planes que se escriben con lo que muestre esta fase, uno por vez:

1. **Fase 2, views y reportes de equipo:** consultas armadas con `status in (<ids>)` a partir de los roles (esto arregla los estados archivados en la categoría *new*), `jk team setup`, y los siete reportes. Necesita los números del Step 1 de la Task 9 y, para `desk`, que alguien confirme qué service desks usan SLA.
2. **Fase 3, `jk plan` y `jk apply`:** necesita probar si `!` entrega una terminal interactiva, **un proyecto de pruebas** para escribir de verdad y la decisión sobre el hallazgo de los comandos `--apply` que ya existen.
3. **Fase 4, cierre:** renombrar el repo y actualizar `git-guardrails.sh` y `AGENTS.md`.
