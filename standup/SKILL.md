---
name: jira-standup
description: Use when the user asks what they (or a teammate) did in a period ("qué hice ayer", "la semana pasada"), what they can work on in the next days ("hoy", "la semana que viene"), what they are blocked on, how loaded a teammate is before assigning them work, or for their delivery metrics (velocity, lead time). Read only. To create or sync epics use jira-team-kit. Jira always goes through jtk, never an Atlassian MCP.
---

# jira-standup

Answers four questions from Jira, live, as tables and trees the user reads at a glance. It never writes to Jira.

```bash
jtk <done|next|blocked|load|stats> ... --project .
```

| The user asks | Run |
|---|---|
| what did I do / yesterday / last week | `jtk done --when yesterday` · `--when last-week` (or `--since D [--until D]`) |
| what can I do today / next week | `jtk next` · `--when next-week` (or `--until D`) |
| what am I blocked on | `jtk blocked` |
| does <person> have room to take work | `jtk load --person "<name>"` |
| my velocity / metrics | `jtk stats [--weeks N]` |

## Steps

1. **Window.** Name it, never count days: `--when` takes `today`, `yesterday`, `this-week`, `last-week`, `this-month`,
   `last-month` for `done`, and `today`, `this-week`, `next-week` for `next` ("ayer" is `yesterday`, "la semana pasada"
   is `last-week`, "la semana que viene" is `next-week`). The CLI does the calendar in `America/Argentina/Buenos_Aires`,
   weeks Monday to Sunday, and prints the window it used: do not add your own. For any other range use
   `--since D --until D` with `YYYY-MM-DD`.
2. **Run it** with `--jira-project KEY` if the user names a project (otherwise the project in
   `./.jira-kanban/conventions.json`, if any, applies). Show the output as it is: it is already Markdown. Do not
   retell it unless asked. If it runs to about 60 lines or more (a month of `done` is ~13 KB), do not reprint it: say in
   one sentence what it holds and that the full report is in the command output, and offer to detail any part. Do not run the same report again in the same conversation: the answer is already in it;
   run it again only if the user asks for fresh data or time has passed.
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

## Updates

Run `jtk update --check` once per conversation, before the first other `jtk` command. It reads the remote only (no Jira, cached for 12 hours) and prints one row; act on its State:

- `up to date` or `ahead`: say nothing.
- `behind`: say in one sentence that jtk is behind (Detail names the new commits) and offer `jtk update`. Run it only if the person says yes; it fast-forwards the install and never resets anything. Then tell them to start a new conversation, because this one still has the old skill loaded.
- `diverged`: tell them once and do not update.
- `unknown` (no network, or not a git clone): say nothing and carry on; never block on it.

If `jtk update` refuses (uncommitted changes, another branch), pass the reason on; do not fix it with git yourself.

## Rules

- Read only: never run `create`, `push`, `assign --apply` or anything with `--apply`.
- Never print or ask for Jira credentials (`IC_JIRA_*`).
- `jtk board setup|set` write only the local profile in `~/.config/jtk`, never Jira.
- Output labels are Spanish; if the user writes in English, the tables stay as they are.
