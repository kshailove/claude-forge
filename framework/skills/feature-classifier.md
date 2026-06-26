# Skill: Feature Classifier

Use this skill after context-discovery to classify a work item as one of:
- `bugfix` — fixing a defect in existing behaviour
- `small-feature` — adding capability that fits within the existing architecture
- `large-feature` — adding capability that requires new data models, APIs, or integrations

## Inputs

- `work_item` — the natural language description or fetched ticket content
- `context` — the output from the context-discovery agent

## Classification rules

### Classify as `bugfix` if:
- The work item describes incorrect, broken, or unexpected behaviour
- Keywords present: "fix", "broken", "not working", "error", "crash", "regression",
  "incorrect", "failing", "bug", "issue"
- The expected change is to existing logic, not new capability

### Classify as `small-feature` if:
- The work item adds new behaviour, but:
  - Touches 2 or fewer existing components (from context-discovery output)
  - Does NOT require a new database table or significant schema change
  - Does NOT require a new external API integration
  - Does NOT require a new background job or service
- Estimated implementation: 1-3 files changed or added

### Classify as `large-feature` if any of these are true:
- Requires a new database table or significant schema migration
- Requires a new external API integration or service dependency
- Requires a new background job, worker, or service
- Touches 3 or more components
- Requires new authentication or authorisation logic
- Requires significant changes to the API surface (3+ new endpoints)
- Estimated implementation: 5+ files changed or added

## Ambiguity

If the classification is uncertain after applying these rules, flag it:

```
Classification: ambiguous
Leaning toward: [small-feature / large-feature]
Reason: [one sentence]
Include in clarifying questions: [the specific question that would resolve this]
```

The orchestrator will then include this in the clarifying questions batch.

## Output format

```
Classification: [bugfix / small-feature / large-feature / ambiguous]
Confidence: [high / medium / low]
Reason: [one sentence explaining the classification]
Components affected: [list from context-discovery]
```
