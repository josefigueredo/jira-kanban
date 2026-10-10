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

# blocked: the other writers
check 2 'git push origin main'
# allowed: the jtk writers ask a person in a native window (or at a terminal), so the agent may launch them
check 0 'jtk push PLATE-1 --apply'
check 0 'jtk create --spec s.json --apply'
check 0 'jtk assign PLATE-1 Ana --apply'
check 0 'jtk apply abc123def456'
check 0 'rtk jtk apply abc123def456'
check 0 'python3 /Users/x/jira-kanban/jtk.py apply abc123def456'
check 0 'cd /tmp && jtk apply abc123def456'
check 0 '/Users/x/.local/bin/jtk apply abc123def456'
# blocked: clicking or typing into the approval window for the person
check 2 "osascript -e 'tell application \"System Events\" to click button \"Apruebo 2\"' && jtk apply abc123def456"
check 2 'cliclick c:100,100; jtk apply abc123def456'
check 2 "osascript -e 'tell application \"System Events\" to keystroke \"a\"'; jtk assign PLATE-1 Ana --apply"
check 2 "peekaboo click --on Apruebo && jtk apply abc123def456"
check 2 "osascript -e 'tell application \"System Events\" to click button \"Apruebo 2\" of window 1 of process \"osascript\"'"
check 2 "osascript -e 'tell application \"System Events\" to keystroke \" \"'"
check 2 "osascript -e 'tell application \"System Events\" to perform action \"AXPress\" of button 1'"
check 2 'cliclick c:600,500'
check 2 'peekaboo click --on Apruebo'
check 0 "osascript -e 'display notification \"hola\"'"
check 0 "osascript -e 'tell application \"Finder\" to get name of startup disk'"
# blocked: a pseudo-terminal typing the approval for it
check 2 "tmux send-keys 'jtk apply abc123def456' Enter"
check 2 "expect -c 'spawn jtk apply abc123def456'"
check 2 'script -q /dev/null jtk apply abc123def456'
check 2 "python3 -c 'import pty; pty.spawn(\"jtk apply abc123def456\".split())'"
check 2 "tmux send -t s 'jtk apply abc123def456' Enter"
check 2 "tmux new-session -d -s s 'jtk apply abc123def456'"
check 2 "tmux send-keys -t s 'APRUEBO 1' Enter"
check 2 "python3 -c 'import pty; pty.spawn([\"jtk\",\"apply\",\"abc123def456\"])'"
check 2 "python3 -c 'import pexpect; pexpect.spawn(\"jtk apply abc123def456\")'"
check 2 'script /tmp/out jtk apply abc123def456'
# allowed
check 0 'jtk plan move plataforma TEAM-1 --to active'
check 0 'jtk plan revert abc123def456'
check 0 'jtk team status plataforma --list'
check 0 'jtk push PLATE-1'
check 0 'jtk assign PLATE-1 Ana'
check 0 'jtk applyx'
check 0 'git status'
check 0 'git commit -m "docs: jtk apply"'
check 0 'echo jtk apply'
check 0 'rg -n "jtk apply" docs'
check 0 'rg -n "jtk apply" scripts/'
check 0 'tmux ls'
check 0 "tmux send-keys -t s 'ls' Enter"
check 0 "tmux new-session -d -s build 'make'"

# create|push|assign --apply through a pseudo-terminal skip the approval just like apply does
check 2 'script -q /dev/null jtk push PLATE-1 --apply'
check 2 "expect -c 'spawn jtk push PLATE-1 --apply'"
check 2 "tmux new-session -d 'jtk create --spec s.json --apply'"
check 2 "python3 -c 'import pty; pty.spawn(\"jtk assign PLATE-1 Ana --apply\".split())'"
check 2 "expect -c 'spawn jk push PLATE-1 --apply'"
check 0 "expect -c 'spawn jtk push PLATE-1'"

# the old name behaves like the new one: old scripts and shell history still say jk
check 0 'jk apply abc123def456'
check 0 'jk push PLATE-1 --apply'
check 2 "tmux send-keys 'jk apply abc123def456' Enter"
check 2 "osascript -e 'tell application \"System Events\" to click button \"Apruebo 1\"'; jk apply abc123def456"
check 0 'python3 /Users/x/jira-kanban/jk.py apply abc123def456'
check 0 'jk plan move plataforma TEAM-1 --to active'

echo "$((total - wrong))/$total cases behaved as expected"
[ "$wrong" -eq 0 ]
