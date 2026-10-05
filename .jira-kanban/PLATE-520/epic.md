---
key: PLATE-520
kind: epic
issuetype: Epic
status: Backlog
category: todo
blocked: false
parent: 
url: https://example.atlassian.net/browse/PLATE-520
synced: 2026-10-05T21:11:22Z
---

# Skill jira-kanban: épicas de Jira desde la conversación, espejadas como kanban local

Objetivo: que un agente (Claude Code, Codex o Cursor) cree una épica de Jira a partir de lo que se estuvo trabajando y la mantenga espejada en los dos sentidos como un kanban local en ./.jira-kanban/ del proyecto.

Problema: registrar en Jira el trabajo ya hecho o planificado se carga a mano, sin seguir las convenciones del proyecto (prefijo de área, historia vs tarea), y lo local y Jira se desincronizan.

Alcance: crear (con vista previa y confirmación), pull, push con detección de conflictos, tablero por categoría de estado, regla de asignación e instalación compartida. Fuera de alcance: componentes, labels y story points.

Repo: ~/CurrentCode/SPECKIT/Harness/jira-kanban (todavía sin remoto en GitHub).
