---
key: PLATE-521
kind: story
issuetype: Story (migrated)
status: Done
category: done
blocked: false
parent: PLATE-520
url: https://example.atlassian.net/browse/PLATE-521
synced: 2026-10-05T21:11:22Z
---

# [AI] Crear una épica en Jira desde la conversación

Como desarrollador quiero pedirle al agente "creame una épica para esto" para registrar en Jira lo trabajado sin cargarlo a mano

Criterios de aceptación:
- AC1: Dado un spec válido Cuando corro jk create sin --apply Entonces veo el plan y no se escribe nada en Jira
- AC2: Dado un spec con una historia sin "Como … quiero … para …" Cuando lo valido Entonces se rechaza y sugiere usar una tarea
- AC3: Dado jk create --apply Cuando termina Entonces los padres se crearon antes que los hijos, los títulos llevan [AREA] y el kanban local usa las claves reales
