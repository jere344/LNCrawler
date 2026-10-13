# CLAUDE.md

## Delegation
- Codebase exploration: delegate to the `explorer` subagent (Haiku). Do not read many files yourself.
- Applying an approved plan: delegate to the `implementer` subagent (Haiku).
- Reviewing the implementer's changes: delegate to the `reviewer` subagent (Haiku) first.
- Planning, design decisions, and the final call on the reviewer's findings: do these yourself (Opus).
