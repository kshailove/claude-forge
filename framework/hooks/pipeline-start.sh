#!/bin/bash
# hooks/pipeline-start.sh
# Runs at the start of every pipeline.
# Resolves the project path from projects.conf, sets up the project's own git repo,
# and creates the directory structure + pipeline-state.md.

set -e

PROJECT=$1

if [ -z "$PROJECT" ]; then
  echo "Usage: pipeline-start.sh <project-name>"
  exit 1
fi

# Locate the claude-forge root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORGE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$FORGE_ROOT/projects.conf"

# Resolve project path from projects.conf
if [ ! -f "$CONFIG" ]; then
  echo "❌ projects.conf not found at $CONFIG"
  exit 1
fi

RAW_PATH=$(grep "^$PROJECT=" "$CONFIG" | cut -d= -f2-)
if [ -z "$RAW_PATH" ]; then
  echo "❌ Project '$PROJECT' not found in projects.conf"
  echo "   Add a line:  $PROJECT=<path-to-project-directory>"
  exit 1
fi

# Absolute path: use as-is. Relative path: resolve relative to FORGE_ROOT.
if [[ "$RAW_PATH" = /* ]]; then
  PROJECT_DIR="$RAW_PATH"
else
  PROJECT_DIR="$FORGE_ROOT/$RAW_PATH"
fi

echo "🚀 Initialising pipeline for: $PROJECT"
echo "   Path: $PROJECT_DIR"

# Create project directory structure
mkdir -p "$PROJECT_DIR/docs"
mkdir -p "$PROJECT_DIR/code"
mkdir -p "$PROJECT_DIR/tests"

# Each project is its own git repo — initialise if needed
if [ ! -d "$PROJECT_DIR/.git" ]; then
  git -C "$PROJECT_DIR" init
  git -C "$PROJECT_DIR" checkout -b main 2>/dev/null || true
  echo "✅ Git repo initialised"
else
  echo "✅ Git repo already exists"
fi

# Create pipeline state file if it doesn't exist
if [ ! -f "$PROJECT_DIR/pipeline-state.md" ]; then
  cat > "$PROJECT_DIR/pipeline-state.md" << EOF
# Pipeline State — $PROJECT

Started: $(date -u +"%Y-%m-%d %H:%M UTC")
Forge: $FORGE_ROOT

| Stage      | Status     | Artifact                  | Gate Decision | Notes |
|------------|------------|---------------------------|---------------|-------|
| research   | ⏳ pending | —                         | auto          |       |
| plan       | ⏳ pending | —                         | auto          |       |
| prd        | ⏳ pending | —                         | ⛔ human      |       |
| spec       | ⏳ pending | —                         | ⛔ human      |       |
| implement  | ⏳ pending | —                         | auto          |       |
| review     | ⏳ pending | —                         | ⛔ human      |       |
| test       | ⏳ pending | —                         | auto          |       |
| fix        | ⏳ pending | —                         | auto (max 5x) |       |
| done       | ⏳ pending | —                         | ⛔ human      |       |
EOF
  echo "✅ Pipeline state initialised"

  # Commit the initial structure to the project's own repo
  git -C "$PROJECT_DIR" add .
  git -C "$PROJECT_DIR" commit -m "chore: initialise project structure"
  echo "✅ Initial commit done"
fi

echo ""
echo "📁 Project directory: $PROJECT_DIR"
echo "📋 Brief: $PROJECT_DIR/brief.md"
echo ""
echo "Ready. Starting Stage 1: Research"
