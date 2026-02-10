#!/bin/bash
# PostToolUse hook: Terminate Claude session when a ralph story is marked complete.
# Outputs {"continue": false} to gracefully end the session so ralph.sh can advance.
#
# Gates:
#   1. .ralph-active must exist (only during ralph runs)
#   2. Tool must have edited prd.json
#   3. passes count must have increased vs snapshot

INPUT=$(cat)

# Gate 1: Only during ralph runs
[ ! -f "$CLAUDE_PROJECT_DIR/.ralph-active" ] && exit 0

# Gate 2: Only prd.json edits
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.file // empty' 2>/dev/null)
[[ "$FILE_PATH" != *prd.json ]] && exit 0

# Gate 3: Did passes count increase?
CURRENT=$(jq '[.userStories[] | select(.passes == true)] | length' "$CLAUDE_PROJECT_DIR/prd.json" 2>/dev/null || echo 0)
SNAPSHOT=$(cat "$CLAUDE_PROJECT_DIR/.ralph-passes-count" 2>/dev/null || echo 0)
[ "$CURRENT" -le "$SNAPSHOT" ] && exit 0

# Story completed! Signal ralph.sh and stop Claude
echo "$CURRENT" > "$CLAUDE_PROJECT_DIR/.ralph-story-complete"
echo '{"continue": false, "stopReason": "Story marked complete. Ralph loop advancing to next iteration."}'
