# Renombre del CLI `jk` a `jtk`: diseño

Fecha: 2026-10-10. Estado: aprobado en chat por el usuario ("renombre completo", luego "aprobado").

## Intención

El repo ya se llama `jira-team-kit`; el comando pasa a llamarse `jtk` para coincidir. Renombre completo: `jk` deja
de existir como comando. Dos cosas no pueden pasar: que `jtk apply` quede sin bloquear por el hook, y que se
pierdan los perfiles y el registro de escrituras reales del usuario.

## Decisiones

1. **Binario:** `jk.py` pasa a `jtk.py`; todos los `prog="jk…"` (cli.py, team_cli.py, board_cli.py, plan_cli.py) a `jtk…`;
   los textos de ayuda, mensajes y el comando exacto que imprime la guarda dicen `jtk`.
2. **Paquete interno `jkan/`:** se queda con ese nombre (invisible para quien usa la herramienta; renombrarlo
   toca cada import sin beneficio).
3. **Datos:** `~/.config/jk` → `~/.config/jtk`, `~/.local/state/jk` → `~/.local/state/jtk`; variables
   `JK_CONFIG_DIR`/`JK_STATE_DIR` → `JTK_CONFIG_DIR`/`JTK_STATE_DIR`.
4. **Sin lectura de las rutas viejas.** Un fallback silencioso sería el alias que se descartó. Migración: `install.sh`
   detecta `~/.config/jk` o `~/.local/state/jk` y **imprime** los `mv` exactos; los corre la persona. Nunca mueve datos.
5. **Registro de escrituras:** las líneas nuevas llevan `"tool": "jtk"`; las viejas conservan `"jk"`. Medido:
   `state.applied`/`entries` filtran por `plan`, no por `tool` (`jkan/state.py:110-127`), así que un plan aplicado a
   medias antes del renombre se sigue reconociendo.
6. **Instalación:** `install.sh` crea `~/.local/bin/jtk`; borra `~/.local/bin/jk` **solo si es un enlace que apunta a
   este repo**; si apunta a otra cosa, avisa y no lo toca.
7. **Hook (del usuario):** parche nuevo `tools/git-guardrails-jtk.patch`, un delta que se aplica encima del de fase 4
   (`git-guardrails-jk-apply.patch`, ya aplicado por el usuario, se conserva como historia y no se renombra);
   las reglas R1–R3 reconocen `jtk` **y** `jk` (cuesta una alternativa en la regex y cubre scripts o historial
   viejos). `tools/check-guardrails.sh` pasa a casos sobre `jtk` más casos que prueban que `jk apply` sigue bloqueado.
8. **Fuera del repo:** `~/CurrentCode/SPECKIT/AGENTS.md`, `README.md` de la raíz y la prosa de WayOfWork
   (`wow/state.py:122`, `wow/flow_sk.py:3,129`, `wow-guide` y `wow-sk-prep` SKILL.md), este último en su propio repo y commit.
9. **Docs históricas:** specs y planes de fases 1–4 (y el spec maestro) quedan como registro; no se reescriben. Se
   actualizan README, skills (`SKILL.md`, `ops/`, `standup/`, `em/`), `references/` y `templates/` si nombran el comando.

## Orden obligatorio de despliegue

1. Rama `feat/rename-jtk` con tests verdes (3.x y `/usr/bin/python3` 3.9).
2. El usuario aplica el parche del hook con `!` (`patch -N`, antes de mergear: sigue bloqueando `jk`) y `tools/check-guardrails.sh` da verde.
3. Mergea. Recién entonces: `./install.sh --with-write` y los `mv` de datos.

Así nunca hay un `jtk` que un agente pueda correr con un hook que no lo ve. El agente no toca `~/.claude/hooks`.

## Pruebas

- Los tests existentes se actualizan al nombre nuevo (sin relajar aserciones).
- Nuevo: `jtk.py` existe y `jk.py` no; ningún `prog=` dice `jk`; la guarda imprime `jtk apply <id>`; las rutas por
  defecto terminan en `.config/jtk` y `.local/state/jtk`; `JK_*` ya no se leen (con `JK_STATE_DIR` seteada se usa la
  ruta por defecto); `install.sh` imprime los `mv` cuando existen datos viejos y no los mueve; no borra un `jk` ajeno.
- Barrido final: `rg -n '\bjk\b'` en código, tests, skills y README del repo solo puede devolver las menciones
  deliberadas (hook que bloquea el nombre viejo, `"tool": "jk"` histórico, nota de migración).

## Riesgos y límites

- Desde que `jtk.py` existe en el árbol (checkout de la rama) y hasta que el hook reconoce `jtk`, un agente podría correr `jtk apply` por un pseudo-terminal sin que el hook lo vea: el parche va **antes** del merge (revisión final, hallazgo 1).
- El parche del hook sigue siendo segunda capa y solo cubre Claude Code (límite ya documentado en fase 4).
- Planes guardados en `~/.local/state/jk/plans` son archivos con hash de contenido: moverlos no cambia el id.

## Resultados

- Suite: 624 tests en `python3` y en `/usr/bin/python3` (3.9); RED observado antes de cada cambio (6/7 en `test_rename`,
  5/5 en los de `install.sh`).
- Hook: `tools/check-guardrails.sh` = 44 casos. Contra el hook actual del usuario, 22/44 (fallan los 22 que bloquean `jtk`, y el del nombre viejo por pseudo-terminal; los
  del nombre viejo pasan); contra una copia con `git-guardrails-jtk.patch` aplicado, 44/44. Tras la revisión final se agregó una regla: `create|push|assign --apply` por pseudo-terminal (hallazgo 2, ya existía desde fase 4). El hook real no se tocó
  (`cmp` contra la copia original).
- Desvío del plan: ninguno de fondo; el parche es delta (nota en el punto 7).
