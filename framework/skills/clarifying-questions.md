# Skill: Clarifying Questions

Use this skill to generate scoping questions for a work item before the pipeline runs.
Questions are asked once, in a single batch, before any unattended work begins.

## When to generate questions

Generate questions when any of these are true:
- The work item description is under 30 words and leaves scope ambiguous
- The classification is `ambiguous` (from feature-classifier)
- Acceptance criteria are missing or vague
- The work item touches an area flagged as risky in context-discovery
- The ticket type is "Task" (not clearly bug or feature)

Do NOT generate questions if:
- The work item is a clear bugfix with a reproduction path
- The work item is detailed enough to implement without assumptions
- The ticket already includes acceptance criteria

## Question limits

Maximum 3 questions per work item. Prioritise:
1. Scope boundary questions (what's in vs out of this work item)
2. Acceptance criteria questions (how do we know this is done?)
3. Edge case questions (what should happen in X scenario?)

Never ask about:
- Tech stack choices (read architecture.md)
- Where to put the code (read implementation-index.md)
- Things that can be reasonably assumed from context

## Output format

Return questions for ALL work items in a single block. The orchestrator presents
this entire block to the human at once before any pipeline runs.

```
## Clarifying questions — please answer before I start

### Work item 1: [title or first 10 words]
1. [question]
2. [question]

### Work item 2: [title or first 10 words]
1. [question]

### Work item 3: [title or first 10 words]
(No questions — scope is clear)
```

## After the human answers

The orchestrator passes the answers back into the relevant mini-pipeline as context.
Treat the answers as additional acceptance criteria for that work item.
