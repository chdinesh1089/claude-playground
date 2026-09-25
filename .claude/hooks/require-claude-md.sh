#!/usr/bin/env bash
# PreToolUse(Bash) hook: block `git commit` when the commit changes project
# files but CLAUDE.md isn't part of it. Bot-generated output is exempt.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // ""')
printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)' || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}"

# Files this commit will contain. If the same command also stages files
# (`git add … && git commit`, `commit -a`), count working-tree changes too.
files=$(git diff --cached --name-only)
if printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+add|commit[^;&|]*[[:space:]]-[a-zA-Z]*a|--all'; then
  files=$(printf '%s\n%s\n' "$files" "$(git status --porcelain --untracked-files=all | cut -c4-)")
fi

relevant=$(printf '%s\n' "$files" | grep -Ev '^(data/|index\.html$|aiapps/flight-price-tracker/index\.html$|aiapps/daily-briefing/[^/]+\.html$)' | grep -v '^$' || true)
[ -z "$relevant" ] && exit 0
printf '%s\n' "$files" | grep -qx 'CLAUDE.md' && exit 0

jq -n --arg files "$(printf '%s\n' "$relevant" | head -10 | paste -sd, -)" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("CLAUDE.md is not staged, but this commit changes: " + $files + ". Update CLAUDE.md (fix stale sections and add a Changelog line), `git add CLAUDE.md`, then commit again.")
  }
}'
