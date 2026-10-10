# jira-standup: qué hice, qué puedo hacer, dónde estoy bloqueado, y si alguien tiene espacio

Fecha: 2026-10-08 · Estado: borrador para revisión · Repo: `Harness/jira-kanban`

## Para qué

Responder desde la terminal, en tablas y árboles que se leen de un bocado y sin abrir Jira:

1. **Qué hice** hace N días ("ayer", "la semana pasada").
2. **Qué puedo hacer** los próximos N días ("hoy", "la semana que viene").
3. **Dónde estoy bloqueado.**
4. **Si una persona de mi equipo tiene espacio** para asignarle tareas.

Los cuatro, más las métricas de `jk stats`, sirven para mí y para otra persona (`--person`). Es **solo lectura**: asignar sigue siendo `jk assign`
con `--apply`, que corre el usuario.

## Qué se midió y qué es inferencia

Medido en el código (commit `f324e58`):

- El espejo local no sirve para (1) ni (4): `jkan/kanban.py:14` guarda `key, kind, issuetype, status, category, blocked,
  parent, url`, sin fechas ni asignado, a propósito (un `pull` sin cambios deja los archivos idénticos).
- `jkan/jira.py:110-119` (`get`) trae summary, status, category y flagged. No trae `resolutiondate`, `duedate`,
  `assignee`, `priority` ni `issuelinks`.
- El espejo solo tiene las épicas con `jk pull` (hoy PLATE-520, 539, 553, 582, 611).
- `jira-writes.jsonl` registra lo que escribió `jk`, no lo que hizo la persona.
- `PLATE` no tiene story points en su pantalla de edición (`conventions.json`, notes): **no hay estimaciones con
  las que medir capacidad.**

Inferencia (verificar con una consulta real antes de implementar): `statusCategoryChangedDate` se puede usar en JQL
en este Jira, y `issuelinks` trae el tipo "is blocked by".

## Decisión: skill hermana, mismo código

Una skill nueva `jira-standup` en una carpeta propia del repo; los comandos viven en el mismo CLI `jk` y reusan
`jkan/jira.py`, `jkan/config.py` y `jkan/people.py`. No se toca `jira-kanban`: esa skill escribe (con `--apply`) y
esta solo lee, y mezclarlas ensucia el `description` que dispara cada una.

Descartado: extender `jira-kanban` (mezcla lectura y escritura) y una skill con código propio (duplica el cliente).

## Comandos

Todos leen Jira en vivo con JQL (`POST /rest/api/3/search/jql`, ya usado en `jira.py:129` y `:206`). Opciones comunes:
`--person "<nombre|email|accountId>"` (por defecto, quien tiene las credenciales), `--jira-project KEY` (opcional),
`--json`.

| Comando | Pregunta | Selección |
|---|---|---|
| `jk done --since D [--until D]` | 1 | asignado a la persona y `statusCategoryChangedDate` dentro de la ventana |
| `jk next --until D` | 2 | ver abajo |
| `jk blocked` | 3 | asignado a la persona, no Done, y con Flagged, estado en `blocked_statuses` o link "is blocked by" sin resolver |
| `jk stats [--weeks N]` | métricas | throughput, lead time, edad del WIP, cumplimiento de fechas, mezcla de trabajo (ver abajo) |
| `jk load --person X [--weeks N]` | 4 | carga abierta de la persona + lo que cerró en las últimas N semanas |

Las fechas llegan siempre como ISO (`YYYY-MM-DD`). El **agente** traduce "ayer" o "la semana pasada" a fechas en la
zona `America/Argentina/Buenos_Aires` y muestra la ventana que usó. El CLI no entiende lenguaje natural.

### `jk next --until D`

Tres tablas, una por pregunta:

1. **Para hacer ya:** asignados a la persona, categoría no Done, no bloqueados. Orden: prioridad, luego `duedate`.
2. **Vence en la ventana:** `duedate <= D`. Incluye los vencidos, marcados.
3. **Sin dueño en sus épicas:** `assignee is EMPTY` y `parent` en una épica donde la persona tiene issues o es la
   dueña. Sirve para tomar trabajo.

### `jk load --person X`

Jira no da capacidad sin estimaciones (ver arriba), así que `load` muestra **números medidos**, no un veredicto
inventado:

| Métrica | Fuente |
|---|---|
| Abiertos asignados | conteo, categoría no Done |
| En curso (WIP) | conteo, categoría In Progress |
| Bloqueados | mismo criterio que `jk blocked` |
| Vencidos / vencen en la ventana | `duedate` |
| Cerrados por semana, últimas N (por defecto 4) | `statusCategoryChangedDate` con categoría Done |

Si la persona y el usuario aparecen juntos (`--person` más el usuario por defecto), la tabla muestra las dos
columnas lado a lado para comparar. Un veredicto "tiene espacio / no" solo sale si `conventions.json` define
`wip_limit`; sin ese valor, el comando no lo emite y lo dice. Así el umbral lo pone el equipo y no el código.

### `jk stats [--weeks N] [--person X]`

Mis métricas, para mí o para otra persona. Todas salen de campos que Jira ya tiene; ninguna necesita estimaciones.
Con pocos datos son ruido, así que cada una muestra su **n** y las que usan tiempos dan **mediana y p85**, no promedio.

| Métrica | Qué dice | Fuente |
|---|---|---|
| Throughput semanal | Velocidad real: issues cerrados por semana, con tendencia (últimas N semanas) | `statusCategoryChangedDate`, categoría Done |
| Lead time | Días desde que se creó hasta que se cerró | `created` → `resolutiondate` |
| Edad del WIP | Cuánto lleva cada issue en curso sin cambiar; marca los estancados | hoy − `statusCategoryChangedDate`, categoría In Progress |
| Cumplimiento de fechas | % cerrado a tiempo de lo que tenía `duedate` | `resolutiondate` vs `duedate` |
| Mezcla de trabajo | Cerrados por área (`[BE]`, `[AI]`, …) y por tipo (Tarea, Historia, Error) | prefijo del título e `issuetype` |
| Antigüedad del backlog | Abiertos asignados más viejos | `created` |

**No se mide con los campos de hoy:** el *cycle time* real (de "en curso" a Done) necesita el changelog de cada
issue, porque `statusCategoryChangedDate` guarda solo el último cambio. Va como opción posterior
(`expand=changelog`), no en la primera versión. Velocidad en story points tampoco: PLATE no los tiene.

## Formato de salida

- `done`: línea de totales (`7 cerradas · 3 en curso`) y un árbol Épica → Historia/Tarea → Subtarea, con fecha y
  estado. Los padres que no cayeron en la ventana se muestran atenuados para dar contexto.
- `next` y `blocked`: tablas Markdown con `Key · Título · Prioridad · Vence · Estado` (y `Bloqueado por · Estado del
  bloqueador · Dueño del bloqueador` en `blocked`). Un bloqueo solo por Flagged dice "Flagged, sin link".
- Las keys de las tablas llevan la URL del issue (`jira.browse_url`); el árbol va en un bloque de código para que las líneas queden alineadas, así que ahí las keys son texto.
- Cada salida abre con una línea que dice **de quién es, qué ventana y cuándo se consultó**.

## Personas

`--person` pasa por `people.resolve()` (`jkan/people.py`): `unique` sigue; `ambiguous` o `none` lanza `NotResolved`
con la lista de candidatos y **no se elige nunca entre dos**. El agente muestra los candidatos (nombre y email) y
pregunta cuál. Acentos y una letra mal puesta están cubiertos por ese módulo.

Ver el trabajo de otra persona usa los permisos que ya tiene el usuario en Jira; este diseño no los amplía.

## Instalación

`install.sh` hoy enlaza la raíz del repo como `~/.agents/skills/jira-kanban`. Se agrega un segundo enlace
`~/.agents/skills/jira-standup -> <repo>/standup` (más los de `~/.claude/skills` y `~/.codex/skills`), con la misma
regla de nunca reemplazar un directorio real. `standup/SKILL.md` invoca el mismo
`python3 ~/.agents/skills/jira-kanban/jk.py`, así no hay dos ejecutables.

## Errores y límites

- Sin credenciales `IC_JIRA_*`: mismo error que hoy; nunca se imprimen.
- Ventana vacía: tabla con "Nada en esta ventana", no un error.
- `statusCategoryChangedDate` guarda **solo el último cambio**: un issue que pasó a en curso y luego a Done aparece
  con la fecha de Done. La salida lo aclara en una nota.
- "Lo que hizo" significa **asignado a la persona**: si otra persona cerró un issue suyo, igual aparece. Es una
  inferencia y se rotula así.
- "Sus épicas" se define por los issues de la persona y las épicas que ella posee; no cubre épicas donde solo
  participa otra gente.
- Paginación: `jira.py:126` y `:203` usan `maxResults: 100`; los comandos nuevos paginan hasta agotar resultados.

## Pruebas

TDD con el opener falso de `tests/helpers.py`, en Python 3.12 y en `/usr/bin/python3` (3.9). Casos mínimos:

- armado del JQL por comando y por ventana (incluye bordes: `--since` sin `--until`);
- árbol de `done` con padres de contexto;
- orden de `next` (prioridad, luego vencimiento) y que un bloqueado no entre en "Para hacer ya";
- `blocked` con link, con Flagged sin link y con estado bloqueado;
- `load` sin `wip_limit` (sin veredicto) y con él;
- `--person` unique / ambiguous / none, y que ambiguous nunca elige;
- `stats`: mediana y p85 con n pequeño, semana sin cierres (cuenta como 0), sin `duedate` (la métrica se omite y se dice);
- `install.sh` crea los enlaces nuevos y se niega a pisar un directorio real.

## Fuera de alcance

- Escribir en Jira (asignar sigue siendo `jk assign --apply`).
- Historial completo por transición (changelog): se evalúa solo si el "último cambio" resulta insuficiente.
- Estimaciones o story points: PLATE no los tiene (por eso la velocidad se mide en issues por semana).
- Cycle time real desde el changelog: segunda versión.
- Interpretar lenguaje natural dentro del CLI.
- Vista HTML: la salida es de terminal.

## Pendiente de verificar antes de implementar

1. `statusCategoryChangedDate` en JQL contra el Jira real.
2. Que `issuelinks` traiga "is blocked by" en PLATE y que sea el tipo que usa el equipo.
3. Cómo se llama el campo de prioridad en este Jira (`priority`) y si `duedate` se usa en PLATE; si nadie lo carga,
   la tabla "Vence en la ventana" quedará vacía y hay que decirlo.
