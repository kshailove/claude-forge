#!/bin/bash
# hooks/pipeline-start.sh
# Runs at the start of every pipeline. Sets up git, creates project structure.

set -e

PROJECT=$1

if [ -z "$PROJECT" ]; then
  echo "Usage: pipeline-start.sh <project-name>"
  exit 1
fi

PROJECT_DIR="projects/$PROJECT"

echo "🚀 Initialising pipeline for: $PROJECT"

# Create project directory structure
mkdir -p "$PROJECT_DIR/docs"
mkdir -p "$PROJECT_DIR/code"
mkdir -p "$PROJECT_DIR/tests"

# Initialise git if not already a repo
if [ ! -d "$PROJECT_DIR/.git" ]; then
  git -C "$PROJECT_DIR" init
  git -C "$PROJECT_DIR" checkout -b main
  echo "# $PROJECT" > "$PROJECT_DIR/docs/.gitkeep"
  git -C "$PROJECT_DIR" add .
  git -C "$PROJECT_DIR" commit -m "chore: initialise project structure"
  echo "✅ Git repo initialised"
else
  echo "✅ Git repo already exists"
fi

# Create pipeline state file if it doesn't exist
if [ ! -f "$PROJECT_DIR/pipeline-state.md" ]; then
  cat > "$PROJECT_DIR/pipeline-state.md" << EOF
# Pipeline State — $PROJECT

Started: $(date -u +"%Y-%m-%d %H:%M UTC")

| Stage      | Status    | Artifact                  | Gate Decision | Notes |
|------------|-----------|---------------------------|---------------|-------|
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
fi

echo ""
echo "📁 Project directory: $PROJECT_DIR"
echo "📋 Brief: $PROJECT_DIR/brief.md"
echo ""
echo "Ready. Starting Stage 1: Research"
