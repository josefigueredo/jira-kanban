#!/usr/bin/env bash
# Runs a list of commands through a git-guardrails hook and compares the exit code (2 = blocked, 0 = allowed).
#   tools/check-guardrails.sh [HOOK]    HOOK defaults to ~/.claude/hooks/git-guardrails.sh
# Exit: 0 every case behaved, 1 some case did not, 2 it could not run. Not part of `unittest discover`: the hook is the
# user's file and may not be updated yet.
set -uo pipefail

HOOK="${1:-$HOME/.claude/hooks/git-guardrails.sh}"
[ -x "$HOOK" ] || { echo "no executable hook at $HOOK" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

total=0
wrong=0
check() {  # check <expected exit code> <command line>
  local want="$1" cmd="$2" got
  got=$(jq -n --arg c "$cmd" '{tool_input: {command: $c}}' | "$HOOK" >/dev/null 2>&1; echo $?)
  total=$((total + 1))
  if [ "$got" != "$want" ]; then
    wrong=$((wrong + 1))
    echo "WRONG want=$want got=$got :: $cmd"
  fi
}

# blocked: the writers that already existed
check 2 'git push origin main'
check 2 'jk push PLATE-1 --apply'
check 2 'jk create --spec s.json --apply'
check 2 'jk assign PLATE-1 Ana --apply'
# blocked: applying a plan, behind every prefix the hook accepts
check 2 'jk apply abc123def456'
check 2 'rtk jk apply abc123def456'
check 2 'python3 /Users/x/jira-kanban/jk.py apply abc123def456'
check 2 'cd /tmp && jk apply abc123def456'
check 2 '/Users/x/.local/bin/jk apply abc123def456'
# blocked: a pseudo-terminal typing the approval for it
check 2 "tmux send-keys 'jk apply abc123def456' Enter"
check 2 "expect -c 'spawn jk apply abc123def456'"
check 2 'script -q /dev/null jk apply abc123def456'
check 2 "python3 -c 'import pty; pty.spawn(\"jk apply abc123def456\".split())'"
# allowed
check 0 'jk plan move plataforma TEAM-1 --to active'
check 0 'jk plan revert abc123def456'
check 0 'jk team status plataforma --list'
check 0 'jk push PLATE-1'
check 0 'jk assign PLATE-1 Ana'
check 0 'jk applyx'
check 0 'git status'
check 0 'git commit -m "docs: jk apply"'
check 0 'echo jk apply'
check 0 'rg -n "jk apply" docs'

echo "$((total - wrong))/$total cases behaved as expected"
[ "$wrong" -eq 0 ]
