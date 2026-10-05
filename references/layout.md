# The local kanban

```
.jira-kanban/<EPIC>/epic.md
.jira-kanban/<EPIC>/stories/<KEY>/story.md
.jira-kanban/<EPIC>/tasks/<KEY>/task.md
.jira-kanban/<EPIC>/<stories|tasks>/<KEY>/subtasks/<KEY>/subtask.md
.jira-kanban/<EPIC>/.sync.json          # baseline of the last pull; push compares against it
.jira-kanban/jira-writes.jsonl          # every write to Jira: time, command, issue, change (keep it out of git)
.jira-kanban/.create-progress-*.json    # keys of a create in flight, removed when it ends (keep it out of git)
.jira-kanban/conventions.json           # optional project override of the skill's conventions.json
```

Each `.md` has a front matter (`key`, `kind`, `issuetype`, `status`, `category`, `blocked`, `parent`, `url`),
the title as `# …` and the description below. The last sync time lives only in `.sync.json`, so a pull with
nothing new leaves every `.md` unchanged. The folder decides kind and parent; the front matter never
moves an issue.

- **Edit:** change `status`, the `# title` or the body, then `jk push KEY`.
- **New subtask:** `…/subtasks/_new-<slug>/subtask.md` with a `# title`; push creates it under its folder's parent.
- **Conflict:** the field also changed in Jira since the last pull. Push never overwrites it: pull, re-apply the local
  edit, push again.
