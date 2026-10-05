---
key: PLATE-529
kind: story
issuetype: Story (migrated)
status: Done
category: done
blocked: false
parent: PLATE-520
url: https://example.atlassian.net/browse/PLATE-529
synced: 2026-10-05T21:11:22Z
---

# [AI] Asignar lo completo y preguntar por lo abierto

Como desarrollador quiero que lo que ya hice se me asigne solo para no reasignar a mano y decidir yo sobre lo pendiente

Criterios de aceptación:
- AC1: Dado un item con done true Cuando se crea Entonces queda asignado a mí sin preguntar
- AC2: Dado un item abierto sin --assign-open ni --no-assign-open Cuando corro --apply Entonces se niega antes de llamar a Jira
