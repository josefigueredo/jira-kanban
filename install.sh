#!/usr/bin/env bash
# Install the jira-kanban and jira-standup skills for Claude Code, Codex and Cursor.
#   ./install.sh
# Shared layout (same as WayOfWork): ~/.agents/skills/<name> points at this repo (jira-kanban) or at its standup/
# folder (jira-standup); ~/.claude/skills/<name>, ~/.codex/skills/<name> and ~/.cursor/skills/<name> point at
# ../../.agents/skills/<name> (measured: ~/.cursor/skills held only explicit links, so Cursor needs its own).
# Re-running is safe. A real directory with a skill's name is never replaced: the script stops with exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=("jira-kanban:" "jira-standup:standup")  # name:folder inside the repo ("" is the repo itself)
case "${1:-}" in
  -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

link() {  # link <target> <path>: create or refresh a symlink, never replace a real file or directory
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "refusing to replace $2: it is not a symlink; move it away and re-run" >&2
    return 1
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
}

status=0
for entry in "${SKILLS[@]}"; do
  NAME="${entry%%:*}"
  SUB="${entry#*:}"
  TARGET="$REPO${SUB:+/$SUB}"
  link "$TARGET" "$HOME/.agents/skills/$NAME" || exit 1
  for host in .claude .codex .cursor; do
    link "../../.agents/skills/$NAME" "$HOME/$host/skills/$NAME" || status=1
  done
  echo "skill: $NAME (Claude Code, Codex, Cursor) -> $TARGET"
done
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; jk needs it" >&2; status=1; }
exit "$status"
