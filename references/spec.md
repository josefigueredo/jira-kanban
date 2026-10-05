# The epic spec

`jk create --spec <file>` reads a JSON file the agent drafts from the conversation (keep it in the scratchpad):

```json
{"epic": {"summary": "…", "description": "objetivo, problema, alcance"},
 "items": [
   {"type": "story", "area": "FE", "summary": "…", "user_story": "Como … quiero … para …",
    "acceptance": ["AC1: Dado … Cuando … Entonces …"], "done": true, "subtasks": [{"summary": "…"}]},
   {"type": "task", "area": "DEVOPS", "summary": "…", "description": "…", "started": true, "subtasks": []}]}
```

| Field | Rule |
|---|---|
| `type` | `story` only when someone benefits ("Como … quiero … para …"); otherwise `task`. Both hang from the epic as siblings; `subtasks` hang from either. There is no fourth level. |
| `area` | Becomes the `[AREA]` title prefix; `conventions.json` lists the valid ones. Do not add components, labels or story points: the project does not use them. |
| `acceptance` | Gherkin, one string per criterion (`AC1: Dado … Cuando … Entonces …`). |
| `done` | The user already finished it here (implemented, verified, merged). Assigned to the user without asking and moved to Done after creation, children before parents. Subtasks inherit it unless they say otherwise; the epic is complete only when everything under it is. |
| `started` | The user is working on it now. Assigned without asking and moved to an in-progress status (never a blocked or review one). Subtasks do not inherit it. Excludes `done`. |
| `priority` | Optional; one of `conventions.json` priorities, default `default_priority`. |

Anything neither `done` nor `started` is open: the user decides whether it is assigned to them
(`--assign-open` / `--no-assign-open`).
