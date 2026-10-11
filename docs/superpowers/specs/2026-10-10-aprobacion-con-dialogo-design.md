# Aprobación con diálogo nativo en lugar de terminal aparte: diseño

Fecha: 2026-10-10. Estado: borrador para revisión del usuario.

## Intención

Hoy un manager que usa Cursor (GUI) tiene que salir a una ventana de terminal para escribir `APRUEBO <n>`. Para esa
persona eso es fricción y se parece a algo sospechoso. Lo que se quiere conservar es otra cosa: **que apruebe un humano,
viendo exactamente qué se va a escribir en Jira, y que el agente no pueda aprobar por sí mismo**.

Lo que dijo el usuario: todos los managers usan macOS; botones `Apruebo <n>` y `Cancelar` (cancelar es el predeterminado,
sin caja de texto); la ventana muestra el detalle de lo que se va a hacer, como la skill de Product Brain.

## Qué cambia para la persona

1. Le pide al agente «asignale a Pepito tal tarea».
2. El agente corre `jtk plan …` (solo lee) y muestra el plan en el chat; después corre `jtk apply <id>`.
3. Aparece una ventana del sistema con el detalle: título del plan, cantidad, y una fila por issue con clave, título y
   el cambio (`sin asignar → Pepito Pérez`, `Backlog → PROCESANDO`, el texto del comentario). Botones: **Cancelar**
   (el botón predeterminado, resaltado; Escape lo elige y Return no aprueba nada) y **Apruebo 2**, que solo responde a un clic.
4. Si cancela, cierra o pasan 100 s, no se escribe nada y el comando sale con un mensaje claro.

## Decisiones

1. **Canal de aprobación.** `guard.confirm` mantiene el camino actual (tres flujos con terminal + `/dev/tty`, se tipea
   `APRUEBO <n>`). Cuando **no** hay terminal, en vez de negarse prueba el diálogo; si el diálogo no puede mostrarse
   (no es macOS, sin sesión gráfica, `osascript` ausente o falla) se niega con el mensaje de hoy y el comando para
   correr en una terminal. Sin variable de entorno, bandera ni configuración que salte la aprobación.
2. **Patrón copiado de pbmcp**, que ya funciona con el usuario en Cursor: `product-brain-mcp/src/pbmcp/approval.py:45-55`
   (HTML a un archivo temporal 0600, `osascript -l JavaScript alert.js`, aprobado solo si el código es 0 y la salida es
   `approved`; cualquier fallo o timeout es rechazo), `alert.js:31-38` (`NSAlert` con la vista del plan; la ventana final es un panel propio, ver «Prueba real», Cancelar
   primero y con Escape, el botón de aprobar con `keyEquivalent` vacío, ventana flotante) y `approval.py:21` (timeout de
   100 s porque Cursor corta una herramienta inactiva a los 120 s, medido el 2026-10-07). Se copian, no se importan:
   cada repo es independiente.
3. **Botones.** Primero `Cancelar` (con Escape; Return no hace nada, como en pbmcp: ningún botón es el predeterminado), segundo `Apruebo <n>` sin tecla
   equivalente: aprobar exige un clic. No hay caja de texto.
4. **Detalle.** Un módulo `jkan/approval.py` arma un HTML con la misma paleta de chips que pbmcp: encabezado (tipo de
   plan y vista), una fila por cambio y, si el plan dejó issues afuera, la sección «Quedan afuera» con el motivo. La
   fuente es el **plan guardado**, nunca lo que el agente cuenta. Para que la fila diga qué issue es, cada item del plan
   guarda además `title` (el resumen del issue en el momento de planificar); entra en el hash como el resto.
5. **Comandos viejos** (`create`, `push`, `assign` con `--apply`): usan el mismo diálogo, con una fila por issue a crear
   o cambiar, armada con lo que ya calculan para la vista previa.
6. **API de la guarda.** `guard.confirm(n, summary, command, streams, open_tty, dialog)`: `dialog` es un parámetro de
   prueba, de la misma clase que `open_tty`, y por defecto usa el diálogo real. El test «no hay bypass» pasa a esperar
   esa firma; sigue sin haber banderas ni variables que salten la aprobación. `summary` pasa a ser un objeto con el
   texto plano (para la terminal) y las filas (para el diálogo); la terminal sigue mostrando texto.
7. **El agente corre `apply`.** Con el diálogo, la aprobación humana ya no depende de que el agente no pueda ejecutar el
   comando, así que las skills (`ops/SKILL.md`) y `AGENTS.md` pasan de «nunca corras `jtk apply`» a «corré `jtk apply
   <id>` solo cuando la persona pidió aplicar ese plan, avisale que le va a aparecer una ventana, y si cancela no
   reintentes».
8. **Hook de Claude Code (del usuario).** Hoy bloquea cualquier `jtk apply` y los `--apply`. Pasa a dejarlos correr solos y
   a seguir bloqueando los rodeos que aprobarían por el humano: combinarlos con pseudo-terminal (`tmux`, `expect`,
   `script`, `pty.`), que es lo que ya hace, y **mandar clics o teclas a la ventana** (`osascript` con `System Events`,
   `cliclick`). Es un parche nuevo sobre el actual; lo aplica la persona y `tools/check-guardrails.sh` lo verifica.
9. **Windows y Linux:** fuera de alcance; ahí queda la terminal como hoy.

## Seguridad: qué protege y qué no

- Protege contra el error (nombre equivocado, plan equivocado) y contra instrucciones inducidas: la ventana muestra el
  plan guardado y la respuesta solo la da un clic humano.
- Un agente no puede hacer clic sin permisos de accesibilidad del sistema, que el usuario no concede por defecto. Si
  esos permisos existieran para Cursor o Terminal, esa defensa se debilita; está dicho en el README.
- No protege contra un agente malicioso con control total de la máquina (podría tocar el código o `PATH`). Era así antes.
- Una ventana por plan: un agente que insista abre ventanas, pero cada una necesita un clic y vence a los 100 s.
- El texto de la ventana usa solo datos del plan guardado y se escapa como HTML (un título de Jira con `<script>` no
  se ejecuta).

## Pruebas

- Unitarias con `dialog` inyectado: aprueba solo con `approved`; rechaza con `cancelled`, código distinto de 0,
  timeout, `osascript` ausente, salida inesperada; no se abre cuando hay terminal; no hay terminal ni diálogo →
  mensaje de hoy; el HTML escapa títulos hostiles; el botón lleva el `n` correcto; el archivo temporal se borra.
- `plan` guarda `title` y el hash cambia si cambia; los planes viejos sin `title` siguen aplicándose (la fila muestra
  solo la clave).
- Hook: casos nuevos en `tools/check-guardrails.sh` (apply solo → pasa; apply con tmux/expect/script → bloquea;
  `osascript` con `System Events` o `cliclick` junto a apply → bloquea).
- **Aceptación manual con el usuario en Cursor** (no se puede automatizar, como en pbmcp): la ventana aparece al
  frente, Escape cancela, Return no aprueba, solo el clic aprueba, el timeout cancela, se ve bien en modo oscuro.

## Riesgos y límites

- La ventana puede quedar detrás de Cursor: pbmcp la sube con `activateIgnoringOtherApps` y nivel flotante; si en
  alguna máquina falla, el timeout cancela sin escribir.
- El timeout de 100 s significa que un plan largo de revisar vence: se vuelve a pedir `apply`.
- Hasta que el usuario aplique el parche nuevo del hook, el agente sigue bloqueado y todo funciona como hoy.

## Resultados de la implementación (revisión final)

- Suite: 666 tests en `python3` y en `/usr/bin/python3` (3.9). La suite nunca abre una ventana real: `tests/helpers.py`
  reemplaza `guard._default_dialog` por una ventana nula.
- Hook: `tools/check-guardrails.sh` = 56 casos; contra el hook actual del usuario 40/56, contra una copia con
  `git-guardrails-dialog.patch` 56/56. El hook real no se tocó.
- Revisión final (`fable`), arreglada en una pasada con test en rojo antes:
  - `jtk push --apply` con issues nuevos fallaba antes de mostrar la ventana (`Path` en vez de texto en una fila).
  - `defaultButtonCell` en `alert.js` le quitaba Escape a Cancelar; se sacó (pbmcp no lo usa).
  - Una ventana que no puede abrirse (`osascript` falla) ya no se informa como «cancelada»: pide la terminal.
  - El hook bloquea siempre los clics y teclas automáticos, no solo junto a `apply` (el rodeo en dos pasos estaba abierto).
  - Se sacó un `cli.py.bak` que se coló en un commit, y se actualizaron los textos viejos (`jtk plan` y la guarda).
- Límites que quedan dichos: el hook no ve scripts en archivos, `Quartz` ni `pyautogui`; un agente con permisos de
  accesibilidad podría hacer clic; la prueba real de la ventana (al frente, Escape, Return, tiempo) es manual:
  `docs/superpowers/acceptance/aprobacion-con-dialogo.md`.
- Menores diferidos: `render_html` recibe `n` y no lo usa; el «100 s» del texto de la ventana está repetido en vez de salir
  de `TIMEOUT`; falsos positivos del hook ante un mensaje de commit que nombre `osascript … click` y `jtk apply`.

## Prueba real y rediseño (2026-10-10, en Cursor, con tareas descartables de PLATE)

La probó la persona, con `jtk apply` y `jtk assign --apply` sobre PLATE-664 a 669. Lo medido:

- **Primera versión (`NSAlert` con un `NSTextView`).** Apareció al frente de Cursor; Cancelar, Escape y Return se portaron
  como se esperaba y el timeout cerró la ventana a los 100 s sin escribir. Pero no pasó la revisión de diseño: el
  renderizador de texto de macOS ignora `padding`, bordes y fondos, así que el detalle parecía un textarea; el ícono del
  escudo ocupaba 64 pt, el título se repetía y la caja tenía alto fijo.
- **Versión final: panel propio.** `jkan/alert.js` abre un `NSPanel` con un `WKWebView` (sin JavaScript, sin recursos
  externos) y dos botones nativos; `approval.render_html` arma la página (tarjeta por tarea con la clave como chip, el
  cambio como píldora origen → destino, «Quedan afuera» aparte, modo claro y oscuro del sistema) y `window_height` estima
  el alto (con margen; el tope es 560 y pasado eso la página scrollea). El diseño se iteró en el navegador, en claro y en oscuro, antes
  de tocar la ventana.
- **Recorrido real con la versión final** (plan de 2 tareas, PLATE-664 y PLATE-669): Escape cancela (`exit=3`); Return no
  hace nada y la ventana sigue abierta; el botón rojo cancela (`exit=3`, asumido por la persona); a los 100 s sin tocar nada se
  cierra sola (`exit=3`); un clic en **Apruebo 2** escribe y dice `applied` (`exit=0`). Antes, con la primera versión: Apruebo
  1 y Apruebo 4 escribieron; el título `Prueba <b>negrita</b> & más` se vio literal; «Quedan afuera» mostró PLATE-665 con el motivo;
  `jtk assign --apply` mostró `-> Jose Ramon Figueredo`, y repetido sobre un issue ya asignado dijo `assigned 0` sin abrir ventana.
- **Fallas vistas y corregidas:** la altura se estimaba mal dos veces (una barra de scroll innecesaria, y un título largo de
  plan que ocupa dos líneas dejó el pie cortado). Se corrigió contando las líneas del título y con margen, y se **quitó la
  regla que escondía la barra**: con una estimación corta, la barra es la red que deja ver lo que se está aprobando.
- **Sin medir:** pantalla completa y modo claro (el modo oscuro sí se vio); la ventana nunca se vio con un plan que llegue al tope de 560.
- Menores: ya no queda diferido que `render_html` ignore `n` (el pie dice «Apruebo n») ni que el «100 s» esté repetido (sale de `TIMEOUT`).
