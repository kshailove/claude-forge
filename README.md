# ClaudeForge

> An agentic build framework powered by Claude Code. Takes a brief, builds a project.

## What it does

ClaudeForge orchestrates a team of Claude subagents to take your project from idea to
tested code — with you as the reviewer at key decision points.

```
brief.md → Research → Plan → PRD ⛔ → Tech Spec ⛔ → Code → Review ⛔ → Tests → Done ⛔
```

## Quick Start

```bash
# 1. Install Claude Code
npm install -g @anthropic/claude-code

# 2. Clone this repo
gh repo clone your-org/claude-forge && cd claude-forge
chmod +x framework/hooks/*.sh

# 3. Create your project directory (outside claude-forge — its own repo)
mkdir -p ../my-app

# 4. Register it in projects.conf
echo "my-app=../my-app" >> projects.conf

# 5. Write your brief
# edit ../my-app/brief.md

# 6. Run
claude
# Then say: "Start the pipeline for my-app"
```

## Full Guide

See **[GETTING-STARTED.md](GETTING-STARTED.md)** for complete instructions.

## Project Layout

Each project lives **outside** the claude-forge directory in its own folder and git repo,
so you can make each one public, private, or untracked independently.

```
gh/
  claude-forge/          ← this repo (public)
    projects.conf        ← maps project names → directories
    CLAUDE.md
    framework/
      agents/            ← 9 specialist subagents
      skills/            ← reusable instructions
      hooks/             ← git + validation scripts

  my-app/                ← your project (its own repo, public or private)
    brief.md
    pipeline-state.md
    docs/  code/  tests/

  another-project/       ← another project, independently versioned
    brief.md
    ...
```
