---
key: PLATE-525
kind: story
issuetype: Story (migrated)
status: Done
category: done
blocked: false
parent: PLATE-520
url: https://example.atlassian.net/browse/PLATE-525
synced: 2026-10-05T21:11:22Z
---

# [AI] Sincronizar el kanban local con Jira en los dos sentidos

Como desarrollador quiero editar el estado, el título y la descripción en los .md locales para que Jira quede al día sin abrirlo

Criterios de aceptación:
- AC1: Dado una épica en Jira Cuando corro jk pull Entonces el kanban local refleja sus hijos y quita los que salieron de la épica
- AC2: Dado un campo cambiado local y en Jira Cuando corro jk push Entonces se informa como conflicto y no se pisa
- AC3: Dado un folder _new-* con un título Cuando corro jk push --apply Entonces se crea la subtarea bajo el padre del folder
