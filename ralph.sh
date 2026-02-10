#!/bin/bash
# Ralph - Autonomous AI agent loop for Chess Speedrun
# Usage: ./ralph.sh [options] [max_iterations]
#
# Options:
#   --tool claude        Tool to use (only claude supported)
#   --cutoff-hour HOUR   Stop after this hour (default: 4, meaning 4 AM)
#   --no-cutoff          Disable time-based cutoff
#   --force              Skip weekly usage warning prompt

set -e

# ─── Defaults ────────────────────────────────────────────────────────────────
TOOL="claude"
MAX_ITERATIONS=10
CUTOFF_HOUR=4
CUTOFF_ENABLED=true
FORCE_CONTINUE=false

# ─── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --tool)
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    --cutoff-hour)
      CUTOFF_HOUR="$2"
      shift 2
      ;;
    --cutoff-hour=*)
      CUTOFF_HOUR="${1#*=}"
      shift
      ;;
    --no-cutoff)
      CUTOFF_ENABLED=false
      shift
      ;;
    --force)
      FORCE_CONTINUE=true
      shift
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      fi
      shift
      ;;
  esac
done

if [[ "$TOOL" != "claude" ]]; then
  echo "Error: This project only supports Claude Code. Use: ./ralph.sh [max_iterations]"
  exit 1
fi

# ─── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup_ralph_markers() {
  rm -f "$SCRIPT_DIR/.ralph-active" "$SCRIPT_DIR/.ralph-passes-count" "$SCRIPT_DIR/.ralph-story-complete" 2>/dev/null
}
trap 'cleanup_ralph_markers' EXIT

PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"
RALPH_CONFIG="$SCRIPT_DIR/.omc/state/ralph-config.json"
STATS_CACHE="$HOME/.claude/stats-cache.json"

# ─── Check prerequisites ────────────────────────────────────────────────────
if ! command -v claude &> /dev/null; then
  echo "Error: Claude Code not found. Install: npm install -g @anthropic-ai/claude-code"
  exit 1
fi

if ! command -v jq &> /dev/null; then
  echo "Error: jq not found. Install: brew install jq"
  exit 1
fi

if ! command -v python3 &> /dev/null; then
  echo "Error: python3 not found. Required for time calculations."
  exit 1
fi

if [ ! -f "$PRD_FILE" ]; then
  echo "Error: prd.json not found at $PRD_FILE"
  echo "Create a prd.json first. See prd.json.example for format."
  exit 1
fi

# ─── Config file handling ────────────────────────────────────────────────────
init_config() {
  if [ ! -f "$RALPH_CONFIG" ]; then
    mkdir -p "$(dirname "$RALPH_CONFIG")"
    cat > "$RALPH_CONFIG" <<'CONFIGEOF'
{
  "weeklyTokenLimit": 500000,
  "warningThreshold": 0.8
}
CONFIGEOF
    echo "Created $RALPH_CONFIG with defaults. Edit weeklyTokenLimit for your plan:"
    echo "  Pro: ~500000  |  Max: ~2000000"
    echo ""
  fi
}

get_config_value() {
  local key="$1"
  local default="$2"
  jq -r ".$key // $default" "$RALPH_CONFIG" 2>/dev/null || echo "$default"
}

# ─── Feature 1: Rate Limit Retry ────────────────────────────────────────────
# Detects rate limit messages in claude output, parses reset time,
# sleeps until reset + 5 minutes, retries up to 3 times per iteration.
#
# Known patterns:
#   "out of extra usage · resets 4:30am (Asia/Calcutta)"
#   "hit your limit"

handle_rate_limit() {
  local output="$1"

  # Check for rate limit patterns
  if ! echo "$output" | grep -qi "out of extra usage\|hit your limit"; then
    return 1  # Not rate-limited
  fi

  echo ""
  echo "[Ralph] Rate limit detected at $(date '+%Y-%m-%d %H:%M:%S')"

  # Try to extract reset time: "resets <time> (<timezone>)"
  local reset_match
  reset_match=$(echo "$output" | grep -oiE 'resets [0-9]{1,2}:[0-9]{2}\s*(am|pm)\s*\([A-Za-z/_]+\)' | head -1)

  if [ -n "$reset_match" ]; then
    echo "[Ralph] Found reset info: $reset_match"

    # Extract time and timezone components
    local reset_time reset_tz
    reset_time=$(echo "$reset_match" | grep -oiE '[0-9]{1,2}:[0-9]{2}\s*(am|pm)')
    reset_tz=$(echo "$reset_match" | grep -oE '\([A-Za-z/_]+\)' | tr -d '()')

    if [ -n "$reset_time" ] && [ -n "$reset_tz" ]; then
      # Use Python to compute seconds until reset + 5 min buffer
      local wait_seconds
      wait_seconds=$(python3 -c "
import sys
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

reset_time_str = '$reset_time'.strip().lower()
tz_str = '$reset_tz'

try:
    tz = ZoneInfo(tz_str)
except Exception:
    print(-1)
    sys.exit(0)

now = datetime.now(tz)

# Parse the reset time (e.g., '4:30am')
from datetime import time as dt_time
import re
m = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)', reset_time_str)
if not m:
    print(-1)
    sys.exit(0)

hour = int(m.group(1))
minute = int(m.group(2))
ampm = m.group(3)

if ampm == 'pm' and hour != 12:
    hour += 12
elif ampm == 'am' and hour == 12:
    hour = 0

# Build reset datetime for today in that timezone
reset_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

# If reset time is in the past, it means tomorrow
if reset_dt <= now:
    reset_dt += timedelta(days=1)

# Add 5 minute buffer
reset_dt += timedelta(minutes=5)

diff = (reset_dt - now).total_seconds()
print(int(max(diff, 60)))  # At least 60 seconds
" 2>/dev/null)

      if [ -n "$wait_seconds" ] && [ "$wait_seconds" -gt 0 ] 2>/dev/null; then
        local wait_minutes=$((wait_seconds / 60))
        local resume_time
        resume_time=$(date -v+"${wait_seconds}S" '+%H:%M:%S' 2>/dev/null || date -d "+${wait_seconds} seconds" '+%H:%M:%S' 2>/dev/null || echo "unknown")
        echo "[Ralph] Sleeping ${wait_minutes} minutes (until ~${resume_time}, 5 min after reset)"
        sleep "$wait_seconds"
        return 0  # Handled, should retry
      fi
    fi
  fi

  # Fallback: couldn't parse reset time, sleep 30 minutes
  echo "[Ralph] Could not parse reset time. Sleeping 30 minutes as fallback."
  sleep 1800
  return 0  # Handled, should retry
}

# ─── Feature 2: Time-Based Cutoff ───────────────────────────────────────────
# Stops the loop if current hour is between CUTOFF_HOUR and 9 AM,
# ensuring a fresh context window for the morning session.

check_time_cutoff() {
  if [ "$CUTOFF_ENABLED" != "true" ]; then
    return 0
  fi

  local current_hour
  current_hour=$(date +%H | sed 's/^0//')  # Remove leading zero

  # Stop if hour >= cutoff AND hour < 9 (i.e., in the early morning dead zone)
  if [ "$current_hour" -ge "$CUTOFF_HOUR" ] && [ "$current_hour" -lt 9 ]; then
    echo ""
    echo "==============================================================="
    echo "  Ralph Time Cutoff: $(date '+%H:%M %Z')"
    echo "  Stopping to ensure fresh context by 9 AM."
    echo "  (Cutoff hour: ${CUTOFF_HOUR}:00, override with --no-cutoff)"
    echo "==============================================================="
    exit 0
  fi
}

# ─── Feature 3: Weekly Usage Warning ────────────────────────────────────────
# Reads ~/.claude/stats-cache.json, sums tokens for the current week,
# warns if usage exceeds the configured threshold percentage.

check_weekly_usage() {
  if [ ! -f "$STATS_CACHE" ]; then
    echo "[Ralph] No stats cache found at $STATS_CACHE - skipping usage check."
    return 0
  fi

  local weekly_limit warning_threshold
  weekly_limit=$(get_config_value "weeklyTokenLimit" "500000")
  warning_threshold=$(get_config_value "warningThreshold" "0.8")

  # Use Python to sum tokens for current week (Mon-Sun)
  local usage_result
  usage_result=$(python3 -c "
import json, sys
from datetime import datetime, timedelta

with open('$STATS_CACHE') as f:
    stats = json.load(f)

daily_tokens = stats.get('dailyModelTokens', [])

# Get current week boundaries (Monday to Sunday)
today = datetime.now().date()
monday = today - timedelta(days=today.weekday())
sunday = monday + timedelta(days=6)

total = 0
for entry in daily_tokens:
    if not isinstance(entry, dict):
        continue
    date_str = entry.get('date', '')
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        continue
    if monday <= entry_date <= sunday:
        tokens_by_model = entry.get('tokensByModel', {})
        for model, count in tokens_by_model.items():
            if isinstance(count, (int, float)):
                total += int(count)

print(total)
" 2>/dev/null)

  if [ -z "$usage_result" ] || ! [[ "$usage_result" =~ ^[0-9]+$ ]]; then
    echo "[Ralph] Could not read weekly usage - skipping check."
    return 0
  fi

  local threshold_tokens
  threshold_tokens=$(python3 -c "print(int($weekly_limit * $warning_threshold))")

  if [ "$usage_result" -ge "$threshold_tokens" ]; then
    local pct
    pct=$(python3 -c "print(round($usage_result / $weekly_limit * 100))")

    echo ""
    echo "==============================================================="
    echo "  WARNING: Weekly token usage at ${pct}%"
    echo "  Used: $(printf "%'d" "$usage_result") / $(printf "%'d" "$weekly_limit") tokens"
    echo "  You may want to stop the ralph loop to preserve remaining quota."
    echo "==============================================================="

    if [ "$FORCE_CONTINUE" = "true" ]; then
      echo "[Ralph] --force flag set, continuing anyway."
      return 0
    fi

    echo ""
    read -r -p "Continue anyway? [y/N] " response
    case "$response" in
      [yY]|[yY][eE][sS])
        echo "[Ralph] Continuing by user choice."
        return 0
        ;;
      *)
        echo "[Ralph] Stopping to preserve weekly quota."
        exit 0
        ;;
    esac
  else
    local pct
    pct=$(python3 -c "print(round($usage_result / $weekly_limit * 100))")
    echo "[Ralph] Weekly token usage: ${pct}% ($(printf "%'d" "$usage_result") / $(printf "%'d" "$weekly_limit"))"
  fi
}

# ─── Archive previous run if branch changed ─────────────────────────────────
if [ -f "$PRD_FILE" ] && [ -f "$LAST_BRANCH_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  LAST_BRANCH=$(cat "$LAST_BRANCH_FILE" 2>/dev/null || echo "")

  if [ -n "$CURRENT_BRANCH" ] && [ -n "$LAST_BRANCH" ] && [ "$CURRENT_BRANCH" != "$LAST_BRANCH" ]; then
    DATE=$(date +%Y-%m-%d)
    FOLDER_NAME=$(echo "$LAST_BRANCH" | sed 's|^ralph/||')
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"

    echo "Archiving previous run: $LAST_BRANCH"
    mkdir -p "$ARCHIVE_FOLDER"
    [ -f "$PRD_FILE" ] && cp "$PRD_FILE" "$ARCHIVE_FOLDER/"
    [ -f "$PROGRESS_FILE" ] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    echo "   Archived to: $ARCHIVE_FOLDER"

    echo "# Ralph Progress Log" > "$PROGRESS_FILE"
    echo "Started: $(date)" >> "$PROGRESS_FILE"
    echo "---" >> "$PROGRESS_FILE"
  fi
fi

# Track current branch
if [ -f "$PRD_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  if [ -n "$CURRENT_BRANCH" ]; then
    echo "$CURRENT_BRANCH" > "$LAST_BRANCH_FILE"
  fi
fi

# Initialize progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Progress Log" > "$PROGRESS_FILE"
  echo "Started: $(date)" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

# ─── Startup checks ─────────────────────────────────────────────────────────
init_config
check_weekly_usage

echo ""
echo "Starting Ralph - Tool: $TOOL - Max iterations: $MAX_ITERATIONS"
echo "  Cutoff: $([ "$CUTOFF_ENABLED" = "true" ] && echo "${CUTOFF_HOUR}:00" || echo "disabled")"
echo "PRD: $PRD_FILE"
echo "Progress: $PROGRESS_FILE"

# ─── Main loop (while-based for rate limit retry support) ────────────────────
ITERATION=1
RATE_LIMIT_RETRIES=0
MAX_RATE_LIMIT_RETRIES=3

while [ "$ITERATION" -le "$MAX_ITERATIONS" ]; do
  echo ""
  echo "==============================================================="
  echo "  Ralph Iteration $ITERATION of $MAX_ITERATIONS (claude)"
  echo "  $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "==============================================================="

  # Check time cutoff before each iteration
  check_time_cutoff

  # Check if all stories are already complete
  REMAINING=$(jq '[.userStories[] | select(.passes == false)] | length' "$PRD_FILE")
  if [ "$REMAINING" -eq 0 ]; then
    echo "All stories already complete!"
    exit 0
  fi
  echo "Remaining stories: $REMAINING"

  # Ralph marker files for hook coordination
  touch "$SCRIPT_DIR/.ralph-active"
  jq '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE" > "$SCRIPT_DIR/.ralph-passes-count"
  rm -f "$SCRIPT_DIR/.ralph-story-complete"

  # Run Claude Code with the CLAUDE.md instructions
  OUTPUT=$(claude --dangerously-skip-permissions --print < "$SCRIPT_DIR/CLAUDE.dev.md" 2>&1 | tee /dev/stderr) || true

  # Check if session ended due to story completion hook
  if [ -f "$SCRIPT_DIR/.ralph-story-complete" ]; then
    echo ""
    echo "[Ralph] Story completion detected! Auto-committing bookkeeping..."
    cd "$SCRIPT_DIR"
    git add prd.json progress.txt 2>/dev/null
    git diff --cached --quiet 2>/dev/null || \
      git commit -m "chore: ralph bookkeeping - story marked complete" 2>/dev/null || true
    rm -f "$SCRIPT_DIR/.ralph-story-complete" "$SCRIPT_DIR/.ralph-active" "$SCRIPT_DIR/.ralph-passes-count"
    RATE_LIMIT_RETRIES=0
    ITERATION=$((ITERATION + 1))
    echo "[Ralph] Iteration $((ITERATION - 1)) complete (early termination). Continuing..."
    sleep 2
    continue
  fi

  # Normal cleanup
  rm -f "$SCRIPT_DIR/.ralph-active" "$SCRIPT_DIR/.ralph-passes-count"

  # Check for completion signal
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "Ralph completed all tasks!"
    echo "Completed at iteration $ITERATION of $MAX_ITERATIONS"
    exit 0
  fi

  # Check for rate limiting
  if handle_rate_limit "$OUTPUT"; then
    RATE_LIMIT_RETRIES=$((RATE_LIMIT_RETRIES + 1))
    if [ "$RATE_LIMIT_RETRIES" -ge "$MAX_RATE_LIMIT_RETRIES" ]; then
      echo ""
      echo "[Ralph] Hit max rate limit retries ($MAX_RATE_LIMIT_RETRIES) for iteration $ITERATION."
      echo "[Ralph] Exiting to avoid infinite waiting. Resume later with: ./ralph.sh $((MAX_ITERATIONS - ITERATION + 1))"
      exit 1
    fi
    echo "[Ralph] Retrying iteration $ITERATION (attempt $((RATE_LIMIT_RETRIES + 1)) of $MAX_RATE_LIMIT_RETRIES)..."
    continue  # Retry same iteration without incrementing
  fi

  # Success - reset retry counter and advance
  RATE_LIMIT_RETRIES=0
  ITERATION=$((ITERATION + 1))

  echo "Iteration $((ITERATION - 1)) complete. Continuing..."
  sleep 2
done

echo ""
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all tasks."
echo "Check $PROGRESS_FILE for status."
exit 1
