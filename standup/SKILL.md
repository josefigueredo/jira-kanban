---
name: jira-standup
description: Use when the user asks what they (or a teammate) did in a period ("qué hice ayer", "la semana pasada"), what they can work on in the next days ("hoy", "la semana que viene"), what they are blocked on, how loaded a teammate is before assigning them work, or for their delivery metrics (velocity, lead time). Read only. To create or sync epics use jira-kanban.
---

# jira-standup

Answers four questions from Jira, live, as tables and trees the user reads at a glance. It never writes to Jira.

```bash
python3 ~/.agents/skills/jira-kanban/jk.py <done|next|blocked|load|stats> ... --project .
```

| The user asks | Run |
|---|---|
| what did I do / yesterday / last week | `jk done --since D [--until D]` |
| what can I do today / next week | `jk next [--until D]` |
| what am I blocked on | `jk blocked` |
| does <person> have room to take work | `jk load --person "<name>"` |
| my velocity / metrics | `jk stats [--weeks N]` |

## Steps

1. **Dates.** The CLI only takes `YYYY-MM-DD`. Turn the user's words into dates in `America/Argentina/Buenos_Aires`
   and say which window you used: "ayer" is `--since` = `--until` = yesterday; "la semana pasada" is Monday to Sunday
   of the previous week; "hoy" for `next` is no `--until`; "la semana que viene" is `--until` = the next Sunday.
2. **Run it** with `--jira-project KEY` if the user names a project (otherwise the project in
   `./.jira-kanban/conventions.json`, if any, applies). Show the output as it is: it is already Markdown. Do not
   retell it unless asked.
3. **Another person.** Pass `--person "<name, email or accountId>"`. If the command exits 1 listing candidates,
   show them (name and email) and ask which one; never pick. `jk who "<name>"` finds a person without running a report.
4. **Capacity.** `load` shows measured numbers. It gives a verdict only if `wip_limit` is set in
   `./.jira-kanban/conventions.json`; never invent a threshold. To assign work, hand the user
   `jk assign KEY "<person>"` (dry run) and the same command with `--apply`: the user runs that, not you.
5. **Say what the numbers are not.** `done` uses the last status change and "assigned to"; `stats` has no
   story points (PLATE has none) and no true cycle time; small `n` is flagged in the output. Repeat those limits if
   the user draws a conclusion from them.

## Rules

- Read only: never run `create`, `push`, `assign --apply` or anything with `--apply`.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- Output labels are Spanish; if the user writes in English, the tables stay as they are.
