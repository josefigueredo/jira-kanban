---
name: jira-standup
description: Use when the user asks what they (or a teammate) did in a period ("qué hice ayer", "la semana pasada"), what they can work on in the next days ("hoy", "la semana que viene"), what they are blocked on, how loaded a teammate is before assigning them work, or for their delivery metrics (velocity, lead time). Read only. To create or sync epics use jira-team-kit.
---

# jira-standup

Answers four questions from Jira, live, as tables and trees the user reads at a glance. It never writes to Jira.

```bash
jtk <done|next|blocked|load|stats> ... --project .
```

| The user asks | Run |
|---|---|
| what did I do / yesterday / last week | `jtk done --since D [--until D]` |
| what can I do today / next week | `jtk next [--until D]` |
| what am I blocked on | `jtk blocked` |
| does <person> have room to take work | `jtk load --person "<name>"` |
| my velocity / metrics | `jtk stats [--weeks N]` |

## Steps

1. **Dates.** The CLI only takes `YYYY-MM-DD`. Turn the user's words into dates in `America/Argentina/Buenos_Aires`
   and say which window you used: "ayer" is `--since` = `--until` = yesterday; "la semana pasada" is Monday to Sunday
   of the previous week; "hoy" for `next` is no `--until`; "la semana que viene" is `--until` = the next Sunday.
2. **Run it** with `--jira-project KEY` if the user names a project (otherwise the project in
   `./.jira-kanban/conventions.json`, if any, applies). Show the output as it is: it is already Markdown. Do not
   retell it unless asked.
3. **Another person.** Pass `--person "<name, email or accountId>"`. If the command exits 1 listing candidates,
   show them (name and email) and ask which one; never pick. `jtk who "<name>"` finds a person without running a report.
4. **Capacity.** `load` shows measured numbers. It gives a verdict only if `wip_limit` is set in
   `./.jira-kanban/conventions.json`; never invent a threshold. To assign work, hand the user
   `jtk assign KEY "<person>"` (dry run) and the same command with `--apply`: the user runs that, not you.
5. **Say what the numbers are not.** `done` uses the last status change and "assigned to"; `stats` has no
   story points (PLATE has none) and no true cycle time; small `n` is flagged in the output. Repeat those limits if
   the user draws a conclusion from them.
6. **Profiles.** Reports read each status through a role (`todo`, `active`, `blocked`, `waiting`, `delivered`,
   `dropped`) that a person confirmed once per project. A line starting with `> ⚠` at the top of the output says what
   is missing: a project without profile (the report falls back to Jira's category), statuses nobody decided, or a
   status the profile has never seen. Show it as it is. To fix it run `jtk board setup KEY`: it prints what it
   understood and exits 3 while statuses are undecided. Relay each undecided status to the user, ask which role it
   plays, and apply the answer with `jtk board set KEY <role> "<status>"`. Never choose a role yourself.
7. **Team questions.** If the user asks about their team or their boards as a whole
   ("cómo viene mi equipo", "qué está bloqueado en mis boards"), that is `jira-em`, not this skill. Reports about
   one person inside a saved view take `--view VIEW` here: `jtk done|next|blocked --person "<name>" --view VIEW`.

## Rules

- Read only: never run `create`, `push`, `assign --apply` or anything with `--apply`.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- `jtk board setup|set` write only the local profile in `~/.config/jtk`, never Jira.
- Output labels are Spanish; if the user writes in English, the tables stay as they are.
