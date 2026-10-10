---
name: jira-em
description: Use when a manager asks about their team or their boards as a whole ("cómo viene mi equipo", "qué está bloqueado en mis boards", "qué está estancado", "resumen de la semana", "cómo anda la mesa de ayuda", "cómo andan mis equipos"), not about themselves. Read only. For "what did I do" or "what can I do" use jira-standup, and to create or sync epics use jira-kanban.
---

# jira-em

Answers questions about the **team and the boards a manager follows**, live from Jira, as tables that are read at a glance.
It never writes to Jira.

```bash
jk team <status|stalled|blocked|flow|digest|desk> VIEW ...
jk team rollup VIEW [VIEW ...]
```

| The user asks | Run |
|---|---|
| how is my team doing / how much is open, by person | `jk team status VIEW` |
| what is stuck / has not moved | `jk team stalled VIEW [--days N]` |
| what is blocked, what waits for someone else | `jk team blocked VIEW` |
| how fast do we deliver, lead time | `jk team flow VIEW [--weeks N]` |
| summary of the week / of a period | `jk team digest VIEW --since D [--until D]` |
| how is the help desk (age, unowned, resolution time) | `jk team desk VIEW [--weeks N]` |
| *which* ones: the unowned, the oldest, the ones in a role (after a count from status or desk) | `jk team status\|desk VIEW --list [--unassigned] [--older-than DAYS] [--role ROLE]` |
| several teams side by side (a Sr EM) | `jk team rollup VIEW VIEW ...` |
| what did <person> do / can do / is blocked on, inside my boards | `jk done\|next\|blocked --person "<name>" --view VIEW` |

## Steps

1. **Find the view.** `jk team list` shows the saved views. If the user has none, or names boards that are not in one,
   create it: `jk team setup NAME --boards KEY,KEY --group <jira group>` (or `--people "<name>" ...`). Ask the user for
   the boards and for the group or the people; never invent them. `jk team show NAME` shows a view and the state of its
   boards' profiles.
2. **Profiles first.** A report is refused (exit 1, "no profile for KEY") until every board of the view has a profile.
   Run `jk board setup KEY` for each. It exits 3 while statuses are undecided: relay each undecided status to the user,
   ask which role it plays (`todo`, `active`, `blocked`, `waiting`, `delivered`, `dropped`), apply the answer with
   `jk board set KEY <role> "<status>"`, and never choose a role yourself. A help desk board needs
   `jk board setup KEY --kind helpdesk`. A report on a profile with undecided statuses still runs and says so.
3. **Dates.** The CLI only takes `YYYY-MM-DD`. Turn the user's words into dates in `America/Argentina/Buenos_Aires` and
   say which window you used ("la semana pasada" is Monday to Sunday of the previous week).
4. **Run it and show the output as it is.** It is already Markdown and ends with a «Límites» section: do not retell it
   unless asked, and repeat those limits if the user draws a conclusion from the numbers. A line starting with `> ⚠`
   at the top says what to distrust (a search that hit its cap, a status the profile has never seen): keep it.
5. **Another person inside the view.** Pass `--person "<name>"`. If the command exits 1 listing candidates, show them
   (name and email) and ask which one; never pick.
6. **From a number to its issues.** When the user asks «which ones?» about a count of `status` or `desk`, add `--list`
   (and `--unassigned`, `--older-than DAYS`, `--role todo|active|blocked|waiting|none` to narrow it). The list is
   what the report counted, oldest first, so without filters it has as many rows as the number. Never answer «which
   ones» from memory or by searching Jira on your own.
7. **Load verdicts.** `jk team status` gives a verdict only for boards with a WIP limit (`jk board limit KEY N`); the
   limit is the team's decision, so ask for it and never invent one.

## Rules

- Read only: never run `create`, `push`, `assign`, anything with `--apply`, or `jk board` writes other than the profile
  commands above.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- Exit code 3 of `jk board` means a person has to decide; it is not an error to retry.
- Questions about the user themselves ("qué hice", "qué puedo hacer", "en qué estoy bloqueado") are `jira-standup`, not this skill.
- Output labels are Spanish; if the user writes in English, the tables stay as they are.
