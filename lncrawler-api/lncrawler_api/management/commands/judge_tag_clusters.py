"""Ask the LLM which tags in pending clusters are interchangeable, then apply it.

Stage 2 of automatic tag merging. Packs pending ``TagCluster`` rows into a few
chat calls per run (``TAG_LLM_TAGS_PER_CALL`` tags each), stores the validated
answer on each cluster, and hands it to ``apply_cluster``, which merges the
sets that pass the safeguards and holds the rest for review.

Runs as a *bounded* scheduler task: a few calls per tick, capped by a daily
budget counted as distinct ``TagCluster.llm_batch`` values judged today. With
no API key it is a no-op.
"""

import logging
import uuid
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from lncrawler_api.models import TagCluster, TagLLMCall
from lncrawler_api.services import llm_service
from lncrawler_api.services import tag_merge_service as tms

logger = logging.getLogger("lncrawler_api.merge")

# Pending clusters inspected per packing pass.
PACK_WINDOW = 200
# Prompt tokens allowed for on top of TAG_LLM_MAX_TOKENS before a call is made.
PROMPT_TOKEN_RESERVE = 3000


class Command(BaseCommand):
    help = "Ask the LLM to judge pending tag clusters and apply the merges it is sure of."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Max LLM calls this run (0 = settings default).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Count pending clusters but do not call the API.")

    def handle(self, *args, **options):
        if not llm_service.is_configured():
            self.stdout.write("LLM not configured (MERGE_LLM_API_KEY empty); nothing to do.")
            return

        daily_limit = settings.TAG_LLM_DAILY_LIMIT
        today = timezone.localdate()
        # Counted from the call ledger, so re-queuing or clearing a cluster never refunds a call.
        used_today = TagLLMCall.objects.filter(created_at__date=today).count()
        budget = daily_limit - used_today
        if budget <= 0:
            self.stdout.write(f"LLM daily budget reached ({used_today}/{daily_limit}); skipping.")
            return
        calls = min(options["limit"] or settings.TAG_LLM_CALLS_PER_TICK, budget)

        # Fresh clusters first; clusters sent back after a changed plan go to the back.
        pending = TagCluster.objects.filter(
            status=TagCluster.STATUS_PENDING
        ).order_by("requeue_count", "created_at", "pk")
        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] {pending.count()} pending cluster(s); up to {calls} call(s) this run."
            )
            return

        model = settings.MERGE_LLM_MODEL
        tally = Counter()
        made = 0
        # Clusters already sent to the model this run. A cluster requeued by a
        # failed call is not picked again until the next run.
        attempted = set()
        for _ in range(calls):
            # Checked before every call: one call can spend many tokens.
            reserve = settings.TAG_LLM_MAX_TOKENS + PROMPT_TOKEN_RESERVE
            if llm_service.token_budget_left() < reserve:
                self.stdout.write(
                    f"LLM daily token budget too low ({llm_service.tokens_used_today()}"
                    f"/{settings.MERGE_LLM_DAILY_TOKENS} used); stopping this tick."
                )
                break
            batch = self._next_batch(pending, attempted)
            if not batch:
                if not pending.exclude(pk__in=attempted).exists():
                    break
                continue
            outcome = self._judge(batch, model, tally)
            if outcome == "rate_limited" or outcome == "failed":
                break
            made += 1

        summary = ", ".join(f"{count} {status}" for status, count in sorted(tally.items()))
        self.stdout.write(self.style.SUCCESS(
            f"judged {sum(tally.values())} cluster(s)"
            + (f": {summary}" if summary else "")
            + f"; daily {used_today + made}/{daily_limit}"
        ))

    @staticmethod
    def _next_batch(pending, attempted):
        """Pack the oldest pending clusters until the call holds enough tags.

        A cluster that was requeued after a failed call (``requeue_count > 0``)
        is judged alone, so a truncation caused by packing heals itself.
        Clusters whose ids are in ``attempted`` are skipped, and every cluster
        put in the batch is added to ``attempted``.
        """
        batch, total = [], 0
        for cluster in list(pending.exclude(pk__in=attempted)[:PACK_WINDOW]):
            tags = tms.refresh_cluster_members(cluster)
            if len(tags) < 2:
                cluster.status = TagCluster.STATUS_NO_MERGE
                cluster.save(update_fields=["status", "updated_at"])
                continue
            if cluster.requeue_count and batch:
                # Left for a call of its own; requeued clusters sort to the back.
                break
            batch.append((cluster, tags))
            attempted.add(cluster.pk)
            total += len(tags)
            if cluster.requeue_count or total >= settings.TAG_LLM_TAGS_PER_CALL:
                break
        return batch

    def _judge(self, batch, model, tally):
        """Run one LLM call for ``batch``. Returns "ok", "rate_limited" or "failed"."""
        usage = tms.tag_usage([tag.pk for _cluster, tags in batch for tag in tags])
        groups, label_maps = [], []
        for _cluster, tags in batch:
            labelled = [(f"t{number}", tag) for number, tag in enumerate(tags, 1)]
            groups.append([(label, tag.name, usage.get(tag.pk, 0)) for label, tag in labelled])
            label_maps.append({label: tag.pk for label, tag in labelled})

        batch_id = uuid.uuid4()
        now = timezone.now()
        try:
            data = llm_service.chat_json(
                tms.build_judge_messages(groups), max_tokens=settings.TAG_LLM_MAX_TOKENS
            )
            results = tms.parse_judge_response(data, label_maps)
        except llm_service.RateLimited as exc:
            # A 429 never reached the model, so it is not charged.
            self.stdout.write(f"Rate limited (retry-after={exc.retry_after}); stopping this tick.")
            return "rate_limited"
        except llm_service.LLMParseError as exc:
            # The call was made and paid for, so it counts against the budget.
            # The whole batch goes back to pending; at MAX_REQUEUES it becomes error.
            TagLLMCall.objects.create(batch=batch_id)
            reason = f"LLM answer unusable, re-queued: {exc}"[:500]
            for cluster, _tags in batch:
                tally[tms._requeue(cluster, reason)] += 1
            return "ok"
        except llm_service.LLMError as exc:
            TagLLMCall.objects.create(batch=batch_id)
            logger.warning("LLM judge failed for tag clusters: %s", exc)
            return "failed"

        TagLLMCall.objects.create(batch=batch_id)
        for (cluster, _tags), sets in zip(batch, results):
            cluster.llm_response = {"sets": sets}
            cluster.llm_model = model
            cluster.llm_batch = batch_id
            cluster.judged_at = now
            cluster.save(update_fields=[
                "llm_response", "llm_model", "llm_batch", "judged_at", "updated_at"
            ])
            tally[tms.apply_cluster(cluster)] += 1
        return "ok"
