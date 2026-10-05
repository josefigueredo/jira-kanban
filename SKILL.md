---
name: jira-kanban
description: Use when the user asks to create a Jira epic for the work being discussed ("creame una épica para esto"), to mirror an existing epic as a local kanban, or to sync local kanban edits (status, titles, new subtasks) back to Jira. Not for epics that a WayOfWork flow registers through Product Brain's export: there Product Brain creates the epic.
---

# jira-kanban

Create a Jira epic from the conversation and mirror it, both ways, as a local kanban in `./.jira-kanban/`. All Jira
access goes through `jk`; never hand-roll Jira calls or another folder layout.

```bash
python3 ~/.agents/skills/jira-kanban/jk.py <create|pull|push|show|board> ... --project .
```

## Steps

1. **Not inside a WayOfWork flow:** if the project has `wow/plan/manifest.json`, its epics come from Product Brain's
   export; say so and use this skill only if the user confirms the work is outside that plan.
2. **Jira project:** there is no default. Use `"project"` from `./.jira-kanban/conventions.json` if it exists;
   otherwise ask the user which project and pass `--jira-project KEY`.
3. **Existing epic first:** a `**Jira Epic:** KEY` in `specs/*/spec.md`, a key in the conversation or the branch. If one
   covers the work, ask before creating anything; to mirror it, run `jk pull KEY`.
4. **Draft the spec** (JSON, in the scratchpad) from the conversation. Read `references/spec.md` first: it has the
   format and when an item is a story or a task, finished (`done`, with its `evidence`: the commits, branch or URL), in progress (`started`) or open.
5. **Preview:** `jk create --spec <file> --jira-project KEY --html <scratchpad>/vista.html` (dry run). Show the tree and
   `open` the HTML, a Jira-like view of what this pass does. If any issue shows "a decidir", ask the user whether to
   assign the open ones to them. Wait for an explicit yes.
6. **Create:** hand the user the exact command to run with `!`: `jk create --spec <file> --jira-project KEY --apply`,
   plus `--assign-open` or `--no-assign-open` with their answer. Never run `--apply` yourself: a guardrail hook
   blocks it. If Jira rejects an issue halfway, jk keeps what was created and names the keys: fix the cause and hand
   the user the same command again; it resumes without duplicating. If only a move to
   Done or in progress fails, every issue exists: never rerun create; finish it with a status edit and push.
7. **Sync:** `jk pull KEY` refreshes from Jira. Local edits go back with `jk push KEY` (dry run), then hand the user
   the same command with `--apply`. `references/layout.md` has the folders, how to edit and add a subtask, and what a
   conflict means.

## Rules

- Every Jira write needs `--apply`, run by the user, and is logged in `./.jira-kanban/jira-writes.jsonl`.
- Progress: `jk board KEY` (after a pull) groups by Jira status category, never by status names; blocked means a
  status in `blocked_statuses` or the Flagged field.
- Project defaults live in `conventions.json`; a project overrides them in `./.jira-kanban/conventions.json`.
