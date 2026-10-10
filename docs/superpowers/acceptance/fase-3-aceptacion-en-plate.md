# Aceptación real de la fase 3, en PLATE

Prueba manual de `jtk plan` y `jtk apply` contra un Jira real, con tickets descartables en el board PLATE. La corrés vos, en
una terminal de verdad. El agente solo corre los `jtk plan` (leen Jira y guardan un archivo) y lee tus salidas.

## Antes de empezar

- **PLATE es un board real.** Quien lo mira recibe notificaciones de lo que se cree o se mueva. Por eso todo vive bajo una
  sola épica con el prefijo `[SANDBOX fase 3]`, y nunca se selecciona por estado ni por antigüedad: **siempre por clave
  explícita**. Ningún plan de esta guía puede tocar un ticket real.
- **Un comentario no se borra con la herramienta.** Se borra a mano en Jira, o al borrar el issue.
- **Al terminar** se cierran y se borran la épica y sus 6 tareas desde la interfaz de Jira (hace falta permiso de
  borrado; si no lo tenés, cerrarlas con prefijo `[SANDBOX]` es suficiente y queda como registro).
- Tiene que haber una terminal real: `stdin`, `stdout`, `stderr` y `/dev/tty`. Una ventana de Terminal o iTerm alcanza;
  `!` de Claude Code no (ahí la guarda se niega, y eso es parte de la prueba).

## Paso 1. Crear la épica y las 6 tareas

Desde `Harness/jira-kanban`, en tu terminal. Primero el ensayo (no escribe nada):

```
jtk create --spec docs/superpowers/acceptance/fase-3-sandbox-spec.json --jira-project PLATE --no-assign-open
```

Tiene que decir `dry run: nothing created; --apply creates 7 issues in PLATE`. Después, escribiendo:

```
jtk create --spec docs/superpowers/acceptance/fase-3-sandbox-spec.json --jira-project PLATE --no-assign-open --apply
```

Pide `APRUEBO 7`. Anotá las 7 claves: la épica `E` y las tareas `T1` a `T6`. Comprobá en Jira que están sin asignar.

**Ojo con `--to active`:** en PLATE el rol `active` tiene dos estados (`PROCESANDO`, id 10115, y `Review`, id 14012), así
que el plan pide elegir uno con `--to-status`. Todos los `move` de esta guía usan `--to-status 10115` (`PROCESANDO`).
Ese pedido es parte de lo que se verifica: si el plan no lo exige, anotalo como desvío.

## Paso 2. La guarda se niega donde debe (guardá cada salida)

Con una clave real de las tareas (`T1`):

1. Planificá desde Claude Code, con `!`: `! jtk plan move plataforma T1 --to active --to-status 10115`. Tiene que imprimir un resumen y un
   id de 12 caracteres (`P1`). No escribe nada en Jira.
2. Aplicalo con `!`: `! jtk apply P1`. **Tiene que fallar con salida 3** y una línea con el comando para correr en otra
   ventana. `T1` no cambia en Jira.
3. En tu terminal, con el id tipeado por stdin: `echo "APRUEBO 1" | jtk apply P1`. **Tiene que negarse**, porque stdin no
   es una terminal. `T1` no cambia.
4. Probá también que el hook funcione: pedile al agente que corra `jtk apply P1` con su herramienta Bash. Tiene que
   bloquearlo el hook, antes de llegar a la guarda.

## Paso 3. Un plan de cada tipo, aplicado desde tu terminal

Siempre dos pasos: `jtk plan …` (lo puede correr el agente) y `jtk apply <id>` en tu terminal, donde escribís
`APRUEBO <n>` con `n` igual a la cantidad de cambios.

| Tipo | Plan | Qué mirar en Jira después |
|---|---|---|
| move | `jtk plan move plataforma T1 T2 --to active --to-status 10115` | `T1` y `T2` pasan a `PROCESANDO` |
| assign | `jtk plan assign plataforma T3 T4 --person "<TU NOMBRE>"` | `T3` y `T4` quedan asignadas a vos |
| comment | `jtk plan comment plataforma T5 T6 --text "prueba de fase 3 (descartable)"` | un comentario en `T5` y otro en `T6` |

Para cada uno: comparar lo que quedó en Jira con lo que decía el resumen del plan y con la última línea de
`~/.local/state/jtk/writes.jsonl` (una por cambio, con `"tool": "jtk"`, el id del plan y `"result": "ok"`).

## Paso 4. Los casos borde, de verdad

1. **Cambió algo entre el plan y el apply:** planificá `jtk plan move plataforma T3 --to blocked`. Antes de aplicar,
   cambiá `T3` a mano en Jira a otro estado. Al aplicar tiene que decir `changed` para `T3` y no tocarlo.
2. **Aplicar dos veces:** volvé a correr `jtk apply P` de un plan que ya aplicaste. La segunda vez dice
   `already applied` y no escribe (el comentario no se duplica).
3. **Deshacer:** `jtk plan revert <id del move del paso 3>` y después `jtk apply` del plan nuevo. `T1` y `T2` vuelven a su
   estado anterior. Si el inverso cierra algo, pide `--allow-close`.
4. **Mover a un estado con campos obligatorios:** planificá `jtk plan move plataforma T6 --to delivered --allow-close`.
   Si el workflow de PLATE pide un campo al pasar a `Done`, tiene que aparecer como `required fields` y no escribir.
   Esto es lo que no se pudo probar contra el Jira falso.
5. **Desasignar:** si Jira lo permite, un `jtk plan assign` que deje una tarea sin dueño. Es el otro caso que solo se
   prueba con Jira real (`Jira.assign(key, None)`).

## Paso 5. La guarda de los comandos viejos

`jtk assign T4 "<TU NOMBRE>" --apply` con `!` tiene que salir con 3 y no escribir. En tu terminal tiene que pedir
`APRUEBO 1` y asignar.

## Paso 6. Cerrar

1. Pegale al agente las salidas de los pasos 2 a 5 (sin credenciales). Él completa la línea «Prueba real» de «Resultados
   de la fase 3» en el spec con fechas, conteos y desvíos, corre las dos suites y commitea.
2. Cerrá y borrá la épica y las 6 tareas en Jira.
3. `~/.local/state/jtk/writes.jsonl` se queda como registro de la prueba; si querés partirlo, hacelo a mano.
