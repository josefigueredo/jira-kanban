# jira-team-kit

Una skill para Claude Code, Codex y Cursor que crea una épica de Jira a partir de lo que se está trabajando y la mantiene
espejada, en los dos sentidos, como un kanban local en `./.jira-kanban/` del proyecto.

Le decís al agente *"creame una épica para esto que estuvimos trabajando"*. El agente arma la épica con sus historias,
tareas y subtareas, te muestra una vista previa navegable con estética de Jira, espera tu "sí" y crea todo en Jira. Después
escribe un folder por issue en el proyecto. Con `pull` traés lo que cambió en Jira; con `push` mandás a Jira lo que
cambiaste localmente.

## Instalación

```bash
git clone git@github.com:josefigueredo/jira-team-kit.git jira-kanban
cd jira-kanban && ./install.sh
```

Por defecto instala `jira-standup` (reportes de solo lectura) y deja `jtk` en `~/.local/bin/jtk`; con
`./install.sh --with-write` suma `jira-team-kit` (crear y sincronizar épicas) y `jira-em-ops` (planes de cambios del equipo). Volver a correrlo nunca quita una skill
ya instalada. Sigue el
mismo layout que WayOfWork: `~/.agents/skills/jira-team-kit` apunta a este repo, `~/.agents/skills/jira-standup` a su
carpeta `standup/`, y `~/.claude/skills/<skill>`, `~/.codex/skills/<skill>` y `~/.cursor/skills/<skill>` apuntan a
`../../.agents/skills/<skill>`. Cursor tiene su propio enlace porque `~/.cursor/skills` sólo contenía enlaces explícitos
(medido el 2026-10-09). Repetirlo es seguro; nunca reemplaza un directorio real.

Requisitos: `python3` (3.9 o más; sólo biblioteca estándar) y credenciales de Jira Cloud.

### Credenciales

Se buscan en este orden, igual que WayOfWork:

1. Variables de entorno: `IC_JIRA_BASE_URL`, `IC_JIRA_USER_EMAIL`, `IC_JIRA_API_TOKEN` (o `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`).
2. `./.env.local` del proyecto.
3. `./.spec-kit/.env` del proyecto.

#### Cómo conseguirlas en una instalación nueva

| Variable | Qué es | De dónde sale |
|---|---|---|
| `IC_JIRA_BASE_URL` | La URL de tu sitio de Jira Cloud, sin barra final: `https://tu-empresa.atlassian.net` | Es la de la barra del navegador cuando abrís Jira |
| `IC_JIRA_USER_EMAIL` | El email de tu cuenta de Atlassian | El que usás para entrar a Jira |
| `IC_JIRA_API_TOKEN` | Un token de API tuyo | [Crear un token de API](https://id.atlassian.com/manage-profile/security/api-tokens) → **Create API token** → nombre y vencimiento (de 1 a 365 días) → **Copy to clipboard**. Se muestra una sola vez. [Guía oficial](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/) |

> **Creá el token sin alcance (el botón «Create API token», no «Create API token with scopes»).** `jtk` llama a la URL de
> tu sitio con autenticación básica (email y token). Un token con alcance solo funciona a través de
> `https://api.atlassian.com/ex/jira/{cloudId}`, que `jtk` no usa: con ese token no entra. Atlassian recomienda los
> tokens con alcance por seguridad (medido en su guía el 2026-10-11); como `jtk` todavía no los soporta, usá el clásico y
> guardalo como un secreto.

Dónde ponerlas, a elección:

```bash
# A) Para todos tus proyectos: en ~/.zshrc (o ~/.bashrc), y abrí una terminal nueva
export IC_JIRA_BASE_URL="https://tu-empresa.atlassian.net"
export IC_JIRA_USER_EMAIL="vos@tu-empresa.com"
export IC_JIRA_API_TOKEN="el-token-que-copiaste"
```

```bash
# B) Para un solo proyecto: las mismas tres líneas, sin `export`, en ./.env.local. Que el archivo esté en .gitignore.
IC_JIRA_BASE_URL=https://tu-empresa.atlassian.net
```

Para comprobar que entran sin escribir nada en Jira: `jtk who "tu nombre" --jira-project KEY` (solo lectura). Si el
token vence, `jtk` deja de poder entrar: creá otro en el mismo link y cambiá la variable.

## Frente al MCP de Atlassian

Si en Cursor escribís «jira», te sugiere el [MCP de Atlassian](https://github.com/atlassian/atlassian-mcp-server)
(servidor remoto, OAuth, [herramientas](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/) para
leer, buscar, crear, editar, transicionar y comentar). Se pisan solo en el CRUD básico; el resto es de esta skill:

| | `jira-team-kit` (`jtk`) | MCP de Atlassian |
|---|---|---|
| Escribir en Jira | Dry run por defecto; `--apply` abre una ventana de macOS que solo una persona puede aprobar | Lo hace el agente directo, sin ventana |
| Registro | `./.jira-kanban/jira-writes.jsonl` con cada escritura | Sin registro local |
| Kanban local | Espejo en dos sentidos (`pull` / `push`) | No |
| Forma de los issues | Plantillas (por qué, qué, hecho cuando) y evidencia | La que invente el agente |
| Reportes de equipo | `standup`, `em`, métricas, perfiles de board, planes de cambios | No |
| Costo y acceso | Tu token; no depende de un admin | Créditos de Rovo del pool de la organización y permisos que fija el admin de Atlassian |
| Código | Este repo | El repo oficial trae documentación y manifiestos, no el código del servidor (corre en la nube de Atlassian; revisado el 2026-10-11) |

**Recomendación: no instales el MCP de Atlassian junto a esta skill.** Sus herramientas de escritura se saltean la ventana
de aprobación, y los permisos los controla un admin que puede cambiarlos sin avisarte, así que no sirven como garantía.
Las cuatro skills le dicen al agente que Jira va siempre por `jtk`; eso lo orienta, pero no impide que alguien instale el
MCP a mano. Si lo instalás igual, que sea con permisos de solo lectura. El hook de Claude Code (ver «Segunda capa») cubre los rodeos
de la ventana de `jtk`, pero no bloquea las herramientas de un MCP.

## Comandos

Todos aceptan `--project DIR` (por defecto, el directorio actual). **Ninguno escribe en Jira sin `--apply`**, y el
`--apply` lo corrés vos: en Claude Code un hook se lo bloquea al agente, que te pasa el comando listo. Cada escritura
queda en `./.jira-kanban/jira-writes.jsonl` (hora, comando, issue y cambio).

| Comando | Qué hace |
|---|---|
| `jtk create --spec spec.json [--html vista.html]` | Vista previa de lo que crearía; con `--html`, la página navegable |
| `jtk create --spec spec.json --jira-project KEY --apply [--assign-open \| --no-assign-open]` | Crea en Jira (primero los padres), pasa a Done lo terminado y escribe el kanban local. Si Jira rechaza un issue a mitad de camino, conserva lo creado y el mismo comando retoma sin duplicar. Si sólo falla un cambio de estado, sigue con los demás, escribe el kanban y lo informa: se termina con `push`, nunca repitiendo `create` |
| `jtk pull EPIC` | Trae la épica y sus hijos de Jira al kanban local |
| `jtk push EPIC [--apply] [--assign-open \| --no-assign-open]` | Manda a Jira los cambios locales: estado, título, descripción, subtareas nuevas |
| `jtk show EPIC` | Lista el kanban local como árbol |
| `jtk board EPIC` | Agrupa el kanban local: Bloqueado · Por hacer · En progreso · Hecho |
| `jtk who "NOMBRE" [--jira-project KEY] [--json]` | Busca una persona en Jira por nombre, email o accountId (solo lectura): `unique`, `ambiguous` o `none` |
| `jtk assign KEY "PERSONA" [--tree] [--apply]` | Asigna un issue (con `--tree`, todo lo que cuelga de él) a una persona |
| `jtk done` · `next` · `blocked` · `load` · `stats` | Reportes de solo lectura (ver «Reportes»): qué hice, qué puedo hacer, qué me bloquea, carga y métricas |

`jtk` queda en `~/.local/bin/jtk` (lo crea `install.sh`; hace falta `~/.local/bin` en el PATH).

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
  pusheados), una branch de `origin` o URLs (un PR, un deploy). jtk los resuelve antes de escribir, también en seco, y los
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

`jtk` asigna por defecto a quien lo corre, pero el spec puede nombrar a otra persona con `"assignee"` (un nombre, un email o
un accountId) en la épica, un ítem o una subtarea; las subtareas heredan la de su ítem. Una persona nombrada gana sobre
`done`, `started` y `--assign-open`, y no cuenta como "pendiente de decidir".

- `jtk create` la busca **mientras planifica**, también en el dry run, y se niega antes de escribir si el nombre no coincide
  con nadie o coincide con varios. Lista los candidatos con su email; **nunca elige entre dos personas**.
- La búsqueda de Jira solo reconoce el comienzo de cada palabra, así que "Matiaz" no encuentra a "Matías". `jtk` consulta
  cada palabra del nombre por separado, ignora tildes y mayúsculas y tolera una letra de diferencia. Una coincidencia
  exacta del nombre completo gana sobre nombres más largos que lo contienen.
- Solo busca entre quienes se pueden asignar en el proyecto (`--jira-project`, o el de la clave en `assign`), activos y
  que no sean bots.
- Para reasignar lo que ya existe: `jtk assign PLATE-639 "Nombre Apellido" --tree` (dry run) y después lo mismo con
  `--apply`. Una asignación rechazada se informa y no frena a las demás.

## Vista previa

`jtk create --spec spec.json --html vista.html` genera una sola página, sin red ni recursos externos, con la estructura de
una pantalla de issue de Jira: árbol a la izquierda, breadcrumb, descripción con criterios de aceptación, tabla de hijos,
estado y panel de detalles con el responsable. Las claves son `NUEVO-1…n` en el orden de creación y la navegación es por
`#hash` (el botón Atrás funciona). Muestra sólo lo que va a ejecutar esa pasada.

## Reportes (solo lectura)

Responden en tablas y árboles, leyendo Jira en vivo (el kanban local no guarda fechas ni asignados). La skill hermana
`jira-standup` (carpeta `standup/`) los usa; el agente traduce "ayer" o "la semana pasada" a un nombre de ventana (`--when yesterday`, `--when last-week`; también `today`,
`this-week`, `this-month`, `last-month` y, para `next`, `next-week`) y la CLI hace el calendario: semanas de lunes a domingo, en la
zona del equipo. Para otro rango, `--since` y `--until` en `YYYY-MM-DD`.

| Comando | Responde |
|---|---|
| `jtk done --when W` o `--since D [--until D]` | Qué hice: árbol Épica → Historia/Tarea → Subtarea, con totales |
| `jtk next [--when W \| --until D]` | Qué puedo hacer: para hacer ya (por prioridad y vencimiento), lo que vence, lo que está sin dueño en mis épicas |
| `jtk blocked` | Dónde estoy bloqueado: por link "is blocked by", por Flagged o por estado bloqueado |
| `jtk load --person "X" [--weeks N]` | Carga de otra persona, en números medidos, al lado de la mía |
| `jtk stats [--weeks N]` | Velocidad (issues cerrados por semana), lead time, edad del WIP, cumplimiento de fechas, mezcla |

Todos aceptan `--person "NOMBRE"` (si el nombre es ambiguo lista a los candidatos y no elige), `--jira-project KEY` y
`--json`. PLATE no tiene story points, así que la velocidad se mide en issues; `jtk load` solo da un veredicto si
`wip_limit` está en `./.jira-kanban/conventions.json`. Límites: Jira guarda solo el último cambio de estado (un issue
que pasó por «en curso» y luego a Done figura con la fecha de Done) y «hecho» significa asignado a la persona.

## Reportes de equipo

Para quien sigue varios boards y un equipo (EM, Sr EM). Primero se guarda un **view**: los boards y el equipo.
Cada board tiene que tener su perfil (`jtk board setup KEY`); sin él, `jtk team` se niega y dice cuál falta. Con el perfil
sin confirmar corre y lo avisa en la primera línea.

| Comando | Responde |
|---|---|
| `jtk team setup NOMBRE --boards PLATE,UA --group team` | Guarda un view. El equipo es un grupo de Jira (`--group`) o personas (`--people "Ana Gómez" …`); sin equipo, todo lo asignado |
| `jtk team show NOMBRE` · `jtk team list` | Ver un view y el estado de los perfiles de sus boards · listar los views |
| `jtk team status VIEW` | Trabajo abierto por rol, por board y por persona; lo que nadie tiene. Con límite de WIP (`jtk board limit KEY N`), un veredicto de carga |
| `jtk team stalled VIEW [--days N]` | Lo `active` que lleva N días o más sin cambiar de categoría, con los días desde la última edición |
| `jtk team blocked VIEW` | Bloqueado (rol, flag o link) y, aparte, lo que espera a un tercero |
| `jtk team flow VIEW [--weeks N]` | Entregas por semana, lead time (mediana y p85, con su n) y edad de lo que está en curso |
| `jtk team digest VIEW --when W` o `--since D [--until D]` | Entregado, descartado y nuevo del período, más lo bloqueado y estancado de hoy |
| `jtk team desk VIEW [--weeks N]` | Boards `helpdesk`: antigüedad de lo abierto, sin asignar, esperando y tiempo de resolución. Sin SLA |
| `jtk team rollup VIEW VIEW …` | Una fila por view: abiertos, bloqueados, estancados, entregados y lead time p85 |

`status` y `desk` aceptan además `--list`: lista los issues que el reporte contó, del más viejo al más nuevo, para pasar de «7 sin asignar» a cuáles son. Se acota con `--unassigned`, `--older-than DÍAS` y `--role todo|active|blocked|waiting|none` (solo junto a `--list`). En `desk`, `--older-than` no cuenta lo que espera a un tercero, igual que los tramos de antigüedad.

Todos aceptan `--json` y `--all`. Cada reporte abre con el view, los boards, el equipo, la ventana y el estado de los
perfiles; muestra el `n` de cada número; corta las tablas en 20 filas con un `… y N más`; avisa si la búsqueda llegó a su
tope de 1000 issues; y cierra con **Límites**. Para un 1:1, `jtk done|next|blocked --person "X" --view VIEW` mira a una
persona dentro de los boards del view.

### Cambiar varios issues a la vez (con guarda)

Sirve para pasar de «7 sin asignar» a «asignados». Es en dos pasos, y el segundo **solo lo hace una persona**:

| Comando | Qué hace |
|---|---|
| `jtk plan move VIEW [KEY …] --to ROL` | Arma un plan para mover issues al estado que cumple ese rol. Solo lee Jira y guarda un archivo con las claves, el estado de origen, el de destino y la transición |
| `jtk plan assign VIEW [KEY …] --person "Ana"` | Plan para reasignar. La persona nunca se adivina: si hay dos, lista las dos |
| `jtk plan comment VIEW [KEY …] --text "…"` | Plan para dejar el mismo comentario |
| `jtk plan revert ID` | Plan inverso de uno aplicado; no garantiza deshacer y lo dice |
| `jtk apply ID` | Aplica **exactamente** ese plan. Abre una ventana con el detalle y dos botones, **Cancelar** y **Apruebo <n>**; sin terminal y sin ventana, no escribe |

Las claves pueden ir solas o combinadas con `--unassigned`, `--older-than DÍAS` y `--role ROL` (los mismos filtros que `--list`). Un plan lleva hasta 25 issues (`--max`, hasta 200); mover a `delivered` o `dropped` exige `--allow-close`.

**La aprobación es de una persona, con un clic.** En macOS, `jtk apply` y los `--apply` de `create`, `push` y `assign`
abren una ventana nativa con el detalle: una fila por issue (clave, título y qué cambia), lo que quedó afuera y dos botones,
**Cancelar** (el predeterminado; también Escape) y **Apruebo <n>**, que solo responde a un clic: Return no aprueba. Si cancelás,
la cerrás o pasan 100 s, no se escribe nada y el comando sale con código 3. El detalle sale del plan guardado, no de lo que cuente
un agente. Si corrés `jtk apply` en una terminal real, sigue pidiendo escribir `APRUEBO <n>` ahí. Sin terminal y sin ventana
(no es macOS, `ssh`, sin sesión gráfica), no escribe nada, imprime la línea para copiar y sale con código 3.

Qué protege y qué no: frena el error (un nombre equivocado, un plan equivocado) y las instrucciones inducidas, porque la
respuesta la da un clic humano. Un agente no puede hacer clic sin permisos de accesibilidad del sistema: **si le diste ese
permiso a Cursor o a Terminal, esa defensa se debilita**. No protege de un agente malicioso con control total de la máquina.

Antes de cada escritura, `apply` vuelve a leer el issue: si alguien lo movió o reasignó después de planificar, lo saltea y lo informa. Reaplicar un plan es seguro (saltea lo ya hecho). Cada escritura queda en `~/.local/state/jtk/writes.jsonl`, también las de `jtk create|push|assign --apply` (el registro de cada proyecto, `.jira-kanban/jira-writes.jsonl`, sigue como antes). Las líneas de un plan llevan `plan`; las de los comandos viejos, no.

La skill `jira-em-ops` (solo con `./install.sh --with-write`) prepara los planes y corre `apply` solo cuando la persona lo pidió; la aprobación es el clic en la ventana. Si cancelás, no reintenta.

### Segunda capa: el hook de Claude Code

Con la ventana, el agente puede lanzar `jtk apply` y los `--apply`, porque la barrera ya no es que no pueda ejecutarlos sino que solo un clic humano aprueba. El hook `~/.claude/hooks/git-guardrails.sh` deja pasar esos comandos y bloquea los rodeos que aprobarían por la persona: combinarlos con un pseudo-terminal (`tmux send-keys`, `send`, `new-session`…, escribir `APRUEBO` en una sesión, `expect`, `pexpect`, `unbuffer`, `socat`, `script`, `pty.`) y bloquea siempre (también en otro comando) los clics y teclas automáticos sobre la ventana: `osascript` con `System Events`, `click`, `keystroke` o `AXPress`, `cliclick`, `peekaboo`. Es una segunda capa y no ve todo (un `.scpt` en un archivo, Quartz, `pyautogui`); la defensa de fondo es no darle permiso de accesibilidad a Cursor ni a Terminal. `jtk plan …` pasa. Se verifica con `tools/check-guardrails.sh` (56 casos).

Los parches los aplica la persona, uno encima del otro y en este orden, siempre con `patch -N` (sin `-N`, correrlo dos veces te ofrece revertirlo; con `-N` la segunda vez no cambia nada pero deja un `.rej` al lado del hook, que podés borrar): `tools/git-guardrails-jk-apply.patch` (fase 4), `tools/git-guardrails-jtk.patch` (el renombre) y `tools/git-guardrails-dialog.patch` (la ventana). El último es el que deja de bloquear `apply`: **aplicalo después de tener esta versión de `jtk` instalada**, porque con la guarda vieja un agente seguiría necesitando terminal pero el hook ya no lo frenaría. El hook solo cubre a Claude Code: en Codex y Cursor quedan la guarda y las reglas de `AGENTS.md`.

### Si venías usando `jk`

El comando se llama `jtk` y el nombre viejo no se conserva. El orden importa, porque el hook tiene que reconocer `jtk` **antes** de que el comando exista donde un agente lo pueda correr: desde que `jtk.py` está en el árbol de este repo, un `jtk apply` mandado por un pseudo-terminal no lo frena un hook que solo conoce `jk`. Por eso el parche va primero, y se puede aplicar ya mismo: sigue bloqueando `jk`. Mientras no mergees e instales, `jk` sigue andando; desde el checkout de la rama deja de andar porque `jk.py` ya no existe.

1. Aplicar el parche del hook (sección anterior), antes de mergear; `tools/check-guardrails.sh` tiene que dar 44/44. Después, mergear esta rama.
2. Correr `./install.sh` (con `--with-write` si lo usás). Borra `~/.local/bin/jk` solo si era el enlace de este repo, linkea `jtk` y **imprime** los `mv` de tus datos sin ejecutarlos.
3. Correr esos `mv` vos: `~/.config/jk` pasa a `~/.config/jtk` (perfiles y views) y `~/.local/state/jk` a `~/.local/state/jtk` (planes y registro de escrituras).

Las variables pasan a `JTK_CONFIG_DIR` y `JTK_STATE_DIR`; las viejas ya no se leen y `install.sh` avisa si las tenés exportadas. El registro conserva sus líneas anteriores (`"tool": "jk"`) y un plan aplicado a medias se puede retomar.

## Perfiles de board

Cada board dice «hecho» a su manera (`Done`, `Finalizado`, `Resuelto`) y Jira a veces archiva mal un estado: medido el
2026-10-09 en el Jira de la compañía, hay estados con nombre de «hecho» fuera de la categoría *done* en 29 proyectos.
Por eso los reportes no se fían de la categoría: leen un **rol por estado** que una persona confirma una vez por proyecto.

Roles: `todo`, `active`, `blocked`, `waiting` (frenado por un tercero), `delivered` y `dropped` (cancelado, rechazado,
no aplica). Varios estados pueden tener el mismo rol (`Finalizado` y `Resuelto` → `delivered`). Los perfiles viven en
`~/.config/jtk/profiles/<KEY>.json` (o en `$JTK_CONFIG_DIR`) y no se editan a mano.

| Comando | Qué hace |
|---|---|
| `jtk board setup KEY [--kind flow\|scrum\|helpdesk]` | Lee los estados de Jira, propone un rol por estado y guarda el borrador; correrlo de nuevo no pierde tus decisiones |
| `jtk board set KEY ROL "ESTADO"…` | Asigna un rol por nombre (o `id:<id>` si dos estados se llaman igual); todo o nada |
| `jtk board show KEY` · `jtk board check KEY` | Muestra el perfil · lo compara con los estados de Jira ahora |
| `jtk board survey [--type T] [--json]` | Propone roles para todos los proyectos y cuenta qué necesita una decisión; no guarda nada |

Salida: `0` listo, `1` entrada rechazada, `2` no se pudo (Jira o disco) y **`3` el perfil tiene estados sin rol**: una
persona tiene que decidir. Un reporte de un proyecto sin perfil usa la categoría de Jira y lo avisa arriba con `> ⚠`.
`jtk board EPIC` sigue siendo el tablero local de una épica.

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

- **Editar:** cambiá `status`, el `# título` o el cuerpo y corré `jtk push EPIC`. Si el mismo campo también cambió en Jira,
  push lo informa como **conflicto** y no lo pisa: `jtk pull`, volvé a aplicar tu cambio y repetí el push.
- **Subtarea nueva:** creá `…/subtasks/_new-<algo>/subtask.md` con un `# título`; push la crea bajo el padre del folder y
  le pone su clave.
- **Versionarlo o no** queda a criterio de cada proyecto. Si se versiona, `jira-writes.jsonl` (evidencia local, trae
  el accountId) y `.create-progress-*.json` (transitorio) van al `.gitignore`.

## Estados y bloqueo

Los nombres de las columnas y de los estados cambian entre tableros y se traducen (en PLATE conviven `PROCESANDO`, `Review`,
`Blocked` y `Done`). Por eso `pull` guarda la **categoría** fija que Jira le da a todo estado (`todo`, `in_progress`, `done`)
y `jtk board` agrupa por ella, nunca por el nombre. **Bloqueado** no es una categoría: un issue lo está si su estado figura
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
