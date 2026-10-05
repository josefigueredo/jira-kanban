---
key: PLATE-530
kind: story
issuetype: Story (migrated)
status: Done
category: done
blocked: false
parent: PLATE-520
url: https://example.atlassian.net/browse/PLATE-530
synced: 2026-10-05T21:11:22Z
---

# [AI] Ver el avance agrupado por categoría de estado y bloqueo

Como desarrollador quiero ver bloqueado, por hacer, en progreso y hecho para saber el avance aunque el tablero use nombres propios o traducidos

Criterios de aceptación:
- AC1: Dado un estado con nombre propio (PROCESANDO) Cuando corro jk board Entonces se agrupa por su categoría de Jira
- AC2: Dado un issue con Flagged o en un estado de blocked_statuses Cuando corro jk board Entonces aparece en Bloqueado
