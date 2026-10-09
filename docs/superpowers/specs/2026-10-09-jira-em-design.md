# jira-em: seguimiento de equipo y escritura guardada para EM y Sr EM

Fecha: 2026-10-09 · Estado: borrador para revisión · Repo: `Harness/jira-kanban`

## Para qué

Darle a los Engineering Managers (EM) y Sr EM de la compañía, desde su agente y su terminal:

1. **Seguimiento de uno o varios boards** de tipos distintos (flujo continuo, scrum, help desk): cuánto hay en cada
   estado, qué está estancado, qué está bloqueado, cómo fluye el trabajo y qué se entregó en un período.
2. **Operación en lote** (mover de estado, reasignar, comentar) con garantías que no dependan de que quien la usa
   preste el 100% de atención.

Éxito: un EM distraído no puede escribir algo equivocado en Jira por una mala lectura del modelo o un "sí" apurado, y
lo determinístico vive en scripts, no en tokens. Los `SKILL.md` son cortos y sin ambigüedad.

Alcance acordado: **seguimiento primero (solo lectura), escritura segura después y aparte**.

## Qué se midió y qué es inferencia

Medido el 2026-10-09 con las credenciales de la persona que escribe la spec, solo con GET, sobre el Jira real.

| Hecho | Medida |
|---|---|
| Proyectos visibles | 253: 124 `software` (87 team-managed, 37 classic), 79 `business`, 43 `service_desk` (JSM), 7 `product_discovery`. Team-managed: 186 de 253 (73%) |
| Boards de la API Agile | 50: 42 `simple`, 5 `kanban`, 3 `scrum`. Los help desk usan colas, no boards |
| El workflow depende del tipo de issue | `UA`: Historia con 4 estados, Tarea con 6 y otros nombres. `PDM`: 18 tipos con 4, 8 y 11 estados |
| Nombres distintos en la categoría *done* de toda la instancia | 92 (`done` ×114, `cancelado` ×87, `finalizado` ×62, `listo` ×41, `resuelto` ×27, `completado` ×5) |
| Proyectos con más de un estado tipo "hecho" | 62 (por ejemplo `Finalizado` + `Resuelto` en `BDBDESK`, `BPDCD`, `CAN`, `FFICSOP`, `FIELDESK`) |
| Estados con nombre de "hecho" fuera de la categoría *done* | 31 en 29 proyectos (`Done` en "en curso" en `GDNC` y `OYP`; `Finalizado` en "por hacer" en `CDMB2`) |
| Proyectos con más de un estado en la categoría *done* | 134, casi siempre `Cancelado` + `Done`: la categoría mezcla entregado y descartado |
| Nombres parecidos con otro significado | `Finalizado sin completar`, `Finalizado con error`, `Listo para entrega`, `Ready to deploy` (×11 en *done*) |
| Mismo nombre con ids distintos dentro de un proyecto | 4 (`en ejecucion`, `en analisis`), ninguno de "hecho" |
| Estados de bloqueo y espera | Caen en la categoría "en curso": `PLATE` `Blocked`, `UA` `ON HOLD`, `CDSP` `Esperando por el cliente` |
| SLA | 0 de 43 service desks con datos en `Time to resolution` (42 sin datos, 1 error de JQL); `request/CDSP-2327/sla` devolvió lista vacía. Hay campos de SLA propios (`DG-SLA-GENERAL`, `DPO-SLA`) |
| Equipo | `assignee in membersOf("team")` funciona; el grupo tiene 7 miembros |
| Transiciones | `UA-438` ofrece **dos** transiciones a "In Progress" (ids 21 y 3). `CDSP-2327` solo ofrece `En curso` y `Finalizada` (no global). En `PLATE`, `UA` y `CDSP` ninguna transición de la muestra exigía campos (`PDM` no tenía issue abierto) |
| `jk` hoy | Acepta **como máximo un** proyecto (`--jira-project`; sin él no filtra por proyecto, `jkan/queries.py:24-29`), no usa `/rest/agile` ni `/rest/servicedeskapi`, elige transiciones por **nombre** (`jkan/jira.py:208-216`) y escribe su bitácora en `./.jira-kanban/` del directorio actual (`jkan/journal.py:24`) |
| Distribución | Cinco repos independientes en `josefigueredo`; se instalan con `git clone` y `./install.sh` (symlinks), solo biblioteca estándar. `arq-review/arqlib/jira.py` es un segundo cliente de Jira que ya divergió del de `jk` |

Inferencia, a verificar antes de depender de ella:

- `statusCategoryChangedDate` cambia solo cuando cambia la **categoría**, y `updated` se reinicia con cualquier edición,
  comentarios incluidos. Por eso "estancado" es una aproximación.
- El `!` de Claude Code, Cursor y Codex puede no entregar una terminal interactiva al comando (se prueba al empezar la
  fase 3).
- Los fixtures de las pruebas se arman con las formas de esta tabla, sin datos de personas.

## Decisiones

**1. Un repo, un `jk`.** Las cuatro skills viven en este repo (`jira-kanban` hoy). El paquete `jkan/` es el núcleo
compartido, así que **no hace falta copiar un `jiracore`** dentro de él. `jk` se instala en `~/.local/bin/jk` (como
`arq`) y ninguna skill llama a la ruta de otra. Descartado: un `jiracore` copiado en cada repo (agrega un origen que
vigilar sin necesidad adentro de este repo) y mover `queries/stats/standup/render` al núcleo (`sync.py` no importa
ninguno, son el código que más cambia —6 de 12 commits sin publicar son de reportes— y contienen política de equipo).
Queda para después: `arq-review` y `WayOfWork` siguen con su cliente; si se unifican, ahí sí corresponde una copia con
manifiesto de hash.

**2. Cuatro skills, separadas por riesgo y por sujeto.**

| Skill | Sujeto | Escribe en Jira | Instala |
|---|---|---|---|
| `jira-standup` | *yo* | No | Por defecto |
| `jira-em` | *mi equipo, mis boards, mi view* | No | Por defecto |
| `jira-kanban` | épicas desde una sesión | Sí, con `--apply` | `--with-write` |
| `jira-em-ops` | operaciones en lote | Sí, vía `jk apply` | `--with-write` |

**3. La fuente de verdad de un estado es un rol confirmado por una persona**, no la categoría de Jira (mal puesta en 29
proyectos) ni el nombre.

**4. Un solo verbo escribe en las operaciones en lote: `jk apply`.** Todo lo demás planifica.

## Estructura de código e instalación

```
jkan/
  core/      jira (cliente), config, journal, people
  reports/   window, queries, standup, stats, render, team  (lectura)
  write/     sync, spec, description, evidence, kanban, template, preview, plan, apply  (escritura)
  profile/   board setup, roles, views
  cli.py     parte en un módulo de comandos por skill
```

- Regla verificada por test: **`reports/` y `profile/` no importan `write/`**. La skill de lectura no puede escribir por
  construcción.
- `install.sh`: instala `~/.local/bin/jk` y los symlinks de las skills elegidas. Por defecto `jira-standup` y `jira-em`;
  `--with-write` suma `jira-kanban` y `jira-em-ops`. Repetirlo es seguro y nunca reemplaza un archivo real, igual que
  hoy. Soporta Claude Code, Codex y Cursor (hoy Cursor necesita su propio enlace).
- Los comandos `jk create|push|assign --apply` conservan su nombre, así que `git-guardrails.sh` y `AGENTS.md` siguen
  valiendo. Se suma `jk apply` al hook en la fase 4.
- Python 3.9 o más, solo biblioteca estándar.

## Perfiles de board y roles

Un **perfil** vive en `~/.config/jk/profiles/<KEY>.json` (a nivel usuario: el EM no trabaja dentro de un repo y mira
varios proyectos).

Seis roles, conjunto cerrado: `todo`, `active`, `blocked`, `waiting` (frenado por un tercero), `delivered`, `dropped`
(cancelado, rechazado, no aplica). El mapa es **muchos a uno por id de estado**: `Finalizado` y `Resuelto` pueden ser
ambos `delivered`.

```json
{
  "project": "UA", "kind": "flow", "confirmed": true, "access": "full", "wip_limit": null,
  "fingerprint": "sha256:…",
  "roles": {
    "todo": [{"id": "10001", "name": "To Do"}],
    "active": [{"id": "10002", "name": "In Progress"}],
    "blocked": [], "waiting": [{"id": "10003", "name": "ON HOLD"}],
    "delivered": [{"id": "10004", "name": "Done"}],
    "dropped": [{"id": "10005", "name": "NOT APPROVED"}]
  },
  "open": []
}
```

`kind` es `flow`, `scrum` o `helpdesk`, y **se declara** (`PEHD` es un proyecto de software que funciona como help desk).
`scrum` se trata como `flow` en esta versión. `access` es `limited` si Jira devolvió 403 en algún recurso.
`fingerprint` es el hash de los ids de estado y detecta workflows cambiados. `open` lista los estados sin decidir.

### Comandos

Solo leen Jira; escriben únicamente el JSON local.

- `jk board setup KEY`: lee estados por grupo de tipos con el mismo workflow, imprime **"lo que entiendo"** (estado, id,
  categoría de Jira, rol propuesto, confianza `alta` o `decidir`) y guarda el borrador. Termina con **código 2** mientras
  `open` no esté vacío. Tolera 403 y lo registra en `access`.
- `jk board set KEY <rol> "<estado>" ["<estado>" …]`: asigna por nombre, resuelto a ids. Un nombre que corresponde a
  más de un id lista los ids y falla; no elige.
- `jk board show KEY` y `jk board check KEY` (compara el `fingerprint` con Jira).
- Nadie edita el JSON a mano.

### Cómo propone

- **`alta`:** el nombre normalizado (sin tildes ni mayúsculas) coincide exactamente con el diccionario inicial **y** la
  categoría de Jira es coherente con el rol. Diccionario inicial: `delivered` = done, finalizado/a, completado/a,
  completo, resuelto/a, cerrado/a, closed, resolved, listo, released; `dropped` = cancelado/a, cancelled, canceled,
  rechazado/a, descartado, discarded, no aplica, not approved; `blocked` = blocked, bloqueado/a. Estados sin nombre en el
  diccionario: categoría *new* → `todo`, *indeterminate* → `active`.
- **`decidir`, siempre:** el nombre trae un calificador (`sin completar`, `con error`, `para entrega`, `pend.`, `por
  tiempo`); el diccionario y la categoría no coinciden (`Done` en "en curso"); un estado de la categoría *done* que no
  está en el diccionario (puede ser entregado o descartado); un estado "en curso" cuyo nombre sugiere espera o bloqueo
  (`ON HOLD`, `Esperando…`).
- El diccionario se valida corriendo `setup` sobre los 253 proyectos (criterio de la fase 1).

### Reglas

1. Los reportes usan **roles, nunca la categoría de Jira**. Un estado sin rol se informa como `estado desconocido: X`,
   sin llamadas extra.
2. "Hecho" y la velocidad cuentan solo `delivered`; `dropped` se muestra aparte.
3. Los reportes corren con un perfil sin confirmar, con una banda arriba que lo dice. Escribir se niega.
4. Los reportes existentes (`jk done|next|blocked|load|stats`) pasan a roles en la fase 1; hoy usan la categoría y no
   cuentan el `Done` mal categorizado de 29 proyectos.

## Views y reportes de equipo

Un **view** vive en `~/.config/jk/views/<nombre>.json`: boards (claves de proyecto) más equipo, que es un grupo de Jira
(`--group`, usado como `assignee in membersOf("…")`) o una lista de personas. Sin equipo se toma a quien tenga asignado
algo en esos boards. Se crea con `jk team setup NOMBRE --boards PLATE,UA --group team`.

Las consultas se arman con los **roles** del perfil como `status in (<ids>)`. Varios boards salen en **una** búsqueda
(`project in (…)`).

| Comando | Responde |
|---|---|
| `jk team status VIEW` | Cantidad por rol (`todo/active/blocked/waiting`) por board y por persona; sin asignar. Con `wip_limit` en el perfil, un veredicto de carga; sin él, solo números |
| `jk team stalled VIEW [--days N]` | Lo `active` sin moverse hace N días (por defecto 7), con dos columnas: días en la categoría y días desde la última edición |
| `jk team blocked VIEW` | `blocked` y `waiting` por separado, con dueño, antigüedad, links "is blocked by" y flag |
| `jk team flow VIEW --weeks N` | Entregas por semana, lead time (p50 y p85), edad del WIP; solo `delivered` |
| `jk team digest VIEW --since D` | Entregado, descartado, nuevo, bloqueado y estancado del período |
| `jk team desk VIEW` | Para boards `helpdesk`: edad en tramos, sin asignar, esperando al cliente, tiempo de resolución. **Sin SLA** |
| `jk team rollup V1 V2 …` | Para el Sr EM: una fila por view con abiertos, bloqueados, estancados, entregados y p85 |

Para un 1:1 se reusan `jk done|next|blocked --person "X"` con `--view VIEW`.

### Contrato de salida

1. Primera línea fija: view, boards, ventana de fechas y estado del perfil.
2. Cada número lleva su `n`; los `n` chicos se marcan.
3. Máximo 20 filas por tabla con `… y N más`; `--all` lo levanta. Si una búsqueda llega a su tope de 1000 issues, lo
   dice. Nunca corta en silencio.
4. Última sección fija, **Límites**.
5. `--json` en todos.

## Guardia de escritura

**Operaciones de la versión 1:** mover de estado, reasignar y comentar (texto plano, el mismo para todos los issues del
plan). Fuera de alcance: crear, borrar, editar campos, etiquetas.

**Planificar nunca escribe.** `jk plan move|assign|comment …` resuelve la selección **una vez** y guarda
`~/.local/state/jk/plans/<id>.json` con las claves exactas, el estado de origen (id), la transición de destino (id) y
un hash. `jk apply <id>` aplica exactamente ese archivo; no vuelve a evaluar la consulta.

**Rechazos al planificar (deterministas):**

1. Perfil sin confirmar en cualquier board tocado.
2. Issue fuera de los boards del view.
3. Más de **25 issues** (`--max` sube hasta 200).
4. Destino por **id de estado** del perfil, nunca por nombre. Si un issue ofrece varias transiciones al rol, se saltea
   como `ambiguo` y se listan.
5. Transición con campos obligatorios, o sin camino al destino: se saltea y se informa.
6. Mover a `delivered` o `dropped` exige `--allow-close`; el plan dice cuántos cierres incluye.
7. Persona a asignar: mismas reglas que `jk who`; si es ambigua, no elige.

**Aplicar:**

- Exige **terminal interactiva** y que la persona escriba **`APRUEBO <n>`**, con `n` igual a la cantidad de issues del
  plan. Sin TTY, `apply` se niega e imprime el comando para que lo corra la persona. Lo impone el script, no la
  disciplina del modelo. Una aprobación escrita en el chat no se acepta: el script no puede saber quién la escribió.
- Antes de cada escritura relee el issue; si su estado ya no es el del plan, lo saltea como `cambió`.
- Un fallo no frena a los demás. Al final, tabla por issue y código de salida distinto de cero si hubo alguno. Reaplicar
  es idempotente: saltea lo que ya está en destino.
- Bitácora única `~/.local/state/jk/writes.jsonl` con plan, issue, estado `de` y `a`. `jk plan revert <id>` arma el plan
  inverso; **no garantiza deshacer** (si el workflow no tiene camino de vuelta, lo marca).

## Contrato de las skills

Cada `SKILL.md`: una tabla "el usuario pide → corré esto", pocas reglas y una lista de lo que nunca hace. La lógica vive
en `jk`.

- `jira-standup`: sin `--person` es quien tiene las credenciales. No habla de equipo.
- `jira-em`: si falta el perfil de un board, corre `jk board setup` y se **detiene** en las decisiones abiertas.
- `jira-kanban`: sin cambios de comportamiento.
- `jira-em-ops`: solo `jk plan …`. Para aplicar entrega el comando y espera; **nunca** corre `jk apply`.
- Comunes: mostrar la salida tal cual (ya es Markdown), no inventar umbrales, no imprimir ni pedir credenciales
  (`IC_JIRA_*`), y código de salida 2 significa "falta una decisión humana", no "reintentá".
- Descripciones separadas por **sujeto** (yo / mi equipo). Se revisa con 12 frases reales por skill antes de publicar,
  a mano. Alternativa si no se separan limpio: `--team` dentro de `jira-standup` y una skill menos.

## Pruebas

TDD, `python3 -m unittest discover -s tests` también en `/usr/bin/python3` (3.9), con Jira falso: nunca sale a la red.
Fixtures con las formas medidas: `GDNC` (`Done` mal categorizado), `BDBDESK` (cuatro estados *done*), `FDQ`
(`Finalizado con error`), `UA` (dos transiciones al mismo nombre), `CDSP` (workflow no global), un 403 y una transición
con campo obligatorio. Casos del guardia: estado cambiado entre plan y apply, tope excedido, perfil sin confirmar,
cierre sin `--allow-close`, ejecución sin TTY y `APRUEBO` con un `n` equivocado.

## Fases

| Fase | Contenido | Se considera terminada cuando |
|---|---|---|
| 0. Estructura | Partir `cli.py`; `jk` en el PATH; `install.sh --with-write`; test de imports prohibidos | Los 244 tests actuales siguen verdes, también en 3.9 |
| 1. Perfiles y roles | `jk board setup/set/show/check`; migrar `done`, `next`, `blocked`, `load`, `stats` a roles | `setup` corrido sobre los 253 proyectos, con el porcentaje `alta` vs `decidir` medido; los 29 proyectos mal categorizados dan lo correcto |
| 2. Equipo | Views y los siete reportes | Corridas de solo lectura sobre `PLATE`, `UA`, `PEHD` y `CDSP`, comparadas con Jira |
| 3. Escritura | `jk plan`, `jk apply`, bitácora | La batería de casos y una prueba real en un proyecto de pruebas |
| 4. Cierre | Docs, renombrar el repo, `git-guardrails.sh` y `AGENTS.md` | Tests verdes y cada cita `archivo:línea` de esta spec re-verificada contra el código |

## Riesgos y pendientes

- **Proyecto de pruebas para la fase 3:** hay que elegir uno; no se prueban escrituras en un board real.
- **TTY bajo `!`:** sin verificar; si no hay, la persona corre `apply` en una terminal aparte.
- **SLA:** fuera de la versión 1 hasta confirmar qué desks lo usan.
- **Idioma de las etiquetas:** `AGENTS.md` pide mensajes del CLI en inglés y el README dice que las etiquetas de los
  reportes son en castellano. Se conserva lo que hay.
- **Perfiles compartidos** entre EM que miran el mismo board: no se resuelve acá; evita que cada uno decida distinto qué
  significa "hecho".
- **Nombre del repo:** deja de describir el contenido; se renombra en la fase 4 (GitHub redirige).
- **Scrum y sprints:** 3 de 50 boards y sin API Agile; fuera de la versión 1.
