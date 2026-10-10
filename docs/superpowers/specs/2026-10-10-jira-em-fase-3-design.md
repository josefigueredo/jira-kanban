# jira-em, fase 3: escritura con guarda

Estado: diseño aprobado el 2026-10-10. Concreta y, donde se indica, corrige la sección «Guardia de escritura» de
`2026-10-09-jira-em-design.md`. Lo que esta spec no menciona sigue como está en aquella.

## Objetivo y alcance

Que un EM pueda **mover de estado, reasignar y comentar** varios issues de una vez, sin que un modelo pueda aprobar esa
escritura por su cuenta. Fuera de alcance: crear, borrar, editar campos, etiquetas.

Terminada cuando pasa la batería de casos de la sección «Pruebas» y hay una prueba real en un proyecto sandbox. El
sandbox es el **último paso** de la fase: todo lo demás se construye y prueba contra el Jira falso.

Lo que no cambia: el push y toda escritura a Jira los hace la persona; el modelo nunca corre `jk apply` ni un `--apply`.

## Qué hay hoy (medido en el código)

| Hecho | Dónde |
|---|---|
| `Jira.transition(key, status)` elige la transición por **nombre** del estado destino; el spec exige **id** | `jkan/jira.py:248` |
| No existe una operación de comentar, ni una de leer solo el estado y el asignado de un issue | `jkan/jira.py` |
| Los escritores viejos reciben `apply` y escriben en la misma llamada: `sync.create`, `sync.push`, `sync.assign` | `jkan/sync.py:130`, `:240`, `:326` |
| `--apply` de `create`, `push` y `assign` se declara en el parser | `jkan/cli.py:171`, `:187` |
| La bitácora actual es por proyecto: `./.jira-kanban/jira-writes.jsonl` | `jkan/journal.py:24` |
| El directorio de configuración se resuelve con `$JK_CONFIG_DIR` o `~/.config/jk` | `jkan/board_profile.py:33` |
| Bajo `!` no hay terminal: `test -t 0` dio «no» el 2026-10-10 | medido |

## La guarda (`jkan/guard.py`)

`confirm(n, resumen, comando)` es la única puerta de escritura. Lo usan `jk apply` y los tres `--apply` viejos.

1. **Exige una terminal real.** `stdin`, `stdout` y `stderr` tienen que ser TTY **y** `/dev/tty` tiene que abrirse. Si
   no, **no escribe nada**, imprime el comando exacto para correrlo en otra terminal y sale con código **3**.
2. **Muestra lo que va a pasar** (el `resumen`, armado desde el archivo del plan o del dry run, no desde lo que el
   modelo cuente) y pide escribir `APRUEBO <n>`.
3. **Lee la respuesta de `/dev/tty`**, no de la entrada estándar: `echo "APRUEBO 3" | jk apply …` no sirve.
4. **Un solo intento.** `n` es la cantidad real de escrituras. Cualquier otra respuesta (otro `n`, minúsculas, espacios
   de más) es «no aprobado»: no escribe y sale con código 3.
5. **Sin atajos.** No hay `--yes`, variable de entorno ni archivo de configuración que la saltee.
6. **Para los tests**, `cli.main` recibe un parámetro `confirm=` (como ya recibe `client=` y `today=`). No hay forma de
   llegar a ese reemplazo desde la línea de comandos. El módulo se prueba aparte con un `/dev/tty` simulado.

Límite honesto: la guarda frena lo accidental y lo inducido desde contextos sin terminal (el chat, `!`, la herramienta
Bash del modelo). **No frena a un agente con shell que decida abrir un pseudo-terminal y escribir la aprobación**: nada
dentro del script puede distinguirlo de una persona. Por eso el hook `git-guardrails.sh` suma `jk apply` (fase 4) y las
skills lo prohíben; la guarda es una capa, no la única.

## Plan

`jk plan move|assign|comment VIEW …` **solo lee Jira**, resuelve la selección una vez y guarda
`<state>/plans/<id>.json`, con `<state>` = `$JK_STATE_DIR` o `~/.local/state/jk`.

### Selección

Claves explícitas, filtros o ambas, siempre dentro de los boards del view:

```
jk plan move    VIEW [KEY …] [--unassigned] [--older-than D] [--role R] --to ROLE [--to-status ID] [--allow-close] [--max N]
jk plan assign  VIEW [KEY …] [--unassigned] [--older-than D] [--role R] --person "<nombre>" [--max N]
jk plan comment VIEW [KEY …] [--unassigned] [--older-than D] [--role R] --text "<texto>" [--max N]
```

Los filtros son los de `--list` y salen de `team.list_issues`, sobre los mismos issues abiertos del view; las claves
explícitas se suman. Sin claves ni filtros, el plan se rechaza (no hay «todo»).

### Rechazos al planificar

Deterministas. Un issue que cae en 2, 4 o 5 se **saltea y se informa**; los demás rechazos frenan todo el plan.

| # | Regla | Efecto |
|---|---|---|
| 1 | Perfil sin confirmar en un board tocado | Frena el plan |
| 2 | Issue fuera de los boards del view | Frena el plan |
| 3 | Más de **25** issues (`--max` sube hasta **200**) | Frena el plan |
| 4 | Destino ambiguo: desde el estado actual hay varias transiciones a estados con ese rol | Saltea como `ambiguo` y lista las opciones; `--to-status ID` lo desambigua |
| 5 | La transición exige campos obligatorios, o no hay camino al destino | Saltea y lo informa |
| 6 | Mover a `delivered` o `dropped` sin `--allow-close` | Frena; con el flag, el plan dice cuántos cierres incluye |
| 7 | Persona ambigua o inexistente (mismas reglas que `jk who`: nunca elige) | Frena el plan |
| 8 | Texto de comentario vacío | Frena el plan |

El destino de un `move` se elige por **id de estado del perfil**, nunca por nombre. `--to ROLE` acepta
`todo|active|blocked|waiting|delivered|dropped`.

### Formato del archivo

```json
{
  "version": 1, "id": "<12 hex>", "kind": "move", "view": "plataforma", "created": "2026-10-10T12:00:00Z",
  "options": {"to_role": "active", "allow_close": false},
  "items": [{"key": "PLATE-1", "from": {"id": "13010", "name": "Selected for Development"},
             "to": {"id": "10115", "name": "PROCESANDO", "role": "active"}, "transition": "21"}],
  "skipped": [{"key": "PLATE-2", "why": "ambiguo", "options": ["PROCESANDO", "Review"]}],
  "hash": "<sha256 del cuerpo sin el campo hash>"
}
```

- `assign`: cada item lleva `to` = `{"id", "name"}` de la persona y `from` = quién estaba asignado (o `null`).
- `comment`: el texto va una vez en `options.text`; los items solo llevan la `key`.
- `id` = los primeros 12 caracteres hex del `hash`. El archivo no se edita a mano: `apply` rechaza uno cuyo hash no
  coincide con su contenido o con su nombre. El hash detecta cambios accidentales, **no** autentica; por eso la
  aprobación se pide sobre lo que `apply` muestra del archivo.

## Apply

`jk apply <id>`:

1. Carga el plan, verifica el hash y que el view y los perfiles de sus boards sigan existiendo y confirmados.
2. Pide la aprobación con la guarda: `n` = items del plan **sin contar los ya aplicados** según la bitácora.
3. Por cada item, **antes de escribir** relee el issue:
   - `move`: si el id de su estado ≠ `from.id` → `cambió` (saltea); si ya está en `to.id` → `ya estaba` (saltea); si
     la transición guardada ya no existe o ya no lleva a `to.id` → `cambió` (saltea). Si no, `POST` de esa transición
     **por id**.
   - `assign`: si ya está asignado a esa persona → `ya estaba`.
   - `comment`: se publica una vez por plan e issue; la idempotencia sale de la bitácora.
4. Un fallo no frena a los demás. Al final imprime la tabla por issue (`aplicado`, `ya estaba`, `cambió`, `error`).

Código de salida: **0** todo aplicado o ya en destino; **1** al menos uno `cambió` o con error; **2** no se pudo (Jira,
disco); **3** hace falta la terminal o no se aprobó. Reaplicar es idempotente: saltea lo que la bitácora ya marca `ok`
para ese plan.

### Bitácora global

`<state>/writes.jsonl`, una línea por escritura: `ts`, `tool`, `command`, `plan`, `key`, `action`
(`move|assign|comment`), `de`, `a`, `result` (`ok` o `error: …`). Los comandos viejos siguen con su bitácora por
proyecto (`jkan/journal.py:24`); unificarlas es de la fase 4.

### Revertir

`jk plan revert <id>` arma el plan inverso desde la bitácora: `move` vuelve al `de` (por id, con las mismas
verificaciones), `assign` vuelve al asignado anterior. **No garantiza deshacer**: si el workflow no tiene camino de
vuelta, o el issue cambió, lo marca. Los comentarios no se revierten y el plan lo dice. El plan inverso se aplica con
`jk apply` y pide `APRUEBO` como cualquier otro.

## Cambios en lo existente

- `Jira.transition_by_id(key, transition_id)` y `Jira.transitions(key)` (lista con `id` y `to`); `Jira.add_comment(key,
  text)` (cuerpo de texto plano). Todos pasan por la bitácora de `Jira`.
- `Jira.get` **no** trae el id del estado ni el asignado (`jkan/jira.py:110-120`; sí los traen `search` y su `_report_issue`). Se agrega `Jira.snapshot(key)` → `{"status_id", "status", "assignee"}`, que es lo que `apply` relee antes de cada escritura.
- `cli.main(argv, client=…, today=…, confirm=…)`.

## Guarda en los comandos viejos

`jk create`, `jk push` y `jk assign` con `--apply` pasan por `guard.confirm`. El dry run ya calcula lo necesario, así
que con `--apply` se corre **primero ese dry run, en silencio**, y recién después se pide la aprobación:

| Comando | `n` |
|---|---|
| `jk create --apply` | issues a crear (`len(result["ops"])`) |
| `jk push --apply` | cambios más issues nuevos (`len(result["changes"]) + len(result["new"])`) |
| `jk assign --apply` | issues a asignar (`len(result["issues"])`) |

Sin `--apply` no cambia nada. Con `--apply` y sin terminal, el comando se niega, imprime el comando y sale con 3.
**Consecuencia asumida:** dejan de funcionar desde `!`; se corren en una terminal aparte, igual que `jk apply`.

## Skill `jira-em-ops`

Se instala solo con `--with-write`. Descripción por sujeto: el equipo del EM, con escritura. Contiene una tabla «el
usuario pide → corré esto» solo con `jk plan …`, y reglas: para aplicar entrega el comando `jk apply <id>` y **espera**;
**nunca** corre `jk apply` ni los `--apply` viejos; no imprime ni pide credenciales; el código 3
significa «falta una persona», no «reintentá». Se prueba a mano con 12 frases reales antes de publicar.

## Pruebas

TDD, en `python3` y `/usr/bin/python3` (3.9), con Jira falso. Casos obligatorios:

- **Guarda:** sin TTY se niega y no escribe; `APRUEBO` con `n` equivocado, en minúsculas o con texto extra; `n` correcto
  aprueba; no hay forma de saltearla desde argumentos ni entorno; lee de `/dev/tty` y no de `stdin`.
- **Plan:** cada rechazo de la tabla; tope de 25 y `--max`; cierre sin `--allow-close`; destino ambiguo con
  `--to-status` y sin él; transición con campo obligatorio; perfil sin confirmar; issue fuera del view; persona
  ambigua; plan que no escribe nada (`FakeJira.writes` vacío).
- **Apply:** estado cambiado entre plan y apply; hash alterado; archivo renombrado; fallo parcial con código 1;
  reaplicar saltea lo hecho; transición guardada que ya no lleva al destino; bitácora con `de` y `a`.
- **Revert:** mover vuelve; asignar vuelve; comentar se marca como no reversible; workflow sin camino de vuelta.
- **Viejos:** `create`, `push` y `assign` con `--apply` sin aprobación no escriben; con aprobación inyectada hacen lo de
  siempre; sin `--apply` no cambia nada.
- **Aceptación real, al final:** en un proyecto sandbox, un plan de cada tipo aplicado desde una terminal aparte, y la
  comprobación de que `jk apply` se niega bajo `!` y desde la herramienta Bash del modelo.

## Riesgos y pendientes

- **Proyecto sandbox:** pendiente; sin él no se cierra la fase. Lo que necesita: proyecto propio y borrable, unos 5 a 10
  issues descartables, workflow tipo PLATE y permiso para editar, transicionar, asignar y comentar.
- **Agente con pseudo-terminal:** ver el límite de la guarda. Mitigación en la fase 4 (hook y `AGENTS.md`).
- **Comentarios no idempotentes en Jira:** la idempotencia depende de la bitácora local; si se borra, reaplicar duplica.
- **Concurrencia:** dos `apply` simultáneos del mismo plan no están protegidos; es una herramienta de una sola persona.
- **Bitácoras separadas** (global y por proyecto) hasta la fase 4.

## Resultados de la fase 3

- **Qué se entregó:** los módulos `guard` y `state` (núcleo), `plan`, `applier` y `plan_cli` (escritura); en `Jira`,
  `transitions`, `transition_by_id`, `add_comment` y `snapshot`; `cli.main(confirm=)` (único punto por donde los tests
  reemplazan la guarda; nada en la línea de comandos llega a ese parámetro); la guarda en `create|push|assign --apply`;
  la skill `jira-em-ops` (solo con `--with-write`).
- **Tests:** 597 en `python3` y en `/usr/bin/python3` (3.9), con Jira falso; ninguna aserción vieja se tocó: los tests de
  `--apply` pasan una aprobación inyectada (`helpers.approve`).
- **Textos de salida en inglés** (AGENTS.md pide los mensajes del CLI en inglés): `applied`, `already there`,
  `already applied`, `changed`, `ambiguous`, `no path`, `required fields`, `error: …`. Reemplazan a los `aplicado`,
  `ya estaba`, `cambió` y `ambiguo` de este spec.
- **Sin bitácora por proyecto:** `plan` y `apply` solo escriben la bitácora global (`writes.jsonl`); unificarlas es de la
  fase 4.
- **`n` de la aprobación es un máximo:** `apply` pide `APRUEBO n` con `n` = issues pendientes según la bitácora; si al
  releer uno resulta `changed` o `already there`, se escriben menos de `n`.
- **Límite conocido:** `jk create --apply` pide la aprobación antes de poder fallar por una decisión `--assign-open`
  pendiente; la persona aprueba y después el comando se niega sin escribir.
- **Prueba real en el proyecto sandbox:** pendiente.
