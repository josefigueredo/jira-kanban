#!/usr/bin/env bash
# Install jtk and its skills for Claude Code, Codex and Cursor.
#   ./install.sh               the read-only skills: jira-standup and jira-em
#   ./install.sh --with-write  also the skills that write to Jira: jira-team-kit and jira-em-ops
# CLI: ~/.local/bin/jtk points at jtk.py; the skills call `jtk`, never another skill's folder.
# Skills (same layout as WayOfWork): ~/.agents/skills/<name> points at this repo (jira-team-kit) or at its own folder
# (jira-standup/, jira-em/, jira-em-ops/); ~/.claude/skills/<name>, ~/.codex/skills/<name> and ~/.cursor/skills/<name> point at
# ../../.agents/skills/<name> (measured: ~/.cursor/skills held only explicit links, so Cursor needs its own).
# Re-running is safe and never removes a skill installed before. A real file or directory where a link goes is
# never replaced: the script stops with exit 1.
# The old command name jk and the old skill names jira-kanban and jira-toolkit are not kept: a link to this repo is removed and the data
# move is printed, not done.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=("jira-standup:jira-standup" "jira-em:jira-em")  # name:folder inside the repo ("" is the repo itself)
case "${1:-}" in
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  --with-write) SKILLS+=("jira-team-kit:" "jira-em-ops:jira-em-ops") ;;
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
chmod +x "$REPO/jtk.py"
link "$REPO/jtk.py" "$HOME/.local/bin/jtk" || status=1
echo "cli: jtk -> $REPO/jtk.py"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "note: add ~/.local/bin to PATH to use jtk" >&2 ;; esac
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; jtk needs it" >&2; status=1; }
# The command used to be called jk. Remove its link only when it is this repo's own; never touch anything else.
OLD="$HOME/.local/bin/jk"
if [ -L "$OLD" ]; then
  if [ "$(readlink "$OLD")" = "$REPO/jk.py" ]; then
    rm "$OLD"
    echo "removed the old link ~/.local/bin/jk (the command is jtk now)"
  else
    echo "note: ~/.local/bin/jk points somewhere else and was left alone" >&2
  fi
elif [ -e "$OLD" ]; then
  echo "note: ~/.local/bin/jk is not a symlink and was left alone" >&2
fi
# The root skill used to be called jira-kanban, and for a moment jira-toolkit. Remove those links only when they are
# this repo's own.
for name in jira-kanban jira-toolkit; do
  for host in .agents .claude .codex .cursor; do
    old="$HOME/$host/skills/$name"
    if [ -L "$old" ]; then
      case "$(readlink "$old")" in
        "$REPO"|"../../.agents/skills/$name") rm "$old"; echo "removed the old skill link $old (the skill is jira-team-kit now)" ;;
        *) echo "note: $old points somewhere else and was left alone" >&2 ;;
      esac
    fi
  done
done
# Data is renamed by the person, never by this script: it prints the exact commands.
migrate() {  # migrate <old> <new> (both written with ~)
  local o="${1/#\~/$HOME}" n="${2/#\~/$HOME}"
  [ -e "$o" ] || return 0
  if [ -e "$n" ]; then
    echo "note: both $1 and $2 exist; merge them by hand, nothing was moved" >&2
  else
    echo "migrate: mv $1 $2"
  fi
}
migrate "~/.config/jk" "~/.config/jtk"
migrate "~/.local/state/jk" "~/.local/state/jtk"
for name in CONFIG STATE; do
  var="JK_${name}_DIR"
  if [ -n "${!var:-}" ]; then echo "note: $var is no longer read; use JTK_${name}_DIR" >&2; fi
done
exit "$status"
