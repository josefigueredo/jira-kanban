# The local kanban

```
.jira-team-kit/<EPIC>/epic.md
.jira-team-kit/<EPIC>/stories/<KEY>/story.md
.jira-team-kit/<EPIC>/tasks/<KEY>/task.md
.jira-team-kit/<EPIC>/<stories|tasks>/<KEY>/subtasks/<KEY>/subtask.md
.jira-team-kit/<EPIC>/.sync.json          # baseline of the last pull; push compares against it
.jira-team-kit/jira-writes.jsonl          # every write to Jira: time, command, issue, change (keep it out of git)
.jira-team-kit/.create-progress-*.json    # keys of a create in flight, removed when it ends (keep it out of git)
.jira-team-kit/conventions.json           # optional project override of the skill's conventions.json
```

A project that still has the old `.jira-kanban/` folder gets it moved to `.jira-team-kit/` the first time any `jtk` command
looks for its data (the move keeps every file as it was). If both folders exist the new one is used and the old one is left
alone; if the move fails, the old folder keeps working.

Each `.md` is written from `templates/issue.md`: a front matter (`key`, `kind`, `issuetype`, `status`, `category`, `blocked`, `parent`, `url`),
the title as `# …` and the description below. The last sync time lives only in `.sync.json`, so a pull with
nothing new leaves every `.md` unchanged. The folder decides kind and parent; the front matter never
moves an issue.

- **Edit:** change `status`, the `# title` or the body, then `jtk push KEY`. An edited body goes to Jira only if it keeps
  the sections of `templates/description.md` (Por qué, Qué, Hecho cuando), all filled in; push lists what is missing as
  `invalid`. A card mirrored from Jira with free text can still change status or title.
- **New subtask:** `…/subtasks/_new-<slug>/subtask.md` with a `# title` and the three sections, written over the lines
  of `templates/description.md` (`Por qué: {{why}}` becomes `Por qué: …`); a placeholder left as is stops the create.
  Push creates it under its folder's parent.
- **Conflict:** the field also changed in Jira since the last pull. Push never overwrites it: pull, re-apply the local
  edit, push again.
