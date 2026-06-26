# Skill: Brief Writer

Use this skill when a user wants to start a new project but hasn't written a brief yet,
or when their brief is too vague to run the pipeline on.

## When to Invoke

The orchestrator calls this skill when:
- `[PROJECT_PATH]/brief.md` doesn't exist
- The user says "I want to build X" without a detailed brief
- A brief exists but is under ~200 words

## Your Job

Interview the user to extract enough information to write a solid brief. Then write the brief for them.

## Interview Questions

Ask these conversationally — not all at once. Adapt based on what they've already said.

**About the product:**
1. What problem does this solve? Who has this problem?
2. Who are the users? (roles, technical level, company type)
3. What does success look like in 3 months?

**About the features:**
4. What are the 3 most important things it must do?
5. What should it explicitly NOT do in v1?
6. Are there existing tools this replaces or integrates with?

**About the tech:**
7. Do you have a preference for tech stack? (language, framework, database)
8. Where will this be hosted/deployed?
9. Does it need to integrate with specific third-party APIs or services?
10. Any auth/security requirements? (SSO, OAuth, roles)

**About constraints:**
11. Is there a deadline or time budget?
12. Who will be building this? (solo, small team, specific skills)

## Brief Template

Once you have the answers, write `[PROJECT_PATH]/brief.md`:

```markdown
# [Project Name] — Brief

## Problem
[2-3 sentences: what problem, who has it, how painful]

## Solution
[2-3 sentences: what you're building and how it addresses the problem]

## Users
- **[Persona 1]:** [description, what they need]
- **[Persona 2]:** [description, what they need]

## Core Features (v1)
1. [Feature 1] — [one line description]
2. [Feature 2] — [one line description]
3. [Feature 3] — [one line description]

## Out of Scope (v1)
- [Thing 1]
- [Thing 2]

## Integrations
- [Tool/API 1] — [what data/action]
- [Tool/API 2] — [what data/action]

## Tech Preferences
- Language: [preference or "no preference"]
- Framework: [preference or "no preference"]
- Database: [preference or "no preference"]
- Hosting: [preference or "no preference"]
- Auth: [SSO/OAuth/username-password/etc]

## Constraints
- Timeline: [if any]
- Team: [who's building it]
- Other: [anything else]
```

## After Writing the Brief

Show the brief to the user and ask:
"Does this capture what you want to build? Any corrections before I start the pipeline?"

Wait for confirmation before proceeding.
