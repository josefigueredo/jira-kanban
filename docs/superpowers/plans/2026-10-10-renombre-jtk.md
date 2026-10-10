# Renombre de `jk` a `jtk` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El CLI `jk` pasa a llamarse `jtk` en todo el repo, en `install.sh`, en el hook de segunda capa y en los documentos que lo nombran, sin perder datos del usuario ni dejar `jtk apply` sin bloquear.

**Architecture:** Un barrido mecánico y acotado (`sd`) sobre los archivos vivos del repo, precedido por un test nuevo que lo pinta de rojo; después `install.sh` aprende a limpiar el enlace viejo y a imprimir la migración de datos; el hook se parchea con un delta que reconoce `jtk` y `jk`; al final se actualizan los documentos del usuario fuera del repo. El paquete interno `jkan/` no se toca.

**Tech Stack:** Python 3 stdlib + `unittest` (también `/usr/bin/python3` 3.9), bash, `jq`, `sd`/`rg`/`fd`.

**Spec:** `docs/superpowers/specs/2026-10-10-renombre-jtk-design.md`

## Global Constraints

- Python 3 solo con stdlib; la suite pasa con `python3 -m unittest discover -s tests` y con `/usr/bin/python3 -m unittest discover -s tests` (3.9).
- Rama `feat/rename-jtk`; conventional commits, sin atribución de IA ni `Co-Authored-By` (regla del usuario).
- El paquete `jkan/` conserva su nombre; el log del proyecto sigue en `./.jira-kanban/jira-writes.jsonl` (no es `jk`).
- Nunca se leen `~/.config/jk`, `~/.local/state/jk`, `JK_CONFIG_DIR`, `JK_STATE_DIR`: sin fallback.
- `install.sh` nunca mueve datos del usuario y solo borra `~/.local/bin/jk` si es un enlace a `$REPO/jk.py`.
- El agente NO modifica `~/.claude/hooks/*` ni corre `jtk apply`; el parche se prueba sobre una copia en el scratchpad.
- No se reescriben specs ni planes anteriores (`docs/superpowers/**` salvo este plan y su spec).
- Fuera del repo se editan `~/CurrentCode/SPECKIT/AGENTS.md` y `README.md` (no es repo git: backup en el scratchpad antes de editar) y la prosa de WayOfWork (repo propio: rama y commit, sin push).

## Review Focus

- Un script o historial viejo que diga `jk apply` o `jk push --apply` no puede pasar el hook (casos con el nombre viejo en `check-guardrails.sh`).
- Quien tiene `JK_STATE_DIR`/`JK_CONFIG_DIR` exportadas no debe quedar escribiendo en el directorio por defecto sin enterarse: `install.sh` lo avisa.
- Las líneas ya escritas en `writes.jsonl` con `"tool": "jk"` siguen contando para `state.applied` (un plan a medias se retoma).
- Un `~/.local/bin/jk` que no es de este repo (enlace ajeno o archivo real) queda intacto.
- El `jtk` instalado arranca de verdad por el enlace: `python3 jtk.py --help` sale 0 y dice `usage: jtk`.

---

### Task 1: El barrido: `jtk.py`, rutas, variables, mensajes y docs vivas

**Files:**
- Create: `tests/test_rename.py`
- Rename: `jk.py` → `jtk.py`
- Modify (barrido): todo archivo versionado salvo `docs/`, `tools/`, `.superpowers/` y `tests/test_rename.py`

**Interfaces:**
- Consumes: `state.state_dir()`, `board_profile.config_dir()`, `state.log_write`, `state.applied` (existentes).
- Produces: comando y entrypoint `jtk`/`jtk.py`; rutas por defecto `~/.config/jtk` y `~/.local/state/jtk`; variables `JTK_CONFIG_DIR`/`JTK_STATE_DIR`; campo `"tool": "jtk"`.

- [ ] **Step 1: Escribir el test que falla (`tests/test_rename.py`)**

```python
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, state_dir
from jkan import board_profile, state


class RenameTest(unittest.TestCase):
    def test_the_entry_point_is_jtk_py_and_jk_py_is_gone(self):
        self.assertTrue((ROOT / "jtk.py").is_file())
        self.assertFalse((ROOT / "jk.py").exists())

    def test_the_installed_entry_point_starts_and_says_jtk(self):
        done = subprocess.run([sys.executable, str(ROOT / "jtk.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertRegex(done.stdout, r"^usage: jtk\b")

    def test_no_parser_still_calls_itself_jk(self):
        for path in (ROOT / "jkan").glob("*.py"):
            self.assertIsNone(re.search(r'prog="jk\b', path.read_text(encoding="utf-8")), path.name)

    def test_the_default_folders_are_the_new_names(self):
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            for name in ("JTK_CONFIG_DIR", "JTK_STATE_DIR", "JK_CONFIG_DIR", "JK_STATE_DIR"):
                env.pop(name, None)
            self.assertRegex(str(board_profile.config_dir()), r"\.config/jtk$")
            self.assertRegex(str(state.state_dir()), r"\.local/state/jtk$")

    def test_the_old_variables_are_not_read(self):
        other = tempfile.mkdtemp(prefix="jtk-old-")
        with mock.patch.dict("os.environ", {"JK_CONFIG_DIR": other, "JK_STATE_DIR": other}, clear=False) as env:
            env.pop("JTK_CONFIG_DIR", None)
            env.pop("JTK_STATE_DIR", None)
            self.assertNotEqual(str(board_profile.config_dir()), other)
            self.assertNotEqual(str(state.state_dir()), other)

    def test_new_log_lines_say_jtk(self):
        base = state_dir()
        state.log_write({"plan": "p1", "key": "TEAM-1", "result": "ok"})
        line = json.loads((base / "writes.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(line["tool"], "jtk")

    def test_lines_written_before_the_rename_still_count_as_applied(self):
        base = state_dir()
        (base / "writes.jsonl").write_text(
            json.dumps({"ts": "T0", "tool": "jk", "plan": "p1", "key": "TEAM-1", "result": "ok"}) + "\n",
            encoding="utf-8")
        self.assertEqual(state.applied("p1"), {"TEAM-1"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verlo fallar**

Run: `python3 -m unittest tests.test_rename 2>&1 | tail -20` (desde la raíz del repo; si el import de `helpers` falla, usar `python3 -m unittest discover -s tests -p 'test_rename.py'`)
Expected: FAIL en `test_the_entry_point...`, `test_the_installed_entry_point...`, `test_the_default_folders...`, `test_the_old_variables...`, `test_new_log_lines...` (todos por el nombre viejo); `test_lines_written_before...` PASA (ya es verdad hoy). Anotar cuáles fallan.

- [ ] **Step 3: El barrido**

```bash
git mv jk.py jtk.py
FILES=$(git ls-files | rg -v '^(docs/|tools/|\.superpowers/|tests/test_rename\.py$)')
echo "$FILES" | xargs rg -l '\bjk\b|JK_' | wc -l
echo "$FILES" | xargs rg -l '\bjk\b|JK_' | xargs sd '\bjk\b' 'jtk'
echo "$FILES" | xargs rg -l 'JK_' | xargs sd 'JK_' 'JTK_'
```

Expected: el primer conteo lista ~50 archivos (README, SKILL.md de la raíz, `em/`, `ops/`, `standup/`, `references/`, `conventions.json`, `install.sh`, `jtk.py`, `jkan/*.py`, `tests/*.py`). Después: `rg -n '\bjk\b|JK_' $(git ls-files | rg -v '^(docs/|tools/|\.superpowers/|tests/test_rename\.py$)')` no devuelve nada, y `rg -c 'jkan' jtk.py jkan | head -3` sigue mostrando `jkan` intacto.

- [ ] **Step 4: Revisar el diff a ojo en los puntos delicados**

Run: `git diff -U0 -- install.sh jtk.py jkan/state.py jkan/board_profile.py | rg '^[+-]' | rg -v '^(\+\+\+|---)'`
Expected: `install.sh` ahora linkea `jtk.py` en `~/.local/bin/jtk`; `state.py` y `board_profile.py` leen `JTK_*` y `.../jtk`; `"tool": "jtk"`. Ninguna línea toca `jkan` ni `.jira-kanban`.

- [ ] **Step 5: Correr toda la suite en los dos Python**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -4; /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -4`
Expected: ambas terminan en `OK` (612 + 7 = 619 tests, o el total actual +7). Si `test_install` o `test_skills` fallan, es el barrido que dejó un texto inconsistente: arreglar el texto, no la aserción.

- [ ] **Step 6: Commit**

```bash
git add -A -- . ':!.superpowers'
git commit -m "refactor: rename the jk command to jtk

The entry point, data folders, environment variables, log tag and the live docs
now say jtk. The jkan package keeps its name. Nothing reads the old paths."
```

---

### Task 2: `install.sh` limpia el enlace viejo y avisa la migración

**Files:**
- Modify: `install.sh`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: `install(home, *args)` y `fresh_home()` de `tests/test_install.py`; `install.sh` ya linkea `~/.local/bin/jtk` (Task 1).
- Produces: salida de `install.sh` con líneas `migrate:` (stdout) y `note:` (stderr); contrato de qué toca y qué no.

- [ ] **Step 1: Tests que fallan (agregar a `InstallTest`)**

```python
    def test_an_old_jk_link_to_this_repo_is_removed(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        os.symlink(str(ROOT / "jk.py"), home / ".local/bin/jk")
        self.assertEqual(install(home).returncode, 0)
        self.assertFalse(os.path.lexists(home / ".local/bin/jk"))
        self.assertEqual(os.readlink(home / ".local/bin/jtk"), str(ROOT / "jtk.py"))

    def test_a_jk_that_is_not_this_repos_link_is_left_alone(self):
        home = fresh_home()
        (home / ".local/bin").mkdir(parents=True)
        os.symlink("/elsewhere/jk.py", home / ".local/bin/jk")
        result = install(home)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(os.readlink(home / ".local/bin/jk"), "/elsewhere/jk.py")
        self.assertIn("left alone", result.stderr)

    def test_old_data_is_announced_with_the_exact_mv_and_never_moved(self):
        home = fresh_home()
        (home / ".config/jk/profiles").mkdir(parents=True)
        (home / ".local/state/jk").mkdir(parents=True)
        result = install(home)
        self.assertEqual(result.returncode, 0)
        self.assertIn("mv ~/.config/jk ~/.config/jtk", result.stdout)
        self.assertIn("mv ~/.local/state/jk ~/.local/state/jtk", result.stdout)
        self.assertTrue((home / ".config/jk/profiles").is_dir())
        self.assertFalse((home / ".config/jtk").exists())

    def test_no_migration_notice_when_there_is_nothing_to_migrate_or_the_new_folder_exists(self):
        home = fresh_home()
        self.assertNotIn("mv ", install(home).stdout)
        (home / ".config/jk").mkdir(parents=True)
        (home / ".config/jtk").mkdir(parents=True)
        result = install(home)
        self.assertNotIn("mv ~/.config/jk", result.stdout)
        self.assertIn("both ~/.config/jk and ~/.config/jtk exist", result.stderr)

    def test_old_environment_variables_are_called_out(self):
        home = fresh_home()
        env = dict(os.environ, HOME=str(home), JK_STATE_DIR="/somewhere", JK_CONFIG_DIR="/else")
        result = subprocess.run(["bash", str(ROOT / "install.sh")], env=env, capture_output=True, text=True)
        self.assertIn("JK_STATE_DIR is no longer read; use JTK_STATE_DIR", result.stderr)
        self.assertIn("JK_CONFIG_DIR is no longer read; use JTK_CONFIG_DIR", result.stderr)
```

- [ ] **Step 2: Verlos fallar**

Run: `python3 -m unittest tests.test_install 2>&1 | tail -15`
Expected: FAIL en los cinco tests nuevos (el enlace viejo sigue ahí, no hay `migrate:`/`note:`); los demás pasan.

- [ ] **Step 3: Implementar (antes de `exit "$status"` en `install.sh`, después del bloque `link ... jtk`)**

```bash
# The command used to be called jk. Remove its link only when it is this repo's own; never touch anything else.
OLD="$HOME/.local/bin/jk"
if [ -L "$OLD" ]; then
  if [ "$(readlink "$OLD")" = "$REPO/jk.py" ]; then
    rm "$OLD"
    echo "removed the old link ~/.local/bin/jk (the command is jtk now)"
  else
    echo "note: ~/.local/bin/jk points somewhere else and was left alone" >&2
  fi
elif [ -e "$OLD" ]; then
  echo "note: ~/.local/bin/jk is not a symlink and was left alone" >&2
fi
# Data is renamed by the person, never by this script: it prints the exact commands.
migrate() {  # migrate <old> <new> (both written with ~)
  local o="${1/#\~/$HOME}" n="${2/#\~/$HOME}"
  [ -e "$o" ] || return 0
  if [ -e "$n" ]; then
    echo "note: both $1 and $2 exist; merge them by hand, nothing was moved" >&2
  else
    echo "migrate: mv $1 $2"
  fi
}
migrate "~/.config/jk" "~/.config/jtk"
migrate "~/.local/state/jk" "~/.local/state/jtk"
for name in CONFIG STATE; do
  var="JK_${name}_DIR"
  [ -n "${!var:-}" ] && echo "note: $var is no longer read; use JTK_${name}_DIR" >&2
done
```

Y actualizar el comentario de cabecera: `# CLI: ~/.local/bin/jtk points at jtk.py; …` y agregar una línea `# The old command name jk is not kept: a link to this repo is removed and the data move is printed, not done.`

- [ ] **Step 4: Verlos pasar y correr la suite completa**

Run: `python3 -m unittest tests.test_install 2>&1 | tail -4; python3 -m unittest discover -s tests 2>&1 | tail -3; /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` en las tres. Nota: `[ -n ... ] && echo` bajo `set -e` no aborta porque está dentro de un `for` con `&&` simple (si abortara el test de variables lo mostraría: usar `if` en ese caso).

- [ ] **Step 5: Commit**

```bash
git add install.sh tests/test_install.py
git commit -m "feat: install.sh removes the old jk link and prints the data migration"
```

---

### Task 3: Hook de segunda capa: parche delta y casos de `check-guardrails.sh`

**Files:**
- Modify: `tools/check-guardrails.sh`
- Create: `tools/git-guardrails-jtk.patch` (delta sobre el hook con el parche de fase 4 ya aplicado)
- No se modifica `~/.claude/hooks/git-guardrails.sh`; se trabaja sobre una copia en el scratchpad.

**Interfaces:**
- Consumes: el hook real `~/.claude/hooks/git-guardrails.sh` (solo lectura) con las variables `JK` (línea ~47) y `APLICA` (línea ~66).
- Produces: `tools/check-guardrails.sh` con casos sobre `jtk` y sobre el nombre viejo; parche que el usuario aplica con `patch`.

- [ ] **Step 1: Pasar los casos al nombre nuevo y agregar los del viejo**

```bash
sd '\bjk\b' 'jtk' tools/check-guardrails.sh
```

Luego, antes del bloque `# allowed`/los `check 0` (o al final de los `check`, antes del `echo "$((total - wrong))…"`), agregar estos casos del nombre viejo y uno de borde:

```bash
# the old name stays blocked too: old scripts and shell history still say jk
check 2 'jk apply abc123def456'
check 2 'jk push PLATE-1 --apply'
check 2 "tmux send-keys 'jk apply abc123def456' Enter"
check 2 'python3 /Users/x/jira-kanban/jk.py apply abc123def456'
check 0 'jk plan move plataforma TEAM-1 --to active'
check 0 'jtk applyx'
```

Y en la cabecera cambiar los textos que digan `jk`. (El barrido ya lo hizo; verificar con `rg -n '\bjk\b' tools/check-guardrails.sh`: deben quedar solo los casos nuevos de arriba.)

- [ ] **Step 2: Verlo fallar contra el hook actual del usuario**

Run: `tools/check-guardrails.sh; echo exit=$?`
Expected: `WRONG want=2 got=0 :: jtk …` en todos los casos que bloquean `jtk` (≈ 25), los casos con `jk` pasan, `exit=1`. Anotar el total (`N/M cases`).

- [ ] **Step 3: Construir el parche sobre una copia (scratchpad)**

```bash
S=/private/tmp/claude-504/-Users-josefigueredo-CurrentCode-SPECKIT/7e3c6941-571f-4c6f-b047-496874b2ab53/scratchpad
cp ~/.claude/hooks/git-guardrails.sh $S/hook.orig && cp $S/hook.orig $S/hook.new
```

En `$S/hook.new` hacer estos reemplazos con `sd`, que fallan si no encuentran (verificar cada uno con `rg -c` antes y después; cada patrón aparece una vez):

- `JK="…/)?jk(\.py)?[[:space:]]+"` → `…/)?(jtk|jk)(\.py)?[[:space:]]+`
- `APLICA='jk(\.py)?` → `APLICA='(jtk|jk)(\.py)?`
- Los textos de mensaje y comentarios que digan `jk create / jk push / jk assign` y `jk apply` → `jtk/jk create…` y `jtk apply`.

Generar el delta y probarlo:

```bash
diff -u $S/hook.orig $S/hook.new | sed -e '1s|.*|--- a/git-guardrails.sh|' -e '2s|.*|+++ b/git-guardrails.sh|' > tools/git-guardrails-jtk.patch
cp $S/hook.orig $S/hook.try && (cd $S && patch --dry-run hook.try < $OLDPWD/tools/git-guardrails-jtk.patch)
```

Expected: `checking file hook.try` sin rechazos. (`$OLDPWD` es el repo; ajustar si el `cd` cambia.)

- [ ] **Step 4: Verlo pasar sobre la copia parcheada**

```bash
cp $S/hook.orig $S/hook.final && (cd $S && patch hook.final < <repo>/tools/git-guardrails-jtk.patch) && chmod +x $S/hook.final
tools/check-guardrails.sh $S/hook.final; echo exit=$?
```

Expected: `N/N cases behaved as expected`, `exit=0` (N = 33 + 6 − duplicados; el número exacto se registra en el ledger). Además `tools/check-guardrails.sh $S/hook.orig` sigue dando `exit=1` (prueba de que el test discrimina).

- [ ] **Step 5: Commit**

```bash
git add tools/check-guardrails.sh tools/git-guardrails-jtk.patch
git commit -m "feat: the guardrails hook patch and its cases cover jtk and the old jk name"
```

---

### Task 4: README, spec y barrido final del repo

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-10-10-renombre-jtk-design.md`

- [ ] **Step 1: README, sección de migración**

Agregar una sección corta "Si venías usando `jk`" (castellano rioplatense) con: el comando ahora es `jtk`; `./install.sh` borra el enlace viejo y **imprime** los `mv` (`~/.config/jk` → `~/.config/jtk`, `~/.local/state/jk` → `~/.local/state/jtk`) que corrés vos; las variables ahora son `JTK_CONFIG_DIR`/`JTK_STATE_DIR` y las viejas no se leen; el orden obligatorio: mergear, aplicar el parche del hook, recién después instalar.

- [ ] **Step 2: README, sección del hook**

En "Segunda capa: el hook de Claude Code" (hoy: `bloquea jtk apply … el parche está en tools/git-guardrails-jk-apply.patch`): decir que bloquea `jtk` y también el nombre viejo `jk`, que el parche de fase 4 (`tools/git-guardrails-jk-apply.patch`, ya aplicado) se completa con `tools/git-guardrails-jtk.patch` (se aplica encima: `patch ~/.claude/hooks/git-guardrails.sh < tools/git-guardrails-jtk.patch`), y que `tools/check-guardrails.sh` cuenta ahora N casos (el número real de Task 3).

- [ ] **Step 3: Spec, nota de desvío**

En el spec, punto 7, anotar: «el parche nuevo es un delta (`git-guardrails-jtk.patch`) que se aplica encima del de fase 4, que se conserva como historia; no se renombra el viejo». Agregar al final una sección `## Resultados` con la salida real de Task 3 y la suite.

- [ ] **Step 4: Barrido final**

Run: `rg -n '\bjk\b|JK_' $(git ls-files | rg -v '^(docs/|\.superpowers/)')`
Expected: solo las menciones deliberadas: `tools/check-guardrails.sh` (casos del nombre viejo), `tools/git-guardrails-jk-apply.patch` (historia), `install.sh` (limpieza del enlace viejo, `migrate`, variables viejas), `tests/test_install.py` y `tests/test_rename.py` (prueban lo viejo) y la sección de migración del README. Cualquier otra aparición es un resto del barrido: corregirla.

- [ ] **Step 5: Suite en los dos Python y commit**

```bash
python3 -m unittest discover -s tests 2>&1 | tail -3; /usr/bin/python3 -m unittest discover -s tests 2>&1 | tail -3
git add README.md docs/superpowers/specs/2026-10-10-renombre-jtk-design.md
git commit -m "docs: jtk migration notes, hook patch order and results"
```

Expected: `OK` en ambos.

---

### Task 5: Fuera del repo: AGENTS.md, README raíz y prosa de WayOfWork

**Files:**
- Modify: `~/CurrentCode/SPECKIT/AGENTS.md`, `~/CurrentCode/SPECKIT/README.md` (no es repo git: backup en el scratchpad antes)
- Modify: prosa de WayOfWork (`wow/state.py:122`, `wow/flow_sk.py:3,129`, `skills/wow-guide/SKILL.md`, `skills/wow-sk-prep/SKILL.md` o donde estén: ubicar con `rg -n '\bjk\b' ~/CurrentCode/SPECKIT/Harness/WayOfWork`) — rama `docs/jtk-rename` en ese repo

- [ ] **Step 1: Medir y respaldar**

```bash
S=/private/tmp/claude-504/-Users-josefigueredo-CurrentCode-SPECKIT/7e3c6941-571f-4c6f-b047-496874b2ab53/scratchpad
cp ~/CurrentCode/SPECKIT/AGENTS.md $S/AGENTS.md.bak-jtk; cp ~/CurrentCode/SPECKIT/README.md $S/README.root.bak-jtk
rg -n '\bjk\b|JK_' ~/CurrentCode/SPECKIT/AGENTS.md ~/CurrentCode/SPECKIT/README.md ~/CurrentCode/SPECKIT/Harness/WayOfWork -g '!docs/superpowers/**' -g '!.git/**'
git -C ~/CurrentCode/SPECKIT/Harness/WayOfWork status -sb | head -3
python3 -m unittest discover -s ~/CurrentCode/SPECKIT/Harness/WayOfWork/tests 2>&1 | tail -3
```

Expected: lista de menciones con archivo y línea; estado limpio de WayOfWork; suite verde (anotar el total). Si WayOfWork tiene cambios sin commitear que no son nuestros, parar y avisar.

- [ ] **Step 2: AGENTS.md y README raíz (con aserción de que el reemplazo ocurrió)**

En `AGENTS.md`, bullet «El usuario publica»: `jk create|push|assign --apply`, `jk apply <id>`, `jk plan …`, `jk …` → `jtk …`, y agregar «(el nombre viejo `jk` sigue bloqueado por el hook)». En el README raíz, la fila de jira-kanban: `jk` → `jtk`. Hacerlo con un script Python que haga `assert old in text` antes de reemplazar (el error anterior fue un reemplazo silencioso). Verificar con `rg -n '\bjk\b' AGENTS.md README.md` que quedan solo las menciones deliberadas.

- [ ] **Step 3: WayOfWork**

```bash
git -C ~/CurrentCode/SPECKIT/Harness/WayOfWork switch -c docs/jtk-rename
```

Reemplazar `jk` → `jtk` solo en las menciones del Step 1 que nombran el comando (no en palabras ajenas); correr su suite de nuevo. Si un test fija el texto viejo, cambiar texto y test juntos. Commit: `docs: the jira-kanban command is called jtk now`. Sin push.

- [ ] **Step 4: Verificar y dejar el estado**

Run: `python3 -m unittest discover -s ~/CurrentCode/SPECKIT/Harness/WayOfWork/tests 2>&1 | tail -3; /usr/bin/python3 -m unittest discover -s ~/CurrentCode/SPECKIT/Harness/WayOfWork/tests 2>&1 | tail -3`
Expected: verde igual que antes. No hay commit en el repo de SPECKIT (raíz sin git).

---

## Después de las tareas (no son tareas del plan)

Revisión final de la rama completa por un subagente `fable`; una pasada de arreglos; merge a `main` si el usuario lo pide. Despliegue, todo del usuario y en este orden: push, merge, `patch` del hook + `tools/check-guardrails.sh` verde, `./install.sh --with-write`, los dos `mv` que imprime. Y recordar que WayOfWork queda en la rama `docs/jtk-rename` esperando su merge.
