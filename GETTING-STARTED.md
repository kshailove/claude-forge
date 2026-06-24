# ClaudeForge — Getting Started Guide

ClaudeForge is an agentic build framework that takes a project brief and drives it
through research, planning, PRD creation, technical spec, implementation, code review,
testing, and bug fixing — using Claude subagents at each stage, with you as the reviewer
at key decision points.

---

## What You Need Before Starting

1. **Claude Code installed**
   ```bash
   npm install -g @anthropic/claude-code
   ```

2. **GitHub CLI installed and authenticated**
   ```bash
   # Install
   brew install gh           # macOS
   sudo apt install gh -y    # Ubuntu

   # Authenticate
   gh auth login
   ```

3. **Anthropic API key** (from console.anthropic.com)
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

4. **This framework cloned**
   ```bash
   gh repo clone your-org/claude-forge
   cd claude-forge
   chmod +x framework/hooks/*.sh
   ```

---

## How to Start a New Project

Projects live **outside** the claude-forge directory — each in their own folder and git repo,
so you can make each one public, private, or untracked independently.

### Step 1 — Create your project folder

```bash
mkdir -p ../my-project
```

Put it anywhere you like. Sibling to claude-forge is the convention, but an absolute path works too.

### Step 2 — Register it in projects.conf

Open `projects.conf` (in the claude-forge root) and add one line:

```
my-project=../my-project
```

Use a relative path (relative to claude-forge) or an absolute path.

### Step 3 — Write your brief

Create `../my-project/brief.md`. This is the most important input in the
entire pipeline. The better your brief, the better everything that follows.

**Option A — Write it yourself** using this template:

```markdown
# [Project Name] — Brief

## Problem
[2-3 sentences: what problem, who has it, how painful]

## Solution
[2-3 sentences: what you're building and why it helps]

## Users
- **[Persona 1]:** [who they are, what they need]
- **[Persona 2]:** [who they are, what they need]

## Core Features (v1)
1. [Feature 1] — [one line]
2. [Feature 2] — [one line]
3. [Feature 3] — [one line]

## Out of Scope (v1)
- [Thing 1]
- [Thing 2]

## Integrations (if any)
- [API/Tool] — [what you'll use it for]

## Tech Preferences
- Language: [e.g. Python, TypeScript, no preference]
- Framework: [e.g. FastAPI, Next.js, no preference]
- Database: [e.g. PostgreSQL, MongoDB, no preference]
- Hosting: [e.g. AWS, Vercel, local Docker]
- Auth: [e.g. Google OAuth, username/password, none]

## Constraints
- [Deadline, team size, budget, other]
```

**Option B — Let Claude write it for you.** Open Claude Code in the framework directory
and say:

```
Help me write a brief for a new project. I want to build [describe your idea].
Use the skill at framework/skills/brief-writer.md.
```

Claude will interview you and write the brief.

### Step 4 — Start the pipeline

Open Claude Code in the `claude-forge` directory:

```bash
cd claude-forge
claude
```

Then say:

```
Start the pipeline for my-project
```

Claude Code will:
- Look up `my-project` in `projects.conf` to find its directory
- Run `framework/hooks/pipeline-start.sh my-project`
- Begin Stage 1 (Research) automatically
- Work through stages, stopping at human gates for your input

---

## The Pipeline in Detail

### Stages That Run Automatically

**Stage 1: Research**
Claude researches the problem space, competitor tools, relevant technology, and
integration options. Produces `docs/research.md`.
*You don't review this — it's input to later stages.*

**Stage 2: Plan**
Claude converts research into a project plan: scope, milestones, risks, key decisions.
Produces `docs/plan.md`.
*You don't review this — it's input to the PRD.*

### ⛔ Gate 1: PRD Review

Claude produces `docs/prd.md` — a full Product Requirements Document with user stories
and acceptance criteria.

**You will be asked:**
```
════════════════════════════════════════
⛔ GATE: PRD
Artifact: ../my-project/docs/prd.md
════════════════════════════════════════
Summary:
• 8 must-have features defined
• 3 user personas
• 24 acceptance criteria written
• Key open questions: [list]

Do you want to (A)pprove, (E)dit, or (R)eject with feedback?
```

**What to check:**
- Are the features the ones you actually want?
- Is v1 scope realistic (not too big, not too small)?
- Are acceptance criteria specific and testable?
- Is anything missing or over-engineered?

**Your options:**
- `A` — Approve and continue to Tech Spec
- `E` — Edit the file yourself in your editor, then say "done"
- `R` — Reject with feedback (e.g. "Remove feature X, add Y, the scope is too large")

### Stage 4: Tech Spec

Claude produces `docs/tech-spec.md` — architecture, data models, API contracts,
component breakdown.

### ⛔ Gate 2: Tech Spec Review

**What to check:**
- Does the architecture match your infrastructure?
- Are the tech choices ones your team knows?
- Are data models complete enough to write migrations?
- Are API shapes sensible?

**Common things to reject with feedback:**
- "We use PostgreSQL not SQLite"
- "Use webhooks for GitHub, not polling"
- "Our team doesn't know Go, use Python"
- "Split the frontend into its own repo"

### Stage 5: Implementation

Claude writes all the code from the tech spec. Produces files in `code/`.

### ⛔ Gate 3: Code Review

Claude reviews its own code against the spec and produces `docs/review.md` with issues
flagged by severity.

**What to check:**
- Are there CRITICAL issues? (These must be fixed before continuing)
- Does the implementation feel like something your team could maintain?
- Anything obviously missing?

### Stages 7-8: Test Writing + Test/Fix Loop

Claude writes a full test suite, runs it, and auto-fixes failures up to 5 times.
If tests still fail after 5 attempts, it escalates to you.

### ⛔ Gate 4: Final Sign-off

All tests passing. You review and approve the completed project.

---

## After the Pipeline

Your project directory will contain:

```
../my-project/              ← its own git repo, separate from claude-forge
  brief.md                  ← your original brief
  pipeline-state.md         ← what ran, when, decisions made
  docs/
    research.md             ← competitive + tech research
    plan.md                 ← scope, milestones, risks
    prd.md                  ← living requirements document
    tech-spec.md            ← architecture reference
    review.md               ← known issues log
  code/
    [all implementation files]
    README.md               ← how to run it
    .env.example            ← required environment variables
    implementation-index.md ← what was built
  tests/
    [all test files]
    README.md               ← how to run tests
    last-run.txt            ← most recent test output
```

Everything is committed to the **project's own git repo** with one commit per stage.
You can push each project to its own GitHub repo (public or private) independently.

**Hand `code/` to your team** as the starting scaffold.
**Use `docs/prd.md` and `docs/tech-spec.md`** as your living project documentation.

---

## Resuming a Paused Pipeline

If you stop mid-pipeline, just re-open Claude Code and say:

```
Resume the pipeline for my-project
```

Claude will read `pipeline-state.md` and continue from where it left off.

---

## Running a Specific Stage Again

If you want to re-run just one stage (e.g. you edited the PRD and want a fresh tech spec):

```
Re-run the spec stage for my-project using the updated prd.md
```

---

## Adding a New Project

Each project is completely independent. Just:

1. `mkdir -p ../new-project` (or wherever you want it)
2. Add `new-project=../new-project` to `projects.conf`
3. Write `../new-project/brief.md`
4. Tell Claude Code: `Start the pipeline for new-project`

---

## Tips for Better Results

### On Writing a Good Brief
- **Be specific about users.** "Engineers at Hiver" is better than "developers".
- **Name your integrations.** "GitHub via PyGitHub" is better than "GitHub".
- **Scope v1 ruthlessly.** The agents will add complexity — start tight.
- **State tech preferences.** If your team knows FastAPI, say so. Agents default to
  common choices which may not match your stack.

### At the PRD Gate
- The PRD gate is the most valuable one. Spend real time here.
- Reject if acceptance criteria are vague — "fast" is not a criterion.
- Keep must-have features to the minimum that proves value.

### At the Tech Spec Gate
- This is where your technical judgment matters most.
- Push back on architecture choices that don't fit your infra.
- Ask for changes using concrete terms: "use Redis for caching, not in-memory".

### At the Code Review Gate
- Don't let CRITICAL issues through. They compound.
- MINOR issues are fine to carry forward if you're time-pressured.

### General
- Use `E` (Edit) at gates to make small fixes yourself — faster than a full re-run.
- Use `R` (Reject) when you want the agent to rethink something substantially.
- The pipeline produces a scaffold, not finished production code. Plan for your team
  to own and extend it.

---

## Example: What to Say to Claude Code

| You want to... | Say... |
|----------------|--------|
| Start fresh | `Start the pipeline for hiver-intelligence` |
| Resume | `Resume the pipeline for hiver-intelligence` |
| Re-run one stage | `Re-run the prd stage for hiver-intelligence` |
| Write a brief | `Help me write a brief for a new project. I want to build X` |
| Jump to implementation | `Run only the implement stage for my-project` |
| See project status | `Show me the pipeline state for my-project` |

---

## Framework Directory Reference

```
claude-forge/                        ← public repo (the framework)
  CLAUDE.md                          ← orchestrator (main brain)
  projects.conf                      ← maps project names → directories
  framework/
    agents/
      research/CLAUDE.md             ← research subagent
      plan/CLAUDE.md                 ← planning subagent
      prd/CLAUDE.md                  ← PRD subagent
      spec/CLAUDE.md                 ← tech spec subagent
      implement/CLAUDE.md            ← implementation subagent
      review/CLAUDE.md               ← code review subagent
      test-writer/CLAUDE.md          ← test writing subagent
      test-runner/CLAUDE.md          ← test execution subagent
      bug-fix/CLAUDE.md              ← bug fixing subagent
    skills/
      brief-writer.md                ← helps write project briefs
      prd-template.md                ← PRD document structure
    hooks/
      pipeline-start.sh              ← project init + git setup
      post-stage.sh                  ← git commit after each stage
      pre-gate.sh                    ← validate artifact before review
  GETTING-STARTED.md                 ← this file

../hiver-intelligence/               ← private repo (your project)
  brief.md
  pipeline-state.md
  docs/  code/  tests/

../my-other-project/                 ← another repo, public or private
  brief.md
  ...
```
