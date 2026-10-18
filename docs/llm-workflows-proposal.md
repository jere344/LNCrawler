# Centralizing LLM workflows — proposal

## Current state

Two workflows, each with its own tables and plumbing:

| Workflow    | Work item table                                                      | LLM output stored on                                                            | Budget / usage                           | Retry                        |
| ----------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------- | ---------------------------- |
| Novel merge | `MergeCandidate` (pending/approved/rejected/merged/skipped)          | `llm_verdict`, `llm_reason`, `llm_model`, `llm_checked_at` columns              | `LLMUsage(purpose='novel')`              | none (no attempts field)     |
| Tag merge   | `TagCluster` (pending/applied/no_merge/review/rejected/undone/error) | `llm_response`, `llm_model`, `llm_batch`, `judged_at`, `error`, `requeue_count` | `TagLLMCall` + `LLMUsage(purpose='tag')` | `_requeue`, `MAX_REQUEUES=3` |

Shared code already exists (`services/llm_service._post_chat`, token budget helpers), but each
workflow re-implements: prompt building, response parsing, status/attempt tracking, budget
checks, scheduler job, management command and admin "requeue" action.

Adding R18 tag classification, synopsis cleanup, genre inference, etc. would mean a new
table + scheduler job + admin + retry logic each time.

## Should we centralize?

Yes, but only the **LLM call layer**, not the domain tables. `MergeCandidate` and `TagCluster`
are real domain objects (they have their own review/apply/undo lifecycle, unrelated to the LLM)
and should stay. What is duplicated is "ask the LLM about X, record the answer, retry, budget".

## Option A — Central `LLMRequest` log + task registry (recommended)

One table, one runner, one admin:

```python
class LLMRequest(models.Model):
    task = CharField(max_length=50, db_index=True)        # 'novel_merge', 'tag_merge', 'tag_r18', ...
    # generic target (or just target_type + target_id ints, simpler and indexable)
    target_type = CharField(max_length=50)
    target_id = BigIntegerField()
    status = CharField(choices=[pending, running, done, failed, skipped], db_index=True)
    priority = SmallIntegerField(default=0)
    attempts = SmallIntegerField(default=0)
    not_before = DateTimeField(null=True)                  # backoff / rate-limit retry_after
    model = CharField(max_length=100, blank=True)
    prompt_version = CharField(max_length=20)              # lets you re-run when the prompt changes
    request = JSONField()                                  # messages sent (or a hash + inputs)
    response = JSONField(null=True)                        # parsed result
    raw_response = TextField(blank=True)
    error = TextField(blank=True)
    prompt_tokens / completion_tokens = IntegerField(default=0)
    batch = UUIDField(null=True)
    created_at / finished_at
    class Meta:
        indexes = [Index(fields=['status', 'task', 'not_before'])]
        constraints = [UniqueConstraint(fields=['task','target_type','target_id','prompt_version'],
                                        condition=Q(status__in=['pending','running']), name='one_open_request')]
```

Each workflow registers a small handler class:

```python
class LLMTask(Protocol):
    name: str
    prompt_version: str
    usage_purpose: str          # keys its token estimate (llm_service.estimated_tokens)
    def build_messages(self, target) -> list[dict]: ...
    def parse(self, raw: str) -> dict: ...            # raise LLMParseError
    def apply(self, target, result: dict) -> None: ... # writes domain state (MergeCandidate status, Tag.is_adult, ...)

REGISTRY = {t.name: t for t in (NovelMergeTask(), TagMergeTask(), TagR18Task())}
```

A single runner (one scheduler job, one `run_llm_requests --task X --limit N` command):
`select_for_update(skip_locked=True)` pending rows → check the single shared daily budget
covers the task's estimated cost → `_post_chat` → `parse`
→ `apply` → store tokens. Errors increment `attempts`, set `not_before` with exponential
backoff or `retry_after`, and mark `failed` after N attempts.

Domain tables keep their decision columns (`MergeCandidate.status`, `TagCluster.status`) and
gain a nullable FK `last_llm_request` for traceability; the `llm_*` columns become redundant
and can be dropped after a data migration.

**Pros:** new LLM workflow = one handler class + enqueue call, no migration; one admin with
filters by task/status, raw response view, bulk "requeue"; unified cost reporting; prompt
versioning gives you re-runs for free.
**Cons:** one migration project for the existing two workflows; generic target loses DB FK
integrity (acceptable for a log).

## Option B — Shared abstract base model

`class LLMJudgedMixin(models.Model): status, attempts, llm_model, llm_response, error, ... (abstract)`
used by `MergeCandidate`, `TagCluster`, and every future workflow table, plus a shared
runner over a queryset.

**Pros:** smallest change, keeps FKs. **Cons:** still one table per workflow (what you dislike),
usage still needs a separate table, admin still duplicated.

## Option C — Generic job queue (Celery/Django-Q/Procrastinate)

Move LLM calls into a task queue with retries/rate limits.
**Pros:** robust retries, concurrency. **Cons:** new infra; doesn't solve storing results
or auditing; can be combined later with Option A (the queue just executes `LLMRequest` rows).

## Recommendation & migration path

Option A, incrementally:

1. Add `LLMRequest` + registry + runner; implement the **new R18 tag classifier**
   (`TagR18Task`: batch ~50 untagged tags per request, answer `{tag: bool, confidence}`,
   `apply` sets `Tag.is_adult` only above a confidence threshold, otherwise leaves it for
   admin review) directly on it — no new table needed.
2. Port tag merge (`judge_tag_clusters`) to a handler; `TagLLMCall` budget → `LLMRequest` sums.
3. Port novel merge; replace `LLMUsage` reads with `LLMRequest` aggregates; drop old columns.
4. One admin (`LLMRequestAdmin`) with requeue/retry/raw view; remove per-workflow requeue actions.

The R18 flag on tags (`Tag.is_adult`, admin actions, propagation to sources,
`recompute_adult_from_tags`) is already implemented and independent of this choice.

## Status

Implemented (Option A, step 1):

- `LLMRequest` queue/log model (`models/llm_models.py`, migration `0084_llmrequest`).
- `LLMTask` registry and runner (`services/llm_tasks.py`), with `run_task` claiming
  rows via `select_for_update(skip_locked=True)`, retry backoff, and stuck-row recovery.
- `TagR18Task` (`tag_r18`): batches unflagged tags, sets `Tag.is_adult` only at or above
  `TAG_R18_LLM_MIN_CONFIDENCE`, and propagates to sources via `mark_sources_adult`.
- One request cap and one token budget for all workflows (`LLM_DAILY_REQUESTS`,
  `LLM_DAILY_TOKENS`; they share the same API), counted from `LLMUsage`. The
  per-workflow call limits (`MERGE_LLM_DAILY_LIMIT`, `TAG_LLM_DAILY_LIMIT`) and the
  `TagLLMCall` table are gone.
  Each request type has a worst-case estimate (reply cap + prompt reserve,
  `llm_service.estimated_tokens` / `can_afford`); a request only starts when the
  remaining budget covers it. The novel and tag judges use the same check.
- `run_llm_requests <task>` management command (`--limit`, `--dry-run`) and the
  `run_llm_tag_r18` scheduler job.
- `LLMRequestAdmin` under "Jobs & Scheduler" with requeue and re-apply actions.

Not started: steps 2 and 3 (porting tag merge and novel merge to the queue).
