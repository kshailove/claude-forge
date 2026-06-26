# ClaudeForge Agent Guidelines

These rules apply to every subagent in the ClaudeForge pipeline.
Read them before doing any stage work.

## Output Discipline

- Write to `[PROJECT_PATH]` — never write files inside the claude-forge directory itself.
- Do not report completion until the artifact file is fully written and has real content.
- Never produce stub artifacts ("TODO: fill this in later"). Either write it or explicitly call it out-of-scope.
- Your artifact is your only output that matters. Conversational summaries are secondary.

## Specificity

- Be opinionated. Name the library, the version, the pattern. "Use FastAPI 0.115+ with SQLAlchemy 2.x async" not "use a Python web framework".
- Never say "consider using", "you might want to", or "depending on your needs" without following immediately with a concrete recommendation.
- Name the tradeoff and take a side. "We chose X over Y because Z" not "both are valid options".

## Scope Discipline

- Do only your stage's job. Do not start the next stage, anticipate later stages, or clean up earlier stages.
- If you notice a problem that belongs to a different stage, note it in an "Issues for next stage" section at the end of your artifact — do not fix it yourself.
- When human feedback is provided for a re-run, address every point explicitly. Don't silently incorporate feedback; call out each change you made.

## Style

- Use plain dash (-) instead of em dash (—) in all written output.
- Keep sentences direct. Omit filler phrases like "it's important to note that", "it's worth mentioning", "as previously discussed".
- Use present tense for decisions ("The system uses PostgreSQL") not future tense ("The system will use PostgreSQL").

## Commit Messages

When committing via `post-stage.sh`, commit messages follow this format:
```
[stage]: [one-line summary of what was produced]
```
Example: `research: competitive analysis and tech stack recommendations`

## On Uncertainty

- If you don't know something (rate limits, API behavior, version compatibility), say so explicitly rather than guessing.
- Flag uncertainties as "Open Questions" in your artifact so the next stage or the human can resolve them.
- Never invent API endpoints, library APIs, or configuration options.
