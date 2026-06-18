#!/bin/bash
# hooks/post-stage.sh
# Runs after every stage completes. Commits artifact to git and updates pipeline state.

set -e

PROJECT=$1
STAGE=$2
ARTIFACT=$3
SUMMARY=$4

if [ -z "$PROJECT" ] || [ -z "$STAGE" ]; then
  echo "Usage: post-stage.sh <project> <stage> [artifact] [summary]"
  exit 1
fi

PROJECT_DIR="projects/$PROJECT"

echo "📦 Post-stage hook: $STAGE"

# Stage all changes
git -C "$PROJECT_DIR" add .

# Commit if there are changes
if git -C "$PROJECT_DIR" diff --staged --quiet; then
  echo "  No changes to commit for stage: $STAGE"
else
  COMMIT_MSG="${STAGE}: ${SUMMARY:-completed}"
  git -C "$PROJECT_DIR" commit -m "$COMMIT_MSG"
  echo "  ✅ Committed: $COMMIT_MSG"
fi

# Update pipeline state
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M UTC")
sed -i "s/| $STAGE.*⏳ pending.*|/| $STAGE   | ✅ done   | ${ARTIFACT:-—}   | —   | $TIMESTAMP |/" \
  "$PROJECT_DIR/pipeline-state.md" 2>/dev/null || true

echo "  ✅ Pipeline state updated"
