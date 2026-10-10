#!/usr/bin/env bash
# Install jk and its skills for Claude Code, Codex and Cursor.
#   ./install.sh               the read-only skills: jira-standup and jira-em
#   ./install.sh --with-write  also the skills that write to Jira: jira-kanban and jira-em-ops
# CLI: ~/.local/bin/jk points at jk.py; the skills call `jk`, never another skill's folder.
# Skills (same layout as WayOfWork): ~/.agents/skills/<name> points at this repo (jira-kanban) or at its standup/
# folder (jira-standup); ~/.claude/skills/<name>, ~/.codex/skills/<name> and ~/.cursor/skills/<name> point at
# ../../.agents/skills/<name> (measured: ~/.cursor/skills held only explicit links, so Cursor needs its own).
# Re-running is safe and never removes a skill installed before. A real file or directory where a link goes is
# never replaced: the script stops with exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=("jira-standup:standup" "jira-em:em")  # name:folder inside the repo ("" is the repo itself)
case "${1:-}" in
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  --with-write) SKILLS+=("jira-kanban:" "jira-em-ops:ops") ;;
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
chmod +x "$REPO/jk.py"
link "$REPO/jk.py" "$HOME/.local/bin/jk" || status=1
echo "cli: jk -> $REPO/jk.py"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "note: add ~/.local/bin to PATH to use jk" >&2 ;; esac
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; jk needs it" >&2; status=1; }
exit "$status"
