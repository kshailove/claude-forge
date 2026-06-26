# ClaudeForge: A Complete Tutorial for AI Beginners

**Understanding Agentic AI, Orchestration, and the ClaudeForge Build Framework**

---

## Table of Contents

1. [What Is This Project? The 10,000-Foot View](#1-what-is-this-project)
2. [Core Concepts: AI, Agents, and Agentic Flows](#2-core-concepts)
3. [How Claude (The AI) Works in This System](#3-how-claude-works)
4. [The Architecture: Orchestrator + Subagents](#4-the-architecture)
5. [The Pipeline: 8 Stages from Brief to Code](#5-the-pipeline)
6. [Deep Dive: Each Agent Explained](#6-deep-dive-each-agent)
7. [Human Gates: Why Humans Stay in the Loop](#7-human-gates)
8. [Data Flow: How Information Moves Through the System](#8-data-flow)
9. [Context Window Management: The Hidden Engineering Challenge](#9-context-window-management)
10. [The Framework Files: What Each File Does](#10-the-framework-files)
11. [The Example Project: Engineering Intelligence Platform](#11-the-example-project)
12. [Agentic Engineering Principles: Lessons From This Codebase](#12-agentic-engineering-principles)
13. [How to Run This Yourself](#13-how-to-run-this-yourself)
14. [Glossary](#14-glossary)

---

## 1. What Is This Project?

ClaudeForge is a **software build automation system powered by AI agents**. You give it a plain English description of an app you want to build (called a "brief"), and it drives the entire software development process — research, planning, product requirements, technical design, code generation, code review, and testing — with an AI doing most of the work.

Think of it like hiring an entire startup engineering team, except the team members are AI agents, and you are the CEO who approves critical decisions.

**What it takes as input:**
A `brief.md` file — a plain English description of what you want to build. Example: "Build an engineering intelligence dashboard that aggregates GitHub, Jira, and Slack data to show team health scores."

**What it produces as output:**
- `docs/research.md` — deep research on the problem space and competitors
- `docs/plan.md` — scope, milestones, and key decisions
- `docs/prd.md` — a full Product Requirements Document
- `docs/tech-spec.md` — architecture, data models, API contracts
- `code/` — all the actual source code
- `docs/review.md` — code review findings
- `tests/` — a full test suite (unit, integration, acceptance tests)

All of this runs with minimal human effort. You only stop to make decisions at 4 key checkpoints.

**Why does this matter?**

Traditionally, building software requires weeks or months and a team of specialists: product managers, architects, engineers, QA engineers. ClaudeForge demonstrates that AI agents, when orchestrated well, can perform each of these roles with production-quality output — while keeping humans in control of the decisions that matter.

---

## 2. Core Concepts

Before diving into how ClaudeForge works, you need to understand some foundational concepts about AI and agents.

### 2.1 What Is a Large Language Model (LLM)?

An LLM (Large Language Model) is an AI that has been trained on massive amounts of text. It learns patterns in human language and can generate coherent, contextually appropriate text in response to prompts. Claude (made by Anthropic) is an LLM. So are GPT-4 (OpenAI) and Gemini (Google).

The key thing to understand: **an LLM is fundamentally a text-in, text-out system.** You send it text (called a "prompt"), and it responds with text (called a "completion"). Everything in agentic AI is built on top of this simple foundation.

### 2.2 What Is a Context Window?

When you talk to an LLM, it can only "see" a certain amount of text at once. This limit is called the **context window**. Think of it like the AI's working memory — it can only hold so much information in mind at once.

Modern models like Claude have large context windows (hundreds of thousands of tokens), but they are not unlimited. Managing what goes into the context window — and what doesn't — is one of the most important engineering challenges in agentic systems. You'll see this theme come up repeatedly in ClaudeForge.

### 2.3 What Is an AI Agent?

An AI agent is an LLM that has been given:
1. **A specific role** — a persona or job description (e.g., "You are a senior software engineer")
2. **Tools** — abilities beyond just text generation (e.g., the ability to read/write files, run code, search the web)
3. **Instructions** — rules about how to behave and what to produce
4. **A goal** — a specific task to accomplish

The word "agent" comes from the idea that the AI is taking *autonomous action* toward a goal, rather than just answering a single question. An agent can:
- Decide what to do next
- Use tools to get information or take actions
- Evaluate its own output and retry if something is wrong
- Handle unexpected situations

### 2.4 What Is an Agentic Flow?

An agentic flow is a **sequence of AI agent actions** organized to accomplish a complex multi-step task. Think of it like a workflow or pipeline where AI does most of the work, but the workflow itself is designed by humans.

Key properties of an agentic flow:
- **Multi-step**: Not a single AI call, but a series of calls
- **Autonomous**: The AI makes decisions and takes actions without step-by-step human guidance
- **Stateful**: State (information produced earlier) is preserved and passed forward
- **Observable**: Humans can see what's happening and intervene

### 2.5 What Is Orchestration?

Orchestration is the **coordination of multiple agents**. In an orchestra, the conductor coordinates dozens of musicians — each expert in their instrument — toward a unified performance. The conductor doesn't play any instrument; they manage timing, balance, and sequence.

In agentic AI, an **orchestrator** is an agent (or program) that:
- Knows the overall goal
- Breaks it into sub-tasks
- Delegates sub-tasks to specialized subagents
- Passes outputs from one agent as inputs to the next
- Handles errors and retries
- Decides when to ask a human for help

ClaudeForge is built entirely around this orchestrator pattern.

---

## 3. How Claude Works in This System

ClaudeForge runs on top of **Claude Code**, which is Anthropic's CLI (Command Line Interface) for Claude. When you run ClaudeForge, you are running Claude in a terminal, and Claude has access to tools like:

- **Read/Write files** — Claude can read your brief.md and write docs like research.md
- **Run bash commands** — Claude can run scripts, git commands, test suites
- **Spawn subagents (Task tool)** — Claude can launch other Claude instances as subagents

This last capability — spawning subagents — is what makes ClaudeForge possible. The main Claude instance (the orchestrator) can create child Claude instances (subagents) and assign them work. Each subagent gets its own context window and a specific set of instructions.

### How CLAUDE.md Files Work

In Claude Code, a file named `CLAUDE.md` in any directory acts as **system-level instructions** for Claude when it operates in that context. It's like a job description that Claude reads before doing anything.

In ClaudeForge:
- `/CLAUDE.md` — the orchestrator's job description (the "conductor")
- `/framework/agents/research/CLAUDE.md` — the research agent's job description
- `/framework/agents/plan/CLAUDE.md` — the plan agent's job description
- ...and so on for each of the 9 agents

When the orchestrator says "run the research stage," it spawns a subagent and tells it to operate with the instructions in `framework/agents/research/CLAUDE.md`. That subagent then reads the brief, does research, and writes the output.

---

## 4. The Architecture

ClaudeForge has a clear two-level hierarchy:

```
┌─────────────────────────────────────────────────────┐
│                   ORCHESTRATOR                       │
│               (main CLAUDE.md)                       │
│                                                      │
│  - Manages the overall pipeline                      │
│  - Spawns subagents for each stage                   │
│  - Handles human gates                               │
│  - Commits to git                                    │
│  - Tracks state in pipeline-state.md                 │
└──────────────────────┬──────────────────────────────┘
                       │ spawns subagents
           ┌───────────┼───────────────────┐
           │           │                   │
    ┌──────▼──┐  ┌─────▼───┐  ┌───────────▼──────┐
    │Research │  │  Plan   │  │ PRD / Spec /     │
    │ Agent   │  │  Agent  │  │ Implement / etc. │
    └─────────┘  └─────────┘  └──────────────────┘
```

### Why This Architecture?

**Why not just use one big Claude prompt?**

You could theoretically ask Claude "here's my brief, give me all the code." But this approach has severe limitations:

1. **Context window limits**: A full research report + plan + PRD + tech spec + code easily exceeds any model's context window.

2. **Quality degradation**: LLMs do worse at complex multi-step tasks in a single prompt. Breaking work into focused steps with focused agents produces dramatically better results.

3. **Specialization**: A "research" agent can be given specific instructions optimized for web search and analysis. An "implementation" agent can be given coding-specific instructions. Mixing these into one agent makes both worse.

4. **Reviewability**: Separate artifacts at each stage allow humans to review, approve, or reject specific outputs rather than getting a single undivided result.

5. **Restartability**: If something goes wrong at Stage 5, you can re-run Stage 5 without redoing Stages 1-4.

### The Orchestrator's Role

The orchestrator (main `CLAUDE.md`) does not do the actual work of any stage. It:

1. Reads the project brief
2. Invokes each agent in sequence using the Task tool
3. Passes the right artifacts from prior stages as context
4. Waits at human gates
5. Handles feedback and re-runs
6. Commits to git
7. Updates the pipeline state file

This separation of "coordination logic" from "execution logic" is a fundamental principle of good agentic system design.

---

## 5. The Pipeline

The ClaudeForge pipeline has 8 stages. Four of them have human gates where you must explicitly approve before the pipeline continues. Here is the complete flow:

```
brief.md (you write this)
    │
    ▼
┌───────────────────────────────────────────────────────┐
│  Stage 1: RESEARCH                                    │
│  Agent: agents/research/CLAUDE.md                    │
│  Input: brief.md                                     │
│  Output: docs/research.md                            │
│  Auto → no human gate                                │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 2: PLAN                                        │
│  Agent: agents/plan/CLAUDE.md                        │
│  Input: brief.md + research.md                       │
│  Output: docs/plan.md                                │
│  Auto → no human gate                                │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 3: PRD (Product Requirements Document)         │
│  Agent: agents/prd/CLAUDE.md                         │
│  Input: brief.md + research.md + plan.md             │
│  Output: docs/prd.md                                 │
│  ⛔ HUMAN GATE 1 — Approve / Edit / Reject            │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 4: TECH SPEC                                   │
│  Agent: agents/spec/CLAUDE.md                        │
│  Input: brief.md + research.md + prd.md              │
│  Output: docs/tech-spec.md                           │
│  ⛔ HUMAN GATE 2 — Approve / Edit / Reject            │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 5: IMPLEMENT                                   │
│  Agent: agents/implement/CLAUDE.md                   │
│  Input: tech-spec.md + prd.md                        │
│  Output: code/* (all source files)                   │
│  Auto → no human gate                                │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 6: CODE REVIEW                                 │
│  Agent: agents/review/CLAUDE.md                      │
│  Input: tech-spec.md + prd.md + code/*               │
│  Output: docs/review.md                              │
│  ⛔ HUMAN GATE 3 — Approve / Reject                   │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 7: TEST WRITING                                │
│  Agent: agents/test-writer/CLAUDE.md                 │
│  Input: prd.md + tech-spec.md + code/*               │
│  Output: tests/*                                     │
│  Auto → no human gate                                │
└────────────────────────────┬──────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────┐
│  Stage 8: TEST-RUN + BUG-FIX LOOP (up to 5x)         │
│                                                       │
│  8a. Test Runner: run test suite                      │
│    → All pass? → Final Gate                          │
│    → Any fail? → 8b Bug Fixer                        │
│                                                       │
│  8b. Bug Fixer: fix failing tests                     │
│    → Loop back to 8a                                 │
│    → If 5 iterations still failing → escalate        │
│                                                       │
│  ⛔ HUMAN GATE 4 — Final sign-off                     │
└───────────────────────────────────────────────────────┘
```

### Why This Order?

The pipeline is ordered from most abstract to most concrete:

1. **Research** — understand the problem domain before deciding anything
2. **Plan** — decide what to build (scope, milestones) before writing requirements
3. **PRD** — write requirements before designing the system
4. **Tech Spec** — design the system before writing code
5. **Implement** — write code before reviewing it
6. **Review** — review code before writing tests
7. **Test** — write tests once code is stable
8. **Test-Run + Fix** — run tests and fix until they pass

Skipping or reordering steps causes problems in real software projects and the same is true for AI-driven ones. If you start coding without a tech spec, you build the wrong thing. If you write tests before the code is reviewed, you waste time testing code that will change.

---

## 6. Deep Dive: Each Agent

Let's examine each agent in detail — what role it plays, what it's instructed to do, what it reads, and what it produces.

### 6.1 Research Agent (`agents/research/CLAUDE.md`)

**Persona**: Senior technical researcher

**What it does**: This agent explores the problem space thoroughly before any decisions are made. It answers: What problem does this solve? Who are the users? What solutions already exist? What technologies should we use? What are the risks?

**Inputs**:
- `brief.md` (the user's project description)
- Optional: human feedback (if this is a re-run after rejection)

**Output** — `docs/research.md` with 6 sections:

| Section | What It Contains |
|---|---|
| Problem Space | Problem definition, who has this pain, how painful it is, current workarounds |
| Existing Solutions | Competitors, honest pros/cons, gaps this project can fill |
| Technology Landscape | Recommended libraries, frameworks, APIs with specific version numbers and tradeoffs |
| Integration Landscape | For each external API: rate limits, auth method, gotchas, error handling |
| Risks & Unknowns | Technical risks, product risks, things that need prototyping ("spikes") |
| Recommended Direction | Opinionated recommendation + key decisions for the planning stage |

**Key design decision**: The research agent is instructed to be *specific* and *honest about tradeoffs*. It doesn't write marketing copy — it writes like a senior engineer who has evaluated options and has opinions. For example, it doesn't say "use a framework that fits your needs" — it says "use FastAPI 0.115+ with SQLAlchemy 2.x async engine, here's why, here are the alternatives, here's when you'd choose differently."

**Why this matters**: AI agents tend to be vague and hedge-everything unless explicitly instructed not to. The research agent's CLAUDE.md counteracts this tendency.

---

### 6.2 Plan Agent (`agents/plan/CLAUDE.md`)

**Persona**: Technical product lead

**What it does**: Converts research findings into a concrete plan — what to build, who it's for, how to scope it, what's explicitly out of scope.

**Inputs**:
- `brief.md`
- `research.md` (full)
- Optional: human feedback

**Output** — `docs/plan.md` with 7 sections:

| Section | What It Contains |
|---|---|
| Project Goals | One sentence primary goal + measurable success metrics |
| Scope | What's in v1, what's out of v1, what's future (v2+) |
| User Personas | 2-3 personas maximum with role, goals, pain points |
| Milestones | Table with milestone name, deliverables, effort estimate |
| Key Decisions | 3-5 explicit architectural/product decisions for the spec stage |
| Risks & Mitigations | Risk table with severity, likelihood, mitigation strategy |
| Dependencies & Assumptions | External factors the plan depends on |

**Why "Key Decisions" matters**: The plan agent explicitly surfaces decisions that will need to be made at the tech spec stage — e.g., "TimescaleDB vs. vanilla PostgreSQL," "GitHub App vs. Personal Access Token." This is forward-looking: it ensures the spec agent doesn't have to re-discover these questions from scratch.

**The "ruthless scoping" instruction**: The plan agent is instructed to be merciless about what goes in v1. This is important because AI models, like eager engineers, tend to over-engineer and add "nice to have" features. The plan agent must resist this and keep v1 small and focused.

---

### 6.3 PRD Agent (`agents/prd/CLAUDE.md`)

**Persona**: Senior product manager

**What it does**: Writes the Product Requirements Document — the contract between "what the product is supposed to do" and "how the system is designed to do it." The PRD is the foundation for both the tech spec and the test suite.

**Inputs**:
- `brief.md`
- `research.md` (full)
- `plan.md` (full)
- Optional: human feedback
- Skill used: `framework/skills/prd-template.md` (structural template)

**Output** — `docs/prd.md` with 8 sections:

| Section | What It Contains |
|---|---|
| Overview | Problem being solved, solution summary, target users |
| Goals & Non-Goals | Checkboxes for goals; explicit exclusions for v1 |
| User Personas | From plan, expanded with key actions |
| Features | For each feature: priority, description, user story, acceptance criteria, edge cases |
| User Flows | Step-by-step flows for key journeys (text or ASCII diagrams) |
| Data Requirements | What data is needed, where it comes from, how fresh, sensitivity level |
| Non-Functional Requirements | Performance targets, security requirements, reliability/uptime |
| Open Questions | Unresolved questions that the tech spec must answer |

**What are Acceptance Criteria (AC)?**

Acceptance criteria are the most important part of the PRD. Each feature has a list of specific, testable conditions that must be true for the feature to be considered "done."

A good AC is binary — it's either true or false:
- ✅ Good: "When a user submits a login form with an incorrect password, the system returns an error message within 500ms and does not reveal whether the email exists."
- ❌ Bad: "The login should be secure and fast."

The PRD agent is instructed to write ACs that are testable and binary. This is critical because the test-writer agent later reads the PRD and writes one acceptance test per criterion.

**The Human Gate at PRD**: The first human gate is here because the PRD is the highest-leverage document in the pipeline. If the PRD is wrong, everything downstream is wrong. A bad tech spec can be patched; a bad PRD means you'll build the wrong thing entirely.

---

### 6.4 Tech Spec Agent (`agents/spec/CLAUDE.md`)

**Persona**: Principal engineer

**What it does**: Translates product requirements into a technical design. Decides the architecture, data models, API contracts, and implementation order. This is the blueprint that the implementation agent follows.

**Inputs**:
- `brief.md`
- `research.md` (full — foundational)
- `prd.md` (full)
- Optional: human feedback

**Output** — `docs/tech-spec.md` with 9 sections:

| Section | What It Contains |
|---|---|
| Architecture Overview | ASCII diagram showing all components and how they connect |
| Tech Stack Decisions | For each technology: choice, alternatives considered, rationale |
| Data Models | Table definitions with every column, type, constraint, index, and relationship |
| API Contracts | Every endpoint with auth, request/response shape, error codes |
| Component Breakdown | Per module: purpose, inputs, outputs, key logic, dependencies |
| Integration Details | Per external API: auth flow, rate limit strategy, error handling, local dev setup |
| Non-Functional Implementation | How auth, caching, logging, error handling are implemented |
| Implementation Order | Ordered list of what to build first — this is the implementation agent's roadmap |
| Open Technical Questions | Things that still need spikes or decisions |

**Why is the tech spec so important?**

The tech spec is where vague requirements become precise engineering decisions. "User authentication" in the PRD becomes "bcrypt-hashed passwords stored in `users.password_hash`, JWT tokens signed with HS256, 24-hour expiry, stored in httpOnly cookies" in the tech spec.

Without a precise spec, the implementation agent makes its own decisions — and they may not align with your infrastructure, security requirements, or team conventions.

**The Human Gate at Tech Spec**: This is the gate where technical leaders should push back if the architecture doesn't fit. This is where you'd say: "Don't use TimescaleDB, we don't have Kubernetes." Changing this after implementation means rewriting code.

---

### 6.5 Implementation Agent (`agents/implement/CLAUDE.md`)

**Persona**: Senior software engineer

**What it does**: Writes all the actual code based on the tech spec. This is the "builder" agent — it follows the implementation order from the spec and produces the full codebase.

**Inputs**:
- `tech-spec.md` (full)
- `prd.md` (summarized — first 100 lines, per context management rules)
- Optional: human feedback

**Output** — All files in `code/` directory:
- `code/README.md` — how to install, run, and test the project; all env vars documented
- `code/implementation-index.md` — list of every file created with one-line description
- All source files following the spec's implementation order

**Code quality rules the agent is instructed to follow**:
- **Typed**: Type hints/annotations on everything
- **Documented**: Docstrings on all public functions
- **Error-handled**: No bare `except:` clauses, no unhandled promise rejections
- **No hardcoded secrets**: All secrets in environment variables
- **No TODOs unless truly unavoidable**

**Implementation order matters**: The spec agent defines the order (data models → business logic → API → background jobs → frontend → deployment files). The implementation agent follows this strictly. Building in this order ensures each layer exists before the layer above it depends on it.

**An important note on AI-generated code**: Code produced by an LLM is a strong first draft, not production-ready code. It will be reviewed by the review agent and tested by the test suite. The pipeline is designed with this in mind — code is never the final output without review and tests.

---

### 6.6 Review Agent (`agents/review/CLAUDE.md`)

**Persona**: Principal engineer (performing a brutal, honest review)

**What it does**: Reviews all the generated code against the tech spec and PRD. The instruction "not-being-nice review" is deliberate — the agent is told to flag issues honestly, not to be encouraging.

**Inputs**:
- `tech-spec.md`
- `prd.md`
- All files in `code/`

**Output** — `docs/review.md` with:
- **Verdict**: `APPROVE`, `APPROVE_WITH_CHANGES`, or `REJECT`
- **Issues list** with severity, location, what's wrong, why it matters, specific fix
- **Review checklist**: spec compliance, correctness, security, code quality, testability

**Severity levels**:

| Severity | Description | Required Action |
|---|---|---|
| 🔴 CRITICAL | Security vulnerability, data loss, broken core flow | Must fix before proceeding |
| 🟠 MAJOR | Incorrect logic, missing error handling, spec deviation | Must fix before proceeding |
| 🟡 MINOR | Code quality, naming, duplication | Should fix before shipping |
| 🔵 SUGGESTION | Optional improvement ideas | Optional |

**Why a separate review agent?** The implementation agent produced the code, so it has a "bias" toward its own work. A separate review agent approaches the code fresh, without any attachment to it. This models how code reviews work in real teams — the author doesn't review their own code.

**The Human Gate at Code Review**: You see the verdict and issue summary. If there are CRITICAL or MAJOR issues, you'll likely reject and have the implementation agent fix them. You can also choose to edit the code yourself and say "done."

---

### 6.7 Test Writer Agent (`agents/test-writer/CLAUDE.md`)

**Persona**: Senior QA engineer

**What it does**: Writes a comprehensive test suite based on the PRD acceptance criteria and the tech spec's component breakdown.

**Inputs**:
- `prd.md` (acceptance criteria drive acceptance tests)
- `tech-spec.md` (component breakdown drives unit/integration tests)
- All files in `code/`

**Output** — Full test suite in `tests/` directory:

```
tests/
  unit/
    test_[module].py         ← one file per module
  integration/
    test_[feature]_api.py    ← one file per feature area
  acceptance/
    test_[feature]_acceptance.py  ← one per PRD feature
  conftest.py                ← shared fixtures (test setup)
  README.md                  ← how to run tests
```

**Three types of tests the agent writes**:

1. **Unit tests**: Test individual functions in isolation. Every public function gets a test with happy path + at least 2 edge cases. No network calls, no database — external dependencies are "mocked" (replaced with fake objects).

2. **Integration tests**: Test that components work together — API endpoints, database operations, interactions with external services (mocked at the network level, not the code level).

3. **Acceptance tests**: One test per PRD acceptance criterion, named `test_ac_[feature]_[criterion]`. These verify the system satisfies the product requirements.

**Why this naming convention?** The name `test_ac_sprint_health_burndown_accurate` immediately tells you which PRD requirement this test verifies. When a test fails, you know exactly which acceptance criterion is broken.

---

### 6.8 Test Runner Agent (`agents/test-runner/CLAUDE.md`)

**Persona**: CI/CD system (automated)

**What it does**: Detects the test framework (pytest for Python, Jest for Node.js, go test for Go, cargo test for Rust), runs the full test suite, and produces a structured report.

**Input**: All files in `code/` and `tests/`

**Output**:
- `tests/last-run.txt` — raw test output
- Structured report:

```
TEST RUN RESULTS
================
Total:   47 tests
Passed:  44 ✅
Failed:  3  ❌
Skipped: 0  ⏭

FAILING TESTS:
- test_sprint_burndown_empty_sprint: AssertionError: expected 0 tasks, got None
- test_github_webhook_invalid_signature: 403 expected, got 200
- test_identity_resolution_fuzzy_match: email match not found
```

**Decision logic**:
- All passing → "Ready for final gate"
- Any failing → "Invoking BugFixAgent. Iteration [n]/5"

---

### 6.9 Bug Fix Agent (`agents/bug-fix/CLAUDE.md`)

**Persona**: Surgical bug fixer (not a refactorer)

**What it does**: Reads each failing test's error message, finds the root cause, and fixes it. The agent is explicitly instructed to only fix what's failing and not refactor working code.

**Inputs**:
- `tests/last-run.txt` (failing test names + error messages)
- All files in `code/`
- All files in `tests/`
- Current iteration number (1-5)

**Process for each failing test**:
1. Read the error — what assertion failed, what exception was raised?
2. Find root cause — is the bug in the code, or is the test itself wrong?
3. Fix the right thing — fix code if code is wrong; fix test if test has wrong expectation
4. Verify the fix makes logical sense

**Escalation at iteration 5**: If after 5 bug-fix iterations tests are still failing, the agent writes `tests/escalation-report.md` containing:
- What tests are still failing
- What was tried in each iteration
- Hypothesis for root cause
- What human intervention is needed

This is the agentic equivalent of an engineer saying "I've been debugging this for hours, I need a senior engineer to look at it."

---

## 7. Human Gates

Human gates are one of the most important design choices in ClaudeForge. They prevent the pipeline from running autonomously to completion without human judgment.

### Why 4 Gates and Not More (or Fewer)?

Too many gates = the human does all the work; the AI is just helping. Too few gates = the AI makes all the decisions; humans lose control.

The 4 gates are placed at the highest-leverage decision points:

| Gate | After Stage | Why Here? |
|---|---|---|
| Gate 1 | PRD | If the requirements are wrong, all code will be wrong. Cheapest place to catch misunderstandings. |
| Gate 2 | Tech Spec | Architecture is expensive to change after coding starts. This is the last checkpoint before significant AI work. |
| Gate 3 | Code Review | Check that AI-generated code meets quality and security standards before writing tests for it. |
| Gate 4 | Final Sign-Off | Confirm that all tests pass and the project is ready. |

### The A/E/R Protocol

At each gate, the orchestrator presents a summary and asks:

> "Do you want to (A)pprove, (E)dit, or (R)eject with feedback?"

**Approve (A)**: The artifact is good. Move to the next stage immediately.

**Edit (E)**: The artifact is almost right but needs minor tweaks. The orchestrator tells you which file to edit, waits for you to make changes and say "done," then continues. This is faster than a full re-run when changes are small.

**Reject (R)**: The artifact has fundamental problems. The orchestrator asks "What should the agent change?" You provide specific feedback. The orchestrator re-runs the stage with your feedback injected into the agent's context. The agent then produces a revised artifact. This loop can happen multiple times until you're satisfied.

### How Feedback Is Injected

When you reject with feedback, the orchestrator includes your feedback in the agent's next invocation context. For example:

```
Task: Re-run the PRD stage for project engg-intelligence.
Agent: framework/agents/prd/CLAUDE.md
Context:
  - Brief: projects/engg-intelligence/brief.md
  - Prior artifacts: research.md, plan.md
  - Human feedback: "The acceptance criteria for the Health Score feature
    are too vague. 'Score is accurate' is not testable. Rewrite them as
    specific, binary conditions. Also, the non-functional requirements
    don't mention data retention — add a 12-month retention requirement."
Output to: projects/engg-intelligence/docs/prd.md
```

The agent receives this feedback in its context window and produces a revised PRD that incorporates it. This is one of the most powerful patterns in agentic engineering: **feedback-driven iteration loops.**

---

## 8. Data Flow

Understanding how data flows through the system is crucial to understanding why the system works.

### Stage-by-Stage Information Accumulation

```
Stage 1 (Research):
  Reads: brief.md
  Writes: research.md

  Information gained: What exists, what technologies to use, what risks exist

Stage 2 (Plan):
  Reads: brief.md + research.md
  Writes: plan.md

  Information gained: What to build in v1, who for, key decisions to make

Stage 3 (PRD):
  Reads: brief.md + research.md + plan.md
  Writes: prd.md

  Information gained: Exactly what features, with testable acceptance criteria

Stage 4 (Spec):
  Reads: brief.md + research.md + prd.md
  Writes: tech-spec.md

  Information gained: How to build it (architecture, data models, API contracts)

Stage 5 (Implement):
  Reads: tech-spec.md + prd.md (summary)
  Writes: code/*

  Information gained: The actual working codebase

Stage 6 (Review):
  Reads: tech-spec.md + prd.md + code/*
  Writes: review.md

  Information gained: What's wrong with the code and how serious

Stage 7 (Test Writer):
  Reads: prd.md + tech-spec.md + code/*
  Writes: tests/*

  Information gained: A test suite that verifies all requirements

Stage 8 (Test Runner):
  Reads: code/* + tests/*
  Writes: tests/last-run.txt

  Information gained: Which tests pass, which fail, why

Stage 8b (Bug Fix):
  Reads: tests/last-run.txt + code/* + tests/*
  Writes: fixed code/*

  Information gained: Root causes of failures and how to fix them
```

### The Principle of Increasing Specificity

Notice how each stage adds more concrete, specific information:

- **Brief**: "Build a dashboard showing team health" (abstract, vague)
- **Research**: "Use FastAPI 0.115+ with asyncpg, PostgreSQL with TimescaleDB" (concrete technologies)
- **Plan**: "V1 includes 8 features, out of scope: mobile, OAuth, real-time" (concrete scope)
- **PRD**: "Feature: Team Health Score — AC: Score updates within 5 minutes of PR merge" (testable criteria)
- **Spec**: "team_health_scores table: id UUID, team_id FK, score INT, calculated_at TIMESTAMP" (precise schema)
- **Code**: `class TeamHealthScore(Base): id: UUID = Field(default_factory=uuid4)...` (actual implementation)
- **Tests**: `def test_health_score_updates_within_5_minutes(): ...` (verification code)

This progression from abstract to concrete is the core pattern of how complex systems are built — whether by humans or AI.

### Information That Flows Forward

Notice that not every prior artifact is passed to every future stage. The data flow is selective:

- Research.md is **foundational** — it flows into Plan, PRD, and Spec
- Plan.md flows into PRD (for personas and scope) but not into implementation
- PRD flows into Spec (requirements drive architecture) and into testing (criteria drive tests)
- Tech Spec flows into implementation and testing
- Code flows into review and testing

The orchestrator's `CLAUDE.md` is explicit about this: pass full research.md and plan.md (they're foundational), pass summarized PRD to implementation agents (too long to pass in full), pass only failing test names to bug-fix agents (not the full test suite).

---

## 9. Context Window Management

This is one of the most important engineering challenges in agentic systems, and ClaudeForge addresses it explicitly.

### The Problem

LLMs have a finite context window. If you pass too much text, one of two things happens:
1. The model runs out of context (errors out or truncates)
2. The model's quality degrades — it starts "forgetting" earlier parts of the context or missing details

As a project progresses, the accumulated artifacts can become very large. A full research.md might be 500 lines. A tech-spec.md for a complex project might be 1,000 lines. The codebase might be 5,000 lines. You cannot pass all of this to every agent.

### ClaudeForge's Solution

The orchestrator's CLAUDE.md explicitly defines these rules:

```
- Pass the FULL research.md and plan.md (they're foundational)
- Pass a SUMMARY of prd.md (first 100 lines) to implementation agents
- Pass only FAILING TEST NAMES + relevant code to bug-fix agents
- Never pass more than 3 prior artifacts in full at once
```

**Why full research and plan?** These documents set the foundation. Without full research, the spec agent might make technology choices that contradict research findings. Without the full plan, the PRD agent might expand scope beyond what was decided.

**Why summarized PRD to implementation?** The full PRD is needed for acceptance criteria (test-writer uses the full PRD), but the implementation agent mainly needs the tech spec. Passing 300 lines of PRD to the implementation agent uses context space that would be better used for the tech spec and code patterns.

**Why only failing tests to bug-fix?** The bug-fix agent has a very narrow job: fix specific failing tests. It doesn't need to read passing tests, all documentation, or the full codebase. It needs the error message, the test code, and the function that's failing. Passing everything else wastes context and may confuse the agent.

### The Golden Rule of Context Management

**Only give an agent what it needs to do its job. Nothing more.**

This seems obvious but is frequently violated in practice. The temptation is to give agents "all the context so they can make good decisions." But more context is not always better — it can dilute the signal, slow down the agent, and waste expensive token budget.

---

## 10. The Framework Files

Let's look at every file in the framework and understand its purpose.

### Directory Structure

```
gh/
  claude-forge/                  ← this repo (public)
  ├── CLAUDE.md                  ← Orchestrator (main agent instructions)
  ├── README.md                  ← Quick start for users
  ├── GETTING-STARTED.md         ← Detailed user guide
  ├── tutorial.md                ← This file
  ├── projects.conf              ← maps project names → directories
  │
  └── framework/
      ├── agents/                ← 9 specialist agent instructions
      │   ├── research/CLAUDE.md
      │   ├── plan/CLAUDE.md
      │   ├── prd/CLAUDE.md
      │   ├── spec/CLAUDE.md
      │   ├── implement/CLAUDE.md
      │   ├── review/CLAUDE.md
      │   ├── test-writer/CLAUDE.md
      │   ├── test-runner/CLAUDE.md
      │   └── bug-fix/CLAUDE.md
      │
      ├── skills/                ← Reusable instruction templates
      │   ├── brief-writer.md    ← Helps users write a good brief
      │   └── prd-template.md    ← Standard PRD document structure
      │
      └── hooks/                 ← Shell scripts for automation
          ├── pipeline-start.sh  ← Initialize project on pipeline start
          ├── post-stage.sh      ← Git commit after each stage
          └── pre-gate.sh        ← Validate artifact before human gate

  engg-intelligence/             ← your project (its own repo, public or private)
  ├── brief.md
  ├── pipeline-state.md
  ├── docs/
  │   └── research.md
  ├── code/
  └── tests/
```

### What Are Skills?

Skills are **reusable instruction templates** that agents can invoke. They're like functions or libraries in code — a piece of logic that can be used in multiple places.

**`brief-writer.md`**: When a user wants to start a new project but hasn't written a brief yet (or their brief is less than 200 words), the orchestrator invokes this skill. It defines a 12-question interview the orchestrator conducts with the user to gather enough information to write a proper brief. The skill specifies what questions to ask, in what order, and what template to use for the output.

**`prd-template.md`**: When the PRD agent writes `prd.md`, it uses this template as the structural framework. It defines the exact sections, formatting rules, and quality criteria for a proper PRD. Using a standard template ensures consistency and completeness — the agent can't "forget" to include acceptance criteria or open questions.

### What Are Hooks?

Hooks are **shell scripts that run automatically at specific points in the pipeline**. They handle bookkeeping tasks that don't require AI reasoning.

**`pipeline-start.sh`**: Runs once at the beginning of any new project pipeline. It:
1. Creates the project directory structure (`docs/`, `code/`, `tests/`)
2. Initializes a git repository if one doesn't exist
3. Creates the initial `pipeline-state.md` file with all stages marked as pending (⏳)

**`post-stage.sh`**: Runs after every stage completes successfully. It:
1. Stages all changed files (`git add .`)
2. Creates a commit with a stage-specific message (e.g., `research: analyzed problem space`)
3. Updates the stage's status in `pipeline-state.md` to "done" with a timestamp

**`pre-gate.sh`**: Runs before every human gate. It validates:
1. The artifact file exists at the expected path
2. The file is not empty
3. The file has at least 100 words (warns if not, but doesn't block)

**Why separate hooks from agent logic?** Shell scripts are better than AI for deterministic, mechanical tasks. An AI running a git commit might make formatting mistakes, might add wrong files, or might behave differently each time. A shell script always does exactly the same thing. This is a key principle: **use AI for tasks that require judgment; use scripts for tasks that are purely mechanical.**

### `pipeline-state.md` — The State Tracker

Each project has a `pipeline-state.md` that tracks what has been done:

```markdown
# Pipeline State — engg-intelligence

| Stage      | Status    | Artifact              | Gate Decision | Notes                    |
|------------|-----------|-----------------------|---------------|--------------------------|
| research   | ✅ done   | docs/research.md      | auto          | 2026-06-11 01:15 UTC     |
| plan       | ✅ done   | docs/plan.md          | auto          | 2026-06-11 02:30 UTC     |
| prd        | 🔄 active | docs/prd.md           | ⛔ pending    |                          |
| spec       | ⏳ pending | —                     | —             |                          |
```

This file serves multiple purposes:
1. **Resume capability**: If you stop mid-pipeline (power outage, need to sleep, etc.), the orchestrator reads this file and knows exactly where to continue
2. **Audit trail**: You can see when each stage completed and what gate decision was made
3. **Status visibility**: At a glance, you know the current state of the project

---

## 11. The Example Project: Engineering Intelligence Platform

The `projects/engg-intelligence/` directory contains a real example of ClaudeForge in use. Let's walk through what we can learn from it.

### The Brief (`brief.md`)

The brief for the engg-intelligence project is a detailed 280-line document defining an "Engineering Intelligence Platform" — a dashboard for engineering managers that aggregates data from GitHub, Jira, ClickUp, Slack, PagerDuty, Zenduty, and Keka HRMS into unified team health metrics.

Key things a brief should contain (as demonstrated by this example):

**Users and Roles** (specific, not vague):
| Role | Access | Usage |
|---|---|---|
| Admin | Full access, configure integrations | Setup |
| Director/VP | All teams | Weekly |
| Engineering Manager | Own team only | Daily |
| Engineer | Own profile only | As-needed |

**Exact metrics to track** (67 metrics catalogued across: PR Health, Sprint Health, Throughput, Incident Health, DORA Metrics, Slack Signals, Collaboration)

**Integrations with specifics** (not just "GitHub" but "GitHub via GitHub App, webhooks for real-time, GraphQL for backfill")

**Tech stack preferences** (Python/FastAPI, TypeScript/React, PostgreSQL, Celery+Redis, Docker)

**Explicit out-of-scope** (mobile, real-time, IC performance scoring, public API, OAuth, alerting)

**Why this level of detail matters**: A vague brief produces vague research, which produces vague plans, which produces vague code. The quality of your brief is the single most important factor in the quality of the final output. The `brief-writer.md` skill exists precisely to help users write briefs that are this detailed.

### The Research Report (`docs/research.md`)

The research agent produced a 484-line report that illustrates what a good research artifact looks like. Let's look at the competitor analysis section as an example of the quality level:

| Competitor | Strengths | Weaknesses | Gap This Project Fills |
|---|---|---|---|
| LinearB | GitHub DORA, free tier, good EM UX | No Slack signals, no ClickUp, no Zenduty, cloud-only | Slack + APAC tools + self-hosted option |
| Jellyfish | Investment allocation, board reporting | $100K+/year, overkill for <200 engineers | Affordable + self-hostable |
| Swarmia | Team-first, working agreements | No Slack signals, no ClickUp/Zenduty | Incident health + APAC tools |

This is actionable research. It doesn't just list competitors — it explains specifically what gaps the project can fill, which directly informs the plan and PRD stages.

The research report also surfaces specific technical gotchas like:
- Slack rate limit change in May 2025: conversations.history is now severely restricted (15 messages/request, 1 request/minute)
- Zenduty's on-call API is rate-limited at only 40 requests/minute (much more restrictive than their general API)
- ClickUp has no native story points field — it varies by workspace configuration

These kinds of details, if missed at research time, would cause painful surprises during implementation.

### The Pipeline State (`pipeline-state.md`)

The current pipeline state shows the project is early stage — research has been generated, with all other stages pending. This is what the file looks like at the beginning:

```
| research   | ⏳ pending | —                 | auto    | |
| plan       | ⏳ pending | —                 | auto    | |
| prd        | ⏳ pending | —                 | ⛔ human | |
...
```

As stages complete, the orchestrator's `post-stage.sh` hook updates this file to show progress, timestamps, and gate decisions.

---

## 12. Agentic Engineering Principles

ClaudeForge embodies several important principles that apply broadly to building agentic AI systems. Understanding these will help you design your own agentic systems.

### Principle 1: Single Responsibility per Agent

Each agent has one job and does it well. The research agent doesn't plan; the plan agent doesn't write requirements; the PRD agent doesn't write code. This mirrors the Single Responsibility Principle from software engineering, applied to agents.

**Why it matters**: Mixing responsibilities into one agent makes each responsibility worse. An agent trying to simultaneously research, plan, and write a PRD produces mediocre work at each task. Focused agents produce better-quality specialized outputs.

### Principle 2: Artifacts Over Conversations

Every stage produces a concrete, written artifact that gets committed to git. The system doesn't rely on the AI "remembering" what it did in a previous conversation. Instead, it externalizes state into files.

**Why it matters**: LLMs have no persistent memory between sessions. If you close the terminal and come back, the AI remembers nothing. By writing everything to files and committing to git, the system becomes **stateless** — it can resume from any point just by reading the files that exist.

This is one of the most important patterns in agentic engineering: **never rely on conversational memory; always persist state to durable storage.**

### Principle 3: Human Gates at High-Leverage Points

Not every decision needs human input, but some decisions are so consequential that they need explicit approval. ClaudeForge gates at PRD, Spec, Code Review, and Final — not after every stage.

**Why it matters**: Too many gates make the system tedious (you might as well do it yourself). Too few gates mean you lose control. Good gate placement requires thinking about "where is the cost of a wrong decision highest?"

For software: wrong requirements (PRD) → everything built is wrong. Wrong architecture (Spec) → expensive rewrite. Bad code quality (Review) → security vulnerabilities in production. These are the right places to gate.

### Principle 4: Feedback Injection for Iteration

When a human rejects a stage, their feedback is injected verbatim into the agent's next run. The agent isn't just told "do it again" — it's told specifically what was wrong and what to change.

**Why it matters**: Generic re-runs produce similar outputs. Feedback-injected re-runs converge toward what the human actually wants. This is the agentic equivalent of how iteration works in human teams — code review with specific comments produces better revisions than "make it better."

### Principle 5: Explicit Escalation Paths

Every error path has an explicit handling strategy. The pipeline doesn't just fail silently. The bug-fix loop runs up to 5 times, then writes an escalation report. Malformed agent outputs are auto-retried once, then surfaced to the human. Every error leads somewhere.

**Why it matters**: In agentic systems that run autonomously, failures can be silent. The system keeps running while producing garbage. Explicit escalation paths ensure that failures are visible and handled — either by the system (auto-retry) or by a human (escalation report).

### Principle 6: Selective Context Passing

Agents receive only the context they need. The bug-fix agent doesn't receive the full research report. The implementation agent receives a summarized PRD rather than the full one.

**Why it matters**: This is counter-intuitive but important. More context is not always better. Irrelevant context:
1. Wastes expensive token budget (longer prompts = higher cost)
2. Can confuse the model (more text = more opportunities for the model to fixate on the wrong part)
3. Can push relevant information out of the "attention window" even within the context limit

Good agentic system design is as much about what you don't pass as what you do.

### Principle 7: Git as the Audit Trail

Every stage's output is committed to git. This means you have a complete, immutable history of every artifact the system produced, in the order it produced them.

**Why it matters**: When something goes wrong (and it will), you need to know: what did the research report say? What was the spec before we changed it? Git commits with descriptive messages make the pipeline's entire history reviewable. You can also roll back — if the implementation at Stage 5 is terrible, you can revert to the spec commit and start Stage 5 over.

### Principle 8: The Brief Drives Everything

The quality of every downstream artifact is limited by the quality of the input brief. A vague brief produces vague research, which produces a weak plan, which produces incomplete requirements, which produces incorrect architecture, which produces buggy code.

**Why it matters**: In agentic systems, garbage in = garbage out, but the garbage is harder to see because the AI produces confident-sounding output at every stage. A bad brief won't cause the system to crash — it will cause it to confidently build the wrong thing. This is why `brief-writer.md` skill exists and why the brief for the engg-intelligence project is 280 lines long.

---

## 13. How to Run This Yourself

### Prerequisites

Before running ClaudeForge, you need:
- **Claude Code** installed (`npm install -g @anthropic/claude-code`)
- **An Anthropic API key** (get one at console.anthropic.com)
- **Git** installed
- **GitHub CLI** (optional, for GitHub operations)

### Step 1: Clone and Set Up

```bash
git clone <this-repo>
cd claude-forge
```

### Step 2: Write Your Brief

Create your project directory (outside claude-forge) and write a brief:

```bash
mkdir -p ../my-project
echo "my-project=../my-project" >> projects.conf
```

Then create `../my-project/brief.md` with:

```markdown
# Project: [Your Project Name]

## Problem
[What problem does this solve? Who has this problem? How painful is it?]

## Users
[Who are the users? What are their roles? How often will they use it?]

## Must-Have Features (v1)
[List only what's essential for v1. Be ruthless.]

## Out of Scope (v1)
[Explicitly list what you're NOT building in v1.]

## Tech Stack Preferences
- Backend: [language/framework]
- Frontend: [if applicable]
- Database: [your preference]
- Hosting: [local/cloud/docker/etc.]

## Integrations
[List any external APIs or services this needs to connect to]

## Constraints
[Budget, timeline, team size, technical constraints]
```

**Tips for a good brief**:
- Name your users specifically (e.g., "Engineering managers at 20-100 person startups" not "developers")
- List all integrations with specifics
- Define "done" — what does v1 success look like?
- The brief-writer skill can guide you through this if you type: "I want to start a new project but haven't written a brief"

### Step 3: Start the Pipeline

Open Claude Code in the claude-forge directory:

```bash
claude
```

Then type:
```
build my-project
```

or more explicitly:
```
start pipeline for my-project
```

The orchestrator will:
1. Verify your brief exists
2. Run `hooks/pipeline-start.sh` to initialize the project
3. Begin Stage 1 (Research)

### Step 4: Interact at Gates

The pipeline will run automatically through Stages 1-3, then stop at the first human gate (PRD). You'll see:

```
════════════════════════════════════════
⛔ GATE: PRD REVIEW
Artifact: projects/my-project/docs/prd.md
════════════════════════════════════════

Summary:
• 6 must-have features defined (login, dashboard, team view, engineer view, admin panel, digests)
• 3 user personas: admin, engineering manager, engineer
• 18 acceptance criteria written
• Key open questions: real-time vs. polling, role inheritance model

Do you want to (A)pprove, (E)dit, or (R)eject with feedback?
```

Read `docs/prd.md` in your editor, then respond with A, E, or R.

### Step 5: Resume If Interrupted

If you need to stop and come back later:

```
resume pipeline for projects/my-project
```

The orchestrator reads `pipeline-state.md` and picks up where it left off.

### Step 6: Review the Output

When the pipeline finishes, your project will have:

```
projects/my-project/
├── brief.md                    (your original brief)
├── docs/
│   ├── research.md             (competitive research, tech choices)
│   ├── plan.md                 (scope, milestones, personas)
│   ├── prd.md                  (features, ACs, flows)
│   ├── tech-spec.md            (architecture, data models, APIs)
│   └── review.md               (code review findings)
├── code/
│   ├── README.md               (how to run)
│   ├── implementation-index.md (list of all files)
│   └── [all your source files]
├── tests/
│   ├── README.md               (how to run tests)
│   ├── unit/
│   ├── integration/
│   └── acceptance/
└── pipeline-state.md           (completed pipeline record)
```

All committed to git with per-stage commit messages.

---

## 14. Glossary

| Term | Definition |
|---|---|
| **Agent** | An AI (LLM) given a specific role, tools, and instructions to autonomously accomplish a goal |
| **Agentic Flow** | A sequence of AI agent actions organized to accomplish a multi-step task |
| **Artifact** | A document or file produced by an agent stage (e.g., research.md, prd.md) |
| **Brief** | A plain English description of what you want to build; the primary input to the pipeline |
| **CLAUDE.md** | A file of instructions that Claude reads as system-level context when operating in a directory |
| **Context Window** | The maximum amount of text an LLM can process at once; its "working memory" |
| **Gate** | A pause in the pipeline where a human must Approve, Edit, or Reject before continuing |
| **Hook** | A shell script that runs automatically at a specific point in the pipeline |
| **LLM** | Large Language Model — an AI trained on text that can generate contextually appropriate responses |
| **Orchestrator** | The top-level agent that coordinates the entire pipeline and manages subagents |
| **Pipeline** | The ordered sequence of stages that transforms a brief into tested code |
| **PRD** | Product Requirements Document — defines features, user stories, and acceptance criteria |
| **Skill** | A reusable instruction template that agents can invoke (like a function or library) |
| **Subagent** | A specialized agent spawned by the orchestrator to perform a specific stage |
| **Tech Spec** | Technical Specification — defines architecture, data models, API contracts |
| **Token** | The unit of text an LLM processes; roughly 4 characters or 0.75 words |
| **Acceptance Criteria (AC)** | Specific, binary, testable conditions that define when a feature is "done" |
| **DORA Metrics** | Four key software delivery metrics: Deployment Frequency, Lead Time, Change Failure Rate, MTTR |
| **Context Management** | The practice of controlling what information is passed to each agent to stay within context window limits |
| **Feedback Injection** | The practice of including human rejection feedback verbatim in an agent's re-run context |

---

## Summary

ClaudeForge is a demonstration of what modern agentic AI engineering looks like in practice. Let's recap the key ideas:

**Architecturally**: An orchestrator + 9 specialist subagents, each with a focused job, explicit inputs, and structured outputs. No agent does more than one job.

**For data flow**: Information accumulates stage by stage, from abstract (brief) to concrete (code + tests). Context is passed selectively — agents only receive what they need.

**For human oversight**: 4 gates at the highest-leverage decision points. A/E/R protocol for each. Feedback injection for iteration. Explicit escalation paths for failures.

**For reliability**: Git as audit trail. State in pipeline-state.md. Auto-retry on failures. Bug-fix loop with escalation after 5 iterations.

**For quality**: Specialized agents produce better output than generalist ones. Structured artifact templates ensure completeness. Code review and test suite verify the output.

The most important lesson from studying this codebase: **good agentic engineering is mostly about structure, not magic.** The AI doesn't need to be told to "be creative" or "think hard." It needs to be given a clear role, appropriate context, structured output requirements, and explicit instructions about how to handle edge cases. Structure + specificity = quality AI output.

---

*This tutorial was written to explain ClaudeForge to someone new to both the codebase and the concepts of agentic AI. If you find anything unclear or incorrect, the best way to improve it is to reject-and-feedback the relevant section using the same A/E/R protocol that ClaudeForge itself uses.*
