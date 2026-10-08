# The epic spec

`jk create --spec <file>` reads a JSON file the agent drafts from the conversation (keep it in the scratchpad):

```json
{"epic": {"summary": "…", "why": "…", "what": "…", "done_when": "…"},
 "items": [
   {"type": "story", "area": "FE", "summary": "…", "user_story": "Como … quiero … para …",
    "why": "…", "what": "…", "done_when": "…", "acceptance": ["AC1: Dado … Cuando … Entonces …"],
    "done": true, "evidence": ["1d93d8d", "https://github.com/org/repo/pull/7"],
    "subtasks": [{"summary": "…", "why": "…", "what": "…", "done_when": "…"}]},
   {"type": "task", "area": "DEVOPS", "summary": "…", "why": "…", "what": "…", "done_when": "…", "started": true}]}
```

| Field | Rule |
|---|---|
| `type` | `story` only when someone benefits ("Como … quiero … para …"); otherwise `task`. Both hang from the epic as siblings; `subtasks` hang from either. There is no fourth level. |
| `why`, `what`, `done_when` | Required on the epic, every item and every subtask; see below. jk builds the Jira description from them with `templates/description.md`; a free `description` key is refused. |
| `how`, `out_of_scope`, `assumptions`, `edge_cases`, `references` | Optional on any issue: text, or a list of strings that jk turns into bullets. Left out of the card when empty. Fill them only from what the conversation already says; never research to fill one. |
| `area` | Becomes the `[AREA]` title prefix; `conventions.json` lists the valid ones. Do not add components, labels or story points: the project does not use them. |
| `acceptance` | Gherkin, one string per criterion (`AC1: Dado … Cuando … Entonces …`). |
| `done` | The user already finished it here: implemented and verified; for a contribution to another team's repo, delivered as an opened PR (their merge is their decision). Assigned to the user without asking and moved to Done after creation, children before parents. Subtasks inherit it unless they say otherwise; the epic is complete only when everything under it is. |
| `evidence` | Required with `done`: what shows it is finished. Each entry is a commit (reachable from the remote's default branch, so merged and pushed), a branch on `origin`, or a URL (a PR, a deploy, a doc). jk resolves them from the project's git repo before any write, in the dry run too, and lists them as permalinks in the description's `Evidencia:` section; one that does not resolve refuses the create. A subtask that inherits `done` inherits its parent's evidence. Use the commits the conversation already produced; never invent one. |
| `started` | The user is working on it now. Assigned without asking and moved to an in-progress status (never a blocked or review one). Subtasks do not inherit it. Excludes `done`. |
| `priority` | Optional; one of `conventions.json` priorities, default `default_priority`. |
| `assignee` | Optional; the name, email or accountId of the person who owns it, on the epic, an item or a subtask (a subtask inherits its item's). Wins over `done`, `started` and `--assign-open`. jk looks the person up while planning, in the dry run too, and refuses the create if the name matches nobody or several people. Not sure who it is? Run `jk who "<name>" --jira-project KEY` first. |

Anything neither `done` nor `started` is open: the user decides whether it is assigned to them
(`--assign-open` / `--no-assign-open`).

## The description

The run is agentic, but the description is read, followed and corrected by a person who was not in the conversation.
Each field is prose in the team's language, plain paragraphs and `- ` bullets (the preview and Jira render both), and
fills one section of `templates/description.md`:

- **`why` → Por qué:** the problem or the need, as observed: what fails, for whom, where (`file:line`, the error, the
  measured value). Gloss every ID from the conversation (a branch, a group letter, a ticket) the first time it appears.
- **`what` → Qué:** the change and its scope. For a subtask, its own slice, not the parent's text again.
- **`how` → Cómo:** the approach, when it is already decided (the file to change, the tool, the order).
- **`out_of_scope` → Fuera de alcance:** what this issue leaves out on purpose, so nobody takes it for forgotten.
- **`assumptions` → Supuestos:** what the plan takes as true without having checked it.
- **`edge_cases` → Casos borde:** the exceptions the conversation already named.
- **`done_when` → Hecho cuando:** how a person checks it without asking you. For a `done` item, what was done and how it
  was verified (the tests, the run); jk adds the evidence links itself.
- **`references` → Referencias:** where to look: files (`file:line`), docs, designs, APIs. Not the commits that close
  it: those go in `evidence`.

A story's `user_story` opens the description and its `acceptance` closes it. The epic says the goal, the problem and
the scope, and how its children split the work. A field that only restates the title means the item is not understood
yet; ask before drafting.
