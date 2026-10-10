# jira-kanban

Una skill para Claude Code, Codex y Cursor que crea una épica de Jira a partir de lo que se está trabajando y la mantiene
espejada, en los dos sentidos, como un kanban local en `./.jira-kanban/` del proyecto.

Le decís al agente *"creame una épica para esto que estuvimos trabajando"*. El agente arma la épica con sus historias,
tareas y subtareas, te muestra una vista previa navegable con estética de Jira, espera tu "sí" y crea todo en Jira. Después
escribe un folder por issue en el proyecto. Con `pull` traés lo que cambió en Jira; con `push` mandás a Jira lo que
cambiaste localmente.

## Instalación

```bash
git clone git@github.com:josefigueredo/skill-kanban-jira.git jira-kanban
cd jira-kanban && ./install.sh
```

Por defecto instala `jira-standup` (reportes de solo lectura) y deja `jk` en `~/.local/bin/jk`; con
`./install.sh --with-write` suma `jira-kanban` (crear y sincronizar épicas). Volver a correrlo nunca quita una skill
ya instalada. Sigue el
mismo layout que WayOfWork: `~/.agents/skills/jira-kanban` apunta a este repo, `~/.agents/skills/jira-standup` a su
carpeta `standup/`, y `~/.claude/skills/<skill>`, `~/.codex/skills/<skill>` y `~/.cursor/skills/<skill>` apuntan a
`../../.agents/skills/<skill>`. Cursor tiene su propio enlace porque `~/.cursor/skills` sólo contenía enlaces explícitos
(medido el 2026-10-09). Repetirlo es seguro; nunca reemplaza un directorio real.

Requisitos: `python3` (3.9 o más; sólo biblioteca estándar) y credenciales de Jira Cloud.

### Credenciales

Se buscan en este orden, igual que WayOfWork:

1. Variables de entorno: `IC_JIRA_BASE_URL`, `IC_JIRA_USER_EMAIL`, `IC_JIRA_API_TOKEN` (o `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`).
2. `./.env.local` del proyecto.
3. `./.spec-kit/.env` del proyecto.

## Comandos

Todos aceptan `--project DIR` (por defecto, el directorio actual). **Ninguno escribe en Jira sin `--apply`**, y el
`--apply` lo corrés vos: en Claude Code un hook se lo bloquea al agente, que te pasa el comando listo. Cada escritura
queda en `./.jira-kanban/jira-writes.jsonl` (hora, comando, issue y cambio).

| Comando | Qué hace |
|---|---|
| `jk create --spec spec.json [--html vista.html]` | Vista previa de lo que crearía; con `--html`, la página navegable |
| `jk create --spec spec.json --jira-project KEY --apply [--assign-open \| --no-assign-open]` | Crea en Jira (primero los padres), pasa a Done lo terminado y escribe el kanban local. Si Jira rechaza un issue a mitad de camino, conserva lo creado y el mismo comando retoma sin duplicar. Si sólo falla un cambio de estado, sigue con los demás, escribe el kanban y lo informa: se termina con `push`, nunca repitiendo `create` |
| `jk pull EPIC` | Trae la épica y sus hijos de Jira al kanban local |
| `jk push EPIC [--apply] [--assign-open \| --no-assign-open]` | Manda a Jira los cambios locales: estado, título, descripción, subtareas nuevas |
| `jk show EPIC` | Lista el kanban local como árbol |
| `jk board EPIC` | Agrupa el kanban local: Bloqueado · Por hacer · En progreso · Hecho |
| `jk who "NOMBRE" [--jira-project KEY] [--json]` | Busca una persona en Jira por nombre, email o accountId (solo lectura): `unique`, `ambiguous` o `none` |
| `jk assign KEY "PERSONA" [--tree] [--apply]` | Asigna un issue (con `--tree`, todo lo que cuelga de él) a una persona |
| `jk done` · `next` · `blocked` · `load` · `stats` | Reportes de solo lectura (ver «Reportes»): qué hice, qué puedo hacer, qué me bloquea, carga y métricas |

`jk` queda en `~/.local/bin/jk` (lo crea `install.sh`; hace falta `~/.local/bin` en el PATH).

## El spec

El agente lo arma desde la conversación. Un ejemplo con una historia, una tarea y una subtarea:

```json
{
  "epic": {"summary": "Login corporativo en el back office", "description": "Objetivo, problema y alcance"},
  "items": [
    {"type": "story", "area": "FE", "summary": "Página de login",
     "user_story": "Como analista quiero ingresar con mi cuenta corporativa para no gestionar credenciales aparte",
     "acceptance": ["AC1: Dado un analista sin sesión Cuando abre el back office Entonces ve el login"],
     "done": true, "evidence": ["1d93d8d"],
     "subtasks": [{"summary": "Formulario con SSO"}]},
    {"type": "task", "area": "DEVOPS", "summary": "Job de CI con los e2e del login", "description": "…"}
  ]
}
```

- **Historia o tarea:** `story` sólo si alguien se beneficia ("Como … quiero … para …"); si no, `task`. Las dos cuelgan
  de la épica como hermanas, igual que en Jira; las subtareas cuelgan de cualquiera. No hay un cuarto nivel.
- **Área:** se convierte en el prefijo del título, `[FE] Página de login`. No se usan componentes, labels ni story points.
- **`done`:** el trabajo ya está terminado (hecho, verificado, mergeado). Ver la asignación, abajo.
- **`evidence`:** obligatoria con `done`. Commits (alcanzables desde la branch principal del remoto, o sea mergeados y
  pusheados), una branch de `origin` o URLs (un PR, un deploy). jk los resuelve antes de escribir, también en seco, y los
  agrega a la descripción como permalinks bajo `Evidencia:`. Si alguno no resuelve, `create` no escribe nada. Una
  subtarea que hereda el `done` hereda también la evidencia.
- **`started`:** lo estás haciendo ahora. Se crea y pasa a un estado de la categoría *En progreso* (evita los
  bloqueados y los de revisión); sus subtareas no lo heredan. No puede ir junto con `done`.

## Asignación

- Lo que está **completo** (`"done": true`) o **en curso** (`"started": true`) se te asigna sin preguntar: lo hiciste
  o lo estás haciendo vos. Las subtareas heredan el `done` de
  su padre salvo que digan otra cosa, y la épica está completa sólo si todo lo que cuelga de ella lo está.
- Lo que **no** está completo necesita tu respuesta: `--assign-open` (asignármelas) o `--no-assign-open` (sin asignar).
  Sin ella, `--apply` se niega antes de llamar a Jira. La skill te lo pregunta.

### A otra persona

`jk` asigna por defecto a quien lo corre, pero el spec puede nombrar a otra persona con `"assignee"` (un nombre, un email o
un accountId) en la épica, un ítem o una subtarea; las subtareas heredan la de su ítem. Una persona nombrada gana sobre
`done`, `started` y `--assign-open`, y no cuenta como "pendiente de decidir".

- `jk create` la busca **mientras planifica**, también en el dry run, y se niega antes de escribir si el nombre no coincide
  con nadie o coincide con varios. Lista los candidatos con su email; **nunca elige entre dos personas**.
- La búsqueda de Jira solo reconoce el comienzo de cada palabra, así que "Matiaz" no encuentra a "Matías". `jk` consulta
  cada palabra del nombre por separado, ignora tildes y mayúsculas y tolera una letra de diferencia. Una coincidencia
  exacta del nombre completo gana sobre nombres más largos que lo contienen.
- Solo busca entre quienes se pueden asignar en el proyecto (`--jira-project`, o el de la clave en `assign`), activos y
  que no sean bots.
- Para reasignar lo que ya existe: `jk assign PLATE-639 "Nombre Apellido" --tree` (dry run) y después lo mismo con
  `--apply`. Una asignación rechazada se informa y no frena a las demás.

## Vista previa

`jk create --spec spec.json --html vista.html` genera una sola página, sin red ni recursos externos, con la estructura de
una pantalla de issue de Jira: árbol a la izquierda, breadcrumb, descripción con criterios de aceptación, tabla de hijos,
estado y panel de detalles con el responsable. Las claves son `NUEVO-1…n` en el orden de creación y la navegación es por
`#hash` (el botón Atrás funciona). Muestra sólo lo que va a ejecutar esa pasada.

## Reportes (solo lectura)

Responden en tablas y árboles, leyendo Jira en vivo (el kanban local no guarda fechas ni asignados). La skill hermana
`jira-standup` (carpeta `standup/`) los usa; el agente traduce "ayer" o "la semana pasada" a fechas `YYYY-MM-DD`.

| Comando | Responde |
|---|---|
| `jk done --since D [--until D]` | Qué hice: árbol Épica → Historia/Tarea → Subtarea, con totales |
| `jk next [--until D]` | Qué puedo hacer: para hacer ya (por prioridad y vencimiento), lo que vence, lo que está sin dueño en mis épicas |
| `jk blocked` | Dónde estoy bloqueado: por link "is blocked by", por Flagged o por estado bloqueado |
| `jk load --person "X" [--weeks N]` | Carga de otra persona, en números medidos, al lado de la mía |
| `jk stats [--weeks N]` | Velocidad (issues cerrados por semana), lead time, edad del WIP, cumplimiento de fechas, mezcla |

Todos aceptan `--person "NOMBRE"` (si el nombre es ambiguo lista a los candidatos y no elige), `--jira-project KEY` y
`--json`. PLATE no tiene story points, así que la velocidad se mide en issues; `jk load` solo da un veredicto si
`wip_limit` está en `./.jira-kanban/conventions.json`. Límites: Jira guarda solo el último cambio de estado (un issue
que pasó por «en curso» y luego a Done figura con la fecha de Done) y «hecho» significa asignado a la persona.

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
.jira-kanban/<EPIC>/epic.md
.jira-kanban/<EPIC>/stories/<KEY>/story.md
.jira-kanban/<EPIC>/tasks/<KEY>/task.md
.jira-kanban/<EPIC>/<stories|tasks>/<KEY>/subtasks/<KEY>/subtask.md
.jira-kanban/<EPIC>/.sync.json        # lo último que se leyó de Jira y cuándo; push compara contra esto
```

Cada `.md` tiene un front matter (`key`, `kind`, `issuetype`, `status`, `category`, `blocked`, `parent`, `url`),
el título como `# …` y la descripción debajo.

- **Editar:** cambiá `status`, el `# título` o el cuerpo y corré `jk push EPIC`. Si el mismo campo también cambió en Jira,
  push lo informa como **conflicto** y no lo pisa: `jk pull`, volvé a aplicar tu cambio y repetí el push.
- **Subtarea nueva:** creá `…/subtasks/_new-<algo>/subtask.md` con un `# título`; push la crea bajo el padre del folder y
  le pone su clave.
- **Versionarlo o no** queda a criterio de cada proyecto. Si se versiona, `jira-writes.jsonl` (evidencia local, trae
  el accountId) y `.create-progress-*.json` (transitorio) van al `.gitignore`.

## Estados y bloqueo

Los nombres de las columnas y de los estados cambian entre tableros y se traducen (en PLATE conviven `PROCESANDO`, `Review`,
`Blocked` y `Done`). Por eso `pull` guarda la **categoría** fija que Jira le da a todo estado (`todo`, `in_progress`, `done`)
y `jk board` agrupa por ella, nunca por el nombre. **Bloqueado** no es una categoría: un issue lo está si su estado figura
en `blocked_statuses` o si tiene marcado el campo *Flagged*. Un issue en *Hecho* sigue contando como hecho aunque tenga
la bandera.

## Convenciones

`conventions.json` no define proyecto: `create` lo pide con `--jira-project` o con `"project"` en el
`./.jira-kanban/conventions.json` del proyecto, y `pull`/`push` lo toman de la key de la épica. Define los tipos de issue, las áreas, las prioridades, `blocked_statuses` y si se
asigna. Un proyecto puede pisar cualquier clave con su propio `./.jira-kanban/conventions.json`.

## Desarrollo

```bash
python3 -m unittest discover -s tests          # con Jira falso: nunca sale a la red
/usr/bin/python3 -m unittest discover -s tests # verifica compatibilidad con 3.9
```

| Módulo | Responsabilidad |
|---|---|
| `jkan/evidence.py` | Resuelve la evidencia (commits, branches, URLs) a permalinks |
| `jkan/spec.py` | Valida el spec y arma el plan de creación en orden |
| `jkan/sync.py` | `create`, `pull`, `push`, `board` y la regla de asignación |
| `jkan/kanban.py` | Árbol local y formato de cada `.md` |
| `jkan/preview.py` | La vista previa HTML |
| `jkan/jira.py` | Cliente de Jira Cloud (v2 para issues, v3 para búsqueda y transiciones) |
| `jkan/config.py` | Credenciales y convenciones |
| `jkan/cli.py` | La línea de comandos |
