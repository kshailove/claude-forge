#!/bin/bash
# hooks/post-stage.sh
# Runs after every stage. Commits to the project's own repo and updates pipeline state.

set -e

PROJECT=$1
STAGE=$2
ARTIFACT=$3
SUMMARY=$4

if [ -z "$PROJECT" ] || [ -z "$STAGE" ]; then
  echo "Usage: post-stage.sh <project> <stage> [artifact] [summary]"
  exit 1
fi

# Locate the claude-forge root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORGE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$FORGE_ROOT/projects.conf"

# Resolve project path from projects.conf
RAW_PATH=$(grep "^$PROJECT=" "$CONFIG" | cut -d= -f2-)
if [ -z "$RAW_PATH" ]; then
  echo "❌ Project '$PROJECT' not found in projects.conf"
  exit 1
fi

if [[ "$RAW_PATH" = /* ]]; then
  PROJECT_DIR="$RAW_PATH"
else
  PROJECT_DIR="$FORGE_ROOT/$RAW_PATH"
fi

STATE_FILE="$PROJECT_DIR/pipeline-state.md"

echo "📦 Post-stage hook: $STAGE"

# Commit to the project's own git repo
git -C "$PROJECT_DIR" add .

if git -C "$PROJECT_DIR" diff --staged --quiet; then
  echo "  No changes to commit for stage: $STAGE"
else
  COMMIT_MSG="${STAGE}: ${SUMMARY:-completed}"
  git -C "$PROJECT_DIR" commit -m "$COMMIT_MSG"
  echo "  ✅ Committed: $COMMIT_MSG"
fi

# Update pipeline state.
# Uses a temp file + awk to avoid sed -i portability issues between macOS and Linux.
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M UTC")
ARTIFACT_DISPLAY="${ARTIFACT:-—}"
TMPFILE=$(mktemp)

awk -v stage="$STAGE" -v artifact="$ARTIFACT_DISPLAY" -v ts="$TIMESTAMP" '
  BEGIN { FS="|"; OFS="|" }
  /^\|/ && $2 ~ stage && $3 ~ "pending" {
    $3 = " ✅ done   "
    $4 = " " artifact " "
    $6 = " " ts " "
    print; next
  }
  { print }
' "$STATE_FILE" > "$TMPFILE" && mv "$TMPFILE" "$STATE_FILE"

echo "  ✅ Pipeline state updated"
