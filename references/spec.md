# The epic spec

`jk create --spec <file>` reads a JSON file the agent drafts from the conversation (keep it in the scratchpad):

```json
{"epic": {"summary": "…", "description": "…"},
 "items": [
   {"type": "story", "area": "FE", "summary": "…", "user_story": "Como … quiero … para …",
    "description": "…", "acceptance": ["AC1: Dado … Cuando … Entonces …"], "done": true, "evidence": ["1d93d8d", "https://github.com/org/repo/pull/7"], "subtasks": [{"summary": "…", "description": "…"}]},
   {"type": "task", "area": "DEVOPS", "summary": "…", "description": "…", "started": true, "subtasks": []}]}
```

| Field | Rule |
|---|---|
| `type` | `story` only when someone benefits ("Como … quiero … para …"); otherwise `task`. Both hang from the epic as siblings; `subtasks` hang from either. There is no fourth level. |
| `description` | Required on the epic, every item and every subtask; see below. |
| `area` | Becomes the `[AREA]` title prefix; `conventions.json` lists the valid ones. Do not add components, labels or story points: the project does not use them. |
| `acceptance` | Gherkin, one string per criterion (`AC1: Dado … Cuando … Entonces …`). |
| `done` | The user already finished it here (implemented, verified, merged). Assigned to the user without asking and moved to Done after creation, children before parents. Subtasks inherit it unless they say otherwise; the epic is complete only when everything under it is. |
| `evidence` | Required with `done`: what shows it is finished. Each entry is a commit (reachable from the remote's default branch, so merged and pushed), a branch on `origin`, or a URL (a PR, a deploy, a doc). jk resolves them from the project's git repo before any write, in the dry run too, and appends them to the description as `Evidencia:` permalinks; one that does not resolve refuses the create. A subtask that inherits `done` inherits its parent's evidence. Use the commits the conversation already produced; never invent one. |
| `started` | The user is working on it now. Assigned without asking and moved to an in-progress status (never a blocked or review one). Subtasks do not inherit it. Excludes `done`. |
| `priority` | Optional; one of `conventions.json` priorities, default `default_priority`. |

Anything neither `done` nor `started` is open: the user decides whether it is assigned to them
(`--assign-open` / `--no-assign-open`).

## The description

The run is agentic, but the description is read, followed and corrected by a person who was not in the conversation.
Write it as prose in the team's language, plain paragraphs and `- ` bullets (the preview and Jira render both):

- **Why:** the problem or the need, as observed: what fails, for whom, where (`file:line`, the error, the measured
  value). Gloss every ID from the conversation (a branch, a group letter, a ticket) the first time it appears.
- **What:** the change, its scope and what stays out. For a subtask, its own slice, not the parent's text again.
- **Done when:** how a person checks it without asking you. For a `done` item, what was done and how it was verified
  (the tests, the run); jk appends the evidence links itself.

The epic says the goal, the problem and the scope, and how its children split the work. A title is not a
description: if the paragraph only restates it, the item is not understood yet; ask before drafting.
