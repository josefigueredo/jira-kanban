# jira-em, fase 4: cierre

Fecha: 2026-10-10. Continúa `2026-10-09-jira-em-design.md` (tabla de fases, fila 4) y `2026-10-10-jira-em-fase-3-design.md`
(«Límite honesto» de la guarda, «Bitácoras separadas», «Resultados de la fase 3»). Donde difieran, gana esta.

## Qué se quiere y para quién

La fase 3 dejó una escritura con guarda (`jk plan` + `jk apply`, y `APRUEBO` en los `--apply` viejos). La guarda frena lo
accidental y lo inducido desde contextos sin terminal, **pero no a un agente que abra un pseudo-terminal**. Esta fase
cierra eso con una segunda capa mecánica, deja las instrucciones de los agentes al día, junta el registro de lo que `jk`
escribió en un solo lugar y deja el repo con un nombre que describa lo que es.

Éxito = (1) el hook local bloquea a un agente que intente aplicar un plan, con casos positivos y negativos medidos;
(2) `AGENTS.md` dice la regla vigente; (3) «qué escribió jk» se responde mirando un solo archivo; (4) los dos menores de
la fase 3 que cambian lo que ve la persona están arreglados; (5) cada cita `archivo:línea` de las specs sigue valiendo.

## Alcance

Entra: hook, `AGENTS.md`, bitácora común, dos menores de la fase 3, re-verificación de citas, docs y renombre del repo.
No entra: la prueba real en el proyecto sandbox (Tarea 11 de la fase 3; sigue siendo de la persona y cierra la fase 3),
SLA, Scrum y sprints, perfiles compartidos, los menores de la fase 1, las consultas personales `jk done|stats` que aún
se basan en la categoría, y los otros dos menores de la fase 3 (el `n` de los comandos viejos cuenta issues y no
escrituras; el resumen de un re-apply no nombra lo ya hecho). Esos quedan escritos como pendientes.

## 1. Hook `git-guardrails.sh`

El archivo vive en `~/.claude/hooks/`, fuera del repo y de la autoridad del agente: **el agente deja el diff y un backup
con fecha; la persona lo aplica**. Hoy el hook bloquea `jk create|push|assign --apply` (variable `JK`, línea 47, regla en
la 48) y no tiene ningún caso para `jk apply`.

Reglas nuevas, con el mismo ancla de «donde empieza un comando» (`INICIO`) para que un mensaje de commit o un `grep` que
mencione el comando no se bloquee:

- **R1.** `jk apply …` (con los mismos prefijos que ya acepta: `rtk`, `python3 …/jk.py`, ruta absoluta) se bloquea.
  `jk plan …`, `jk team …` y el resto pasan: planificar solo lee.
- **R2.** Un comando que combine `jk apply` / `jk.py apply` con una herramienta que da un pseudo-terminal (`tmux`
  en sus formas `send-keys`, `send`, `new-session`…, `expect`, `pexpect`, `unbuffer`, `script`, `pty.`, `socat`) se bloquea
  aunque `jk apply` no esté al inicio, igual que escribir `APRUEBO` con `tmux send` (el rodeo en dos pasos). Es el
  rodeo que la guarda no puede ver. Falso positivo asumido: un mensaje de commit que nombre las dos cosas a la vez.
- El mensaje de bloqueo usa el texto existente («No tenés autoridad… lo corre él con `!`»), con el matiz de que `jk
  apply` **no funciona bajo `!`** (no hay TTY, medido en la fase 3): se corre en una ventana de terminal aparte.

Prueba: `tools/check-guardrails.sh [RUTA_DEL_HOOK]` arma el JSON de entrada del hook (`{"tool_input":{"command":…}}`),
lo ejecuta y compara el código de salida (2 = bloqueado, 0 = pasa). Casos que bloquean: `jk apply abc123def456`, `rtk jk
apply x`, `python3 ~/…/jk.py apply x`, `cd /tmp && jk apply x`, `/Users/…/.local/bin/jk apply x`, `tmux send-keys 'jk apply
x' Enter`, `expect -c 'spawn jk apply x'`. Casos que pasan: `jk plan move v K --to active`, `jk team status v --list`,
`jk applyx`, `git commit -m "docs: jk apply"`, `echo jk apply`, y los de los otros bloques del hook (que siguen igual).
El script **no** forma parte de `unittest discover` (el hook es del usuario y puede no estar actualizado); su salida
medida se cita en «Resultados».

## 2. `AGENTS.md` (raíz de SPECKIT)

En «El usuario publica» se suma `jk apply` a la lista de lo que escribe en Jira y lo hace la persona; se aclara que
`jk plan` sí lo corre el agente (solo lee y guarda un archivo) y que `jk apply` y los `--apply` viejos exigen una terminal
real, no el chat ni `!`. En «Dónde se toca qué» no cambia nada. La fila de `Harness/jira-kanban/` del `README.md` de la
raíz deja de decir «crea una épica… (`jk`)» y pasa a describir lo que es: reportes de equipo, escritura con guarda y
sincronización de épicas. La lista de skills del `CLAUDE.md` **global** de la persona no se toca (es privada); se le
propone el texto en el reporte final.

## 3. Bitácora común

Hay dos registros: el global (`~/.local/state/jk/writes.jsonl`, `tool: "jk"`, lo escribe `apply`) y el del proyecto
(`./.jira-kanban/jira-writes.jsonl`, `tool: "jira-kanban"`, mismo formato que el de WayOfWork; `jkan/journal.py:28`, lo
escriben `create|push|assign`). Decisión: **el del proyecto no cambia** (WayOfWork y las personas lo usan) y los tres
comandos viejos escriben **también** en el global.

- `journal.journal(project, command, also=None)` recibe una segunda función; `cli._client` le pasa `state.log_write`. Cada
  escritura de `Jira` va a las dos. `journal` y `state` son núcleo: el núcleo puede importarse a sí mismo.
- La entrada global de un comando viejo es `{"ts","tool":"jk","command":"create|push|assign","action","key",…,"result":"ok"}`
  y **no lleva `plan`**: así `state.applied(plan_id)` nunca la confunde con un plan aplicado.
- `plan` y `apply` siguen sin `journal` (su registro ya es el global; si no, se duplicaría cada línea).
- Un global ilegible nunca deshace la escritura ni la hace fallar (igual que hoy con el del proyecto).
- No hay migración de historia ni borrado de nada.

## 4. Dos menores de la fase 3

1. **`apply` revalida los perfiles.** El spec de la fase 3 pide que al aplicar los perfiles «sigan existiendo y
   confirmados»; hoy `jk apply` solo comprueba que existan (`team_cli.context`). Se agrega `plan.check_profiles` sobre
   las claves del plan: un perfil con estados sin rol sale con código 1 y sin escribir ni pedir la aprobación.
2. **`revert` y el cierre.** Un plan que cierra issues exige `--allow-close`; el revert de un `move` a `delivered` o
   `dropped` también. `jk plan revert ID [--allow-close]`: sin la bandera, si el plan inverso cierra algo, se rechaza con
   «reverting closes issues: add --allow-close».

## 5. Cierre

- **Citas.** Re-verificar contra el código cada `archivo:línea` de las specs (`rg -n "[a-z_]+\.py:[0-9]+" docs/superpowers/specs/`
  da 14 citas en las tres specs al 2026-10-10), abrir la línea citada, comprobar que dice lo que la spec afirma y corregir el
  número o la frase. Resultado en una lista «cita → vigente / corregida».
- **Docs.** README: sección corta «Segunda capa: el hook» (qué bloquea y cómo verificarlo con `tools/check-guardrails.sh`)
  y la bitácora común. Spec maestro: fila 4 de la tabla pasa a «hecha» y se cierra «Escritura que ya existe sin guardia»
  (resuelta en la fase 3). Esta spec gana «Resultados de la fase 4».
- **Renombre del repo.** Lo hace la persona en GitHub (hoy `josefigueredo/skill-kanban-jira`;
  GitHub redirige el nombre viejo). El nombre se decide en este paso, no antes. Después el agente actualiza el `git
  clone` y la URL del README, la fila del README de la raíz y, con `git remote set-url`, el `origin`. Nada de eso se
  adelanta antes del renombre: una URL citada tiene que existir (regla «medir, no especular» de `AGENTS.md`).

## Pruebas

TDD, en `python3` y `/usr/bin/python3` (3.9), con Jira falso. Línea base: 599 tests.

- **Bitácora común:** una escritura de `create|push|assign` deja una línea en cada registro; el global no tiene `plan`;
  `state.applied` la ignora; si el global no se puede escribir la escritura sigue y el exit code no cambia; `plan` y
  `apply` no duplican líneas.
- **Menores:** `apply` con un perfil sin decidir → código 1, `FakeJira.writes` vacío, `confirm` sin llamar; `revert` de un
  cierre sin `--allow-close` → rechazado con ese texto, con la bandera → plan; sin cierre no pide nada nuevo.
- **Hook:** `tools/check-guardrails.sh` con los casos de arriba; el agente lo corre sobre una copia del hook con el diff
  aplicado (en el scratchpad) **antes** de entregarlo, y la persona lo corre sobre el real después de aplicarlo.
- **Citas y docs:** la lista de citas verificadas; `wow cite check` no aplica (es de las páginas de `Research/docs`).

## Riesgos y pendientes

- **El hook solo cubre a Claude Code.** Codex y Cursor no pasan por `~/.claude/hooks`; ahí queda la guarda y la regla del
  `AGENTS.md`. Se documenta, no se resuelve.
- **R2 puede dar falsos positivos** (ver arriba) y no cubre un script propio que abra el pseudo-terminal sin nombrar
  esas herramientas; la guarda y las instrucciones siguen siendo capas, no certezas.
- **Prueba real de la fase 3** pendiente: la unificación de bitácoras se prueba con Jira falso; el comportamiento de
  `Jira.assign(key, None)` y de las transiciones con campos obligatorios solo se confirma en el sandbox.
- **Renombre:** la persona decide el nombre y el momento; hasta entonces los docs usan el actual.

## Resultados de la fase 4

- **Qué se entregó:** el tee de `journal.journal(…, also=)` apuntado a `state.log_write` desde `cli._client` (los tres
  comandos viejos escriben también en la bitácora común, sin `plan`); `jk apply` revalida perfiles antes de pedir la
  aprobación (y rechaza un plan cuyo board salió del view o perdió el perfil; antes `apply` escribía sin revalidar);
  `jk plan revert ID [--allow-close]`; `tools/check-guardrails.sh` y `tools/git-guardrails-jk-apply.patch`; `AGENTS.md`
  y el `README.md` de la raíz de SPECKIT editados en el lugar (no es un repo git; copias en el scratchpad); README de
  este repo.
- **Tests:** 612 en `python3` y en `/usr/bin/python3` (3.9), con Jira falso (línea base 599).
- **Hook, medido el 2026-10-10:** `tools/check-guardrails.sh` sobre el hook real daba **14/23** (fallaban justo los 9
  casos nuevos de `jk apply` y pseudo-terminal). La revisión final encontró rodeos naturales que la primera versión no
  cubría (tmux en dos pasos, `tmux send`, `pty.spawn` con lista, `pexpect`, `script` sin guion): se agregaron como casos,
  la copia parchada falló 6 de 33, y con la regex ampliada da **33/33**; el parche reproduce byte a byte el archivo
  probado (`patch` + `cmp`). El hook real no se tocó. Aplicado por la persona el 2026-10-10 (backup `git-guardrails.sh.bak-2026-10-10`) y verificado sobre el hook real: **33/33**.
- **Citas `archivo:línea`:** 15 revisadas abriendo la línea. Vigentes: `jira.py:248` (transition), `board_profile.py:33`,
  `sync.py:130|:240|:326`, `jira.py:110-120` (get). Corregidas: `kanban.py:15`→`:14`; `jira.py:98-108`→`:110-119` (get);
  `jira.py:114` (search/jql, children)→`:129` y `:206`; `jira.py:114` (maxResults)→`:126` y `:203`;
  `queries.py:24-29`→`:26-34` (ahora `_scope` acepta la lista de un view); `jira.py:208-216` (transiciones por nombre)→`:223-256`;
  `journal.py:24`→`:28` (cuatro citas); `cli.py:171|:187`→`:198|:214`.
- **Renombre del repo (2026-10-10):** `josefigueredo/skill-kanban-jira` → `josefigueredo/jira-team-kit`
  con `gh repo rename` (pedido por la persona, permiso ADMIN); `git ls-remote` sobre el nombre nuevo devuelve `1465a25`, el
  mismo `HEAD` de `main`. `origin` actualizado, README de este repo y de la raíz de SPECKIT al día; la carpeta local
  sigue siendo `Harness/jira-kanban` y el nombre viejo redirige.
- **Pendiente:** prueba real de la fase 3 en el sandbox, los dos menores de la fase 3 que quedaron afuera (el `n` de los viejos cuenta
  issues; el resumen de un re-apply no nombra lo ya hecho), los menores de la fase 1 y `jk done|stats` por categoría.
