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

# 3. Write your brief
mkdir -p projects/my-app
# edit projects/my-app/brief.md

# 4. Run
claude
# Then say: "Start the pipeline for projects/my-app"
```

## Full Guide

See **[GETTING-STARTED.md](GETTING-STARTED.md)** for complete instructions.

## Example Project

See `projects/hiver-intelligence/brief.md` for a real-world example brief
(cross-tool intelligence dashboard for engineering managers).

## Framework Structure

```
CLAUDE.md                    ← orchestrator
framework/
  agents/                    ← 9 specialist subagents
  skills/                    ← reusable instructions
  hooks/                     ← git + validation scripts
projects/                    ← your projects live here
```
