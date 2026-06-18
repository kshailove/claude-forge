# Skill: PRD Template

This skill provides the standard PRD structure for ClaudeForge projects.
The PRD agent uses this as its output template.

## Document Header

```markdown
# [Project Name] — Product Requirements Document

**Version:** 1.0
**Status:** Draft | Under Review | Approved
**Last updated:** [date]
**Authors:** ClaudeForge PRD Agent
**Approved by:** —

---
```

## Section Structure

The PRD agent must produce all sections below.
Sections marked * are mandatory even if brief.

### * 1. Overview
```markdown
## Overview

### Problem Statement
[2-3 sentences. What problem. Who has it. Why it matters now.]

### Solution
[2-3 sentences. What we're building. How it addresses the problem.]

### Success Metrics
| Metric | Target | How measured |
|--------|--------|--------------|
| [metric] | [target] | [method] |
```

### * 2. Users
```markdown
## Users

### Persona: [Name]
- **Role:** [job title / type]
- **Goals:** [what they want to achieve]
- **Pain points:** [what frustrates them today]
- **Key actions in this product:** [what they'll do here]
```

### * 3. Goals & Non-Goals
```markdown
## Goals
- [ ] [Measurable goal 1]
- [ ] [Measurable goal 2]

## Non-Goals (v1)
- [Explicit exclusion 1]
- [Explicit exclusion 2]
```

### * 4. Features
```markdown
## Features

### [Feature Name]
**Priority:** Must-have | Nice-to-have | Future
**Persona:** [which persona uses this]

**Description:**
[What this does from the user's perspective. No technical details.]

**User Story:**
As a [persona], I want to [action] so that [outcome].

**Acceptance Criteria:**
- [ ] [Testable criterion — observable, binary true/false]
- [ ] [Testable criterion]
- [ ] [Testable criterion]

**Edge Cases & Notes:**
- [Anything non-obvious]
```

### 5. User Flows
```markdown
## User Flows

### Flow: [Name]
[Describe step by step in plain English or ASCII]

Start: [entry point]
  → [Step 1]
  → [Step 2]
    → [Branch A] if [condition]
    → [Branch B] if [condition]
  → End: [outcome]
```

### 6. Data Requirements
```markdown
## Data Requirements

| Data | Source | Freshness needed | Sensitivity |
|------|--------|-----------------|-------------|
| [data] | [source] | [real-time/hourly/daily] | [public/internal/sensitive] |
```

### 7. Non-Functional Requirements
```markdown
## Non-Functional Requirements

### Performance
- Page load: < [Xms] for [percentile]
- API response: < [Xms] p95

### Security
- Auth: [mechanism]
- Data at rest: [encryption requirement]
- Access control: [role-based? what roles?]

### Reliability
- Uptime target: [X]%
- Data retention: [X days/months]
```

### 8. Open Questions
```markdown
## Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| 1 | [question] | [who decides] | [when needed] |
```

## Formatting Rules

- Use checkboxes `- [ ]` for acceptance criteria so they can be tracked
- Feature priorities: only 40% of features should be Must-have
- Every AC must be a complete sentence that could be put in a test name
- No acceptance criterion should contain "and" (split into two)
