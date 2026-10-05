---
key: PLATE-534
kind: task
issuetype: Tarea
status: Done
category: done
blocked: false
parent: PLATE-520
url: https://example.atlassian.net/browse/PLATE-534
synced: 2026-10-05T21:11:22Z
---

# [AI] Endurecer la skill: retomar un create a medias, sin proyecto por defecto y registro de escrituras

Si Jira rechaza un issue a mitad de camino, create conserva lo creado y el mismo comando retoma sin duplicar. Lo terminado pasa a Done y lo que está en curso a En progreso. No hay proyecto de Jira por defecto (--jira-project). Cada escritura queda en .jira-kanban/jira-writes.jsonl y el --apply lo corre el usuario.
