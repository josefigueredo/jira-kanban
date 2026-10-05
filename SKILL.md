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
4. **Draft the spec** (JSON, in the scratchpad) from the conversation:
   ```json
   {"epic": {"summary": "…", "description": "objetivo, problema, alcance"},
    "items": [
      {"type": "story", "area": "FE", "summary": "…", "user_story": "Como … quiero … para …",
       "acceptance": ["AC1: Dado … Cuando … Entonces …"], "subtasks": [{"summary": "…"}]},
      {"type": "task", "area": "DEVOPS", "summary": "…", "description": "…", "subtasks": []}]}
   ```
   - `story` only when someone benefits ("Como … quiero … para …"); otherwise `task`. Both hang from the epic as
     siblings; `subtasks` hang from either. There is no fourth level.
   - `area` becomes the `[AREA]` title prefix (`conventions.json` lists them). Do not add components, labels or story
     points: the project does not use them.
   - `"done": true` on an item the user already finished here (implemented, verified, merged); its subtasks inherit
     it unless they say otherwise. Complete issues are assigned to the user without asking and moved to Done after
     creation (children before parents). `"started": true` on one the user is working on now: assigned without asking
     and moved to an in-progress status; its subtasks stay to do.
5. **Preview:** `jk create --spec <file> --jira-project KEY --html <scratchpad>/vista.html` (dry run). Show the tree, open the
   HTML for the user (`open <path>`): a standalone, Jira-like view to navigate epic → items → subtasks. If any issue
   shows "a decidir", ask the user whether to assign the incomplete ones to them. Wait for an explicit yes.
6. **Create:** hand the user the exact command to run with `!`: `jk create --spec <file> --jira-project KEY --apply`,
   plus `--assign-open` or `--no-assign-open` with their answer when some issue is not complete (without it,
   `--apply` refuses). Never run `--apply` yourself: a guardrail hook blocks it. Parents are created first; the
   local kanban is written with the real keys. If Jira rejects an issue halfway, jk keeps what was created, pulls the
   partial kanban and names the keys: fix the cause and hand the user the same command again; it resumes without
   duplicating.
7. **Sync:** `jk pull KEY` refreshes from Jira. Local edits (front-matter status, `# title`, body) go back with
   `jk push KEY` (dry run), then hand the user the same command with `--apply`. A new subtask is `…/subtasks/_new-<slug>/subtask.md` with a
   `# title`; push creates it under its folder's parent.

## Local layout

```
.jira-kanban/<EPIC>/epic.md
.jira-kanban/<EPIC>/stories/<KEY>/story.md
.jira-kanban/<EPIC>/tasks/<KEY>/task.md
.jira-kanban/<EPIC>/<stories|tasks>/<KEY>/subtasks/<KEY>/subtask.md
.jira-kanban/<EPIC>/.sync.json        # baseline of the last pull; push compares against it
```

## Rules

- Every Jira write needs `--apply`, run by the user. Each write is logged in `./.jira-kanban/jira-writes.jsonl`
  (time, command, issue, change), so a change in Jira can be ruled in or out as this skill's.
- Progress: `jk board KEY` (after a pull) groups by Jira status category, never by status names; blocked means a
  status in `blocked_statuses` or the Flagged field.
- A `conflict` from push means the field changed in Jira too: pull, re-apply the local edit, push again.
- Project defaults live in `conventions.json`; a project overrides them in `./.jira-kanban/conventions.json`.
