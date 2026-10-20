# AGENTS.md

## Delegation
- Codebase exploration: delegate to the `explorer` subagent (Haiku). Do not read many files yourself.
- Applying an approved plan: delegate to the `implementer` subagent (Haiku).
- Reviewing the implementer's changes: delegate to the `reviewer` subagent (Haiku) first.
- Planning, design decisions, and the final call on the reviewer's findings: do these yourself (Opus).

## Local database is dev data, not prod
The local containers (`lncrawler-api-1`, its Postgres) hold dev data, not a copy of prod. Do not treat
row counts or contents as what prod has. When the question is
about prod, ask for the prod data (an admin page, an export) instead of drawing conclusions locally.

## Running the backend tests
Run them inside the running API container (Django test runner, Postgres):

```bash
docker exec lncrawler-api-1 python manage.py test lncrawler_api auth_app --parallel 8 --keepdb
```

- Takes ~15–20s. `--keepdb` reuses the test database between runs. New migrations are still applied; drop it after editing or deleting an existing migration, or if the schema looks stale.
- To run a subset, pass a dotted label instead of the apps, e.g. `lncrawler_api.tests.test_tags`.
- Add `--durations 20` to list the slowest tests.
