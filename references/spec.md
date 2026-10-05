# The epic spec

`jk create --spec <file>` reads a JSON file the agent drafts from the conversation (keep it in the scratchpad):

```json
{"epic": {"summary": "…", "description": "objetivo, problema, alcance"},
 "items": [
   {"type": "story", "area": "FE", "summary": "…", "user_story": "Como … quiero … para …",
    "acceptance": ["AC1: Dado … Cuando … Entonces …"], "done": true, "evidence": ["1d93d8d", "https://github.com/org/repo/pull/7"], "subtasks": [{"summary": "…"}]},
   {"type": "task", "area": "DEVOPS", "summary": "…", "description": "…", "started": true, "subtasks": []}]}
```

| Field | Rule |
|---|---|
| `type` | `story` only when someone benefits ("Como … quiero … para …"); otherwise `task`. Both hang from the epic as siblings; `subtasks` hang from either. There is no fourth level. |
| `area` | Becomes the `[AREA]` title prefix; `conventions.json` lists the valid ones. Do not add components, labels or story points: the project does not use them. |
| `acceptance` | Gherkin, one string per criterion (`AC1: Dado … Cuando … Entonces …`). |
| `done` | The user already finished it here (implemented, verified, merged). Assigned to the user without asking and moved to Done after creation, children before parents. Subtasks inherit it unless they say otherwise; the epic is complete only when everything under it is. |
| `evidence` | Required with `done`: what shows it is finished. Each entry is a commit (reachable from the remote's default branch, so merged and pushed), a branch on `origin`, or a URL (a PR, a deploy, a doc). jk resolves them from the project's git repo before any write, in the dry run too, and appends them to the description as `Evidencia:` permalinks; one that does not resolve refuses the create. A subtask that inherits `done` inherits its parent's evidence. Use the commits the conversation already produced; never invent one. |
| `started` | The user is working on it now. Assigned without asking and moved to an in-progress status (never a blocked or review one). Subtasks do not inherit it. Excludes `done`. |
| `priority` | Optional; one of `conventions.json` priorities, default `default_priority`. |

Anything neither `done` nor `started` is open: the user decides whether it is assigned to them
(`--assign-open` / `--no-assign-open`).
