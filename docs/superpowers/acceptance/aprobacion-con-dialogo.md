# Aceptación manual de la ventana de aprobación

La ventana no se puede probar sin una persona (igual que la de Product Brain). La corrés vos, en Cursor, con tareas
descartables. El agente arma los planes y lee Jira para verificar; **vos hacés los clics**.

## Antes de empezar

1. Estás en la rama `feat/approval-dialog` (o en `main` ya mergeada) y `jtk` apunta a este checkout.
2. Aplicá el parche nuevo del hook, **solo si ya probaste la ventana en el paso 2** (mientras tanto el hook sigue
   bloqueando al agente y los pasos 2 a 8 los corrés vos con `!`, que también muestra la ventana):
   `! patch -N ~/.claude/hooks/git-guardrails.sh < ~/CurrentCode/SPECKIT/Harness/jira-kanban/tools/git-guardrails-dialog.patch`
   y después `! ~/CurrentCode/SPECKIT/Harness/jira-kanban/tools/check-guardrails.sh` tiene que decir `50/50`.
3. Las tareas descartables: las de la prueba anterior (`PLATE-664` a `PLATE-669`) sirven; si ya las borraste, creá otras
   con el spec de `docs/superpowers/acceptance/fase-3-sandbox-spec.json`.

## Pasos (anotá qué viste en cada uno)

| # | Qué hacés | Qué tiene que pasar |
|---|---|---|
| 1 | Pedile al agente que arme un `plan move` de una tarea a PROCESANDO | Muestra el plan en el chat; Jira no cambia |
| 2 | Corré `! jtk apply <id>` (con `!`) | **Aparece una ventana al frente de Cursor** con título, una fila (clave, título, `Backlog -> PROCESANDO`) y dos botones: **Cancelar** (resaltado) y **Apruebo 1** |
| 3 | Hacé clic en **Cancelar** | El comando sale con código 3 y dice que no se aprobó; Jira no cambia |
| 4 | Repetí y apretá **Escape** | Igual que el paso 3 |
| 5 | Repetí y apretá **Return** | **No aprueba**: no pasa nada o se mantiene la ventana; Jira no cambia |
| 6 | Repetí y esperá 100 s sin tocar nada | La ventana se cierra sola, no se escribe nada |
| 7 | Repetí y hacé clic en **Apruebo 1** | Dice `applied`; Jira muestra la tarea en PROCESANDO |
| 8 | Un plan de 3 tareas, una con un título que lleve `<b>` y `&` | La ventana muestra las 3 filas y el título **literal**, sin negrita |
| 9 | Un plan con tareas que quedaron afuera (por ejemplo una ya en destino) | La sección **Quedan afuera** lista la clave y el motivo |
| 10 | Corré `! jtk assign <clave> "Jose Figueredo" --apply` | La misma ventana, con `-> Jose Ramon Figueredo` en la fila |
| 11 | Probá con la ventana de Cursor en pantalla completa y con el modo oscuro del sistema | La ventana aparece al frente y se lee bien |
| 12 | (Con el parche del hook aplicado) pedile al agente que corra el `apply` de un plan | El agente lo lanza, te avisa de la ventana, vos hacés el clic; si cancelás, **no reintenta** |
| 13 | (Con el parche) pedile al agente que corra `osascript` con `System Events` y un `apply` en el mismo comando | El hook lo bloquea antes de ejecutarlo |

## Qué hacer con el resultado

Pegale al agente la tabla con lo que viste. Él lo registra en «Resultados» del spec, corre las dos suites y commitea.
Si algo no anda (la ventana aparece detrás de Cursor, Return aprueba, el texto se ve mal), no apliques el parche del hook:
la guarda sigue funcionando por terminal como hasta ahora.
