---
name: jira-kanban
description: Use when the user asks to create a Jira epic for the work being discussed ("creame una épica para esto"), to mirror an existing epic as a local kanban, or to sync local kanban edits (status, titles, new subtasks) back to Jira.
---

# jira-kanban

Create a Jira epic from the conversation and keep it mirrored, both ways, as a local kanban in `./.jira-kanban/` of the
current project. All Jira access goes through `jk`; never hand-roll Jira calls or another folder layout.

```bash
python3 ~/.claude/skills/jira-kanban/jk.py <create|pull|push|show> ... --project .
```

## Steps

1. **Existing epic first.** Look for one already covering the work: a `**Jira Epic:** KEY` in `specs/*/spec.md`, a key
   in the conversation or the branch. If there is one, ask before creating anything; to mirror it, run `jk pull KEY`.
2. **Draft the spec** (JSON, in the scratchpad) from the conversation:
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
3. **Preview:** `jk create --spec <file>` (dry run). Show the tree to the user and wait for an explicit yes.
4. **Create:** `jk create --spec <file> --apply`. Issues are created parents first and assigned to the caller; the
   local kanban is written with the real keys.
5. **Sync:** `jk pull KEY` refreshes from Jira. Local edits (status in the front matter, the `# title` line, the body)
   go back with `jk push KEY` (dry run) and `jk push KEY --apply` after the user agrees. A new subtask is a folder
   `…/subtasks/_new-<slug>/subtask.md` with a `# title`; push creates it and renames the folder to its key.

## Local layout

```
.jira-kanban/<EPIC>/epic.md
.jira-kanban/<EPIC>/stories/<KEY>/story.md
.jira-kanban/<EPIC>/tasks/<KEY>/task.md
.jira-kanban/<EPIC>/<stories|tasks>/<KEY>/subtasks/<KEY>/subtask.md
.jira-kanban/<EPIC>/.sync.json        # baseline of the last pull; push compares against it
```

## Rules

- Every Jira write needs `--apply` and the user's yes for that write.
- A `conflict` from push means the field changed in Jira too: pull, re-apply the local edit, push again.
- Project defaults live in `conventions.json`; a project overrides them in `./.jira-kanban/conventions.json`.
