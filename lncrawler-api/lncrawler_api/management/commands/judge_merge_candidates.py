"""Adjudicate gray-band merge candidates with an LLM (optional).

Selects pending review candidates that have not been judged yet, asks the
configured OpenAI-compatible model whether each pair is the same novel, and
stores the verdict on the ``MergeCandidate`` for the admin reviewer.

Runs as a *bounded* scheduler task: a few calls per tick, capped by a daily
budget derived from ``MergeCandidate.llm_checked_at`` (no extra state), so a
slow or rate-limited provider never blocks the rest of maintenance. With no
API key configured it is a no-op and the deterministic queue still works.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from lncrawler_api.models import MergeCandidate
from lncrawler_api.services import llm_service

logger = logging.getLogger("lncrawler_api.merge")


class Command(BaseCommand):
    help = "Ask the LLM to adjudicate pending merge candidates (gray band)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Max calls this run (0 = settings default).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Select candidates but do not call the API.")

    def handle(self, *args, **options):
        if not llm_service.is_configured():
            self.stdout.write("LLM not configured (MERGE_LLM_API_KEY empty); nothing to do.")
            return

        daily_limit = getattr(settings, "MERGE_LLM_DAILY_LIMIT", 20)
        today = timezone.localdate()
        used_today = MergeCandidate.objects.filter(llm_checked_at__date=today).count()
        budget = daily_limit - used_today
        if budget <= 0:
            self.stdout.write(f"LLM daily budget reached ({used_today}/{daily_limit}); skipping.")
            return
        limit = options["limit"] or getattr(settings, "MERGE_LLM_LIMIT_PER_TICK", 20)
        limit = min(limit, budget)

        candidates = list(
            MergeCandidate.objects.filter(
                status=MergeCandidate.STATUS_PENDING,
                decision=MergeCandidate.DECISION_REVIEW,
                llm_checked_at__isnull=True,
            )
            .select_related("novel_a", "novel_b")
            .prefetch_related(
                "novel_a__sources__authors",
                "novel_a__sources__alternative_titles",
                "novel_b__sources__authors",
                "novel_b__sources__alternative_titles",
            )
            .order_by("-certainty")[:limit]
        )
        if not candidates:
            self.stdout.write("No unjudged review candidates.")
            return
        if options["dry_run"]:
            self.stdout.write(f"[dry-run] would judge {len(candidates)} candidate(s).")
            return

        model = getattr(settings, "MERGE_LLM_MODEL", "openai/gpt-oss-20b")
        judged = rate_limited = failed = 0
        for candidate in candidates:
            if candidate.novel_a is None or candidate.novel_b is None:
                continue
            try:
                verdict = llm_service.judge(
                    self._profile(candidate.novel_a), self._profile(candidate.novel_b)
                )
            except llm_service.RateLimited as exc:
                self.stdout.write(
                    f"Rate limited (retry-after={exc.retry_after}); stopping this tick."
                )
                rate_limited += 1
                break
            except llm_service.LLMError as exc:
                logger.warning("LLM judge failed for %s: %s", candidate.pk, exc)
                failed += 1
                break

            candidate.llm_verdict = verdict
            candidate.llm_reason = verdict.get("reason", "")
            candidate.llm_model = model
            candidate.llm_checked_at = timezone.now()
            candidate.save(update_fields=[
                "llm_verdict", "llm_reason", "llm_model", "llm_checked_at", "updated_at"
            ])
            judged += 1

        self.stdout.write(self.style.SUCCESS(
            f"judged {judged} candidate(s); {failed} error(s); {rate_limited} rate-limited; "
            f"daily {used_today + judged}/{daily_limit}"
        ))

    @staticmethod
    def _profile(novel):
        titles = [novel.title] if novel.title else []
        alts, authors, languages = set(), set(), set()
        synopsis = ""
        for src in novel.sources.all():
            if src.title and src.title not in titles:
                titles.append(src.title)
            if src.language:
                languages.add(src.language)
            if not synopsis and src.synopsis:
                synopsis = src.synopsis
            for author in src.authors.all():
                authors.add(author.name)
            for alt in src.alternative_titles.all():
                alts.add(alt.name)
        return {
            "title": novel.title or (titles[0] if titles else ""),
            "titles": titles,
            "alternative_titles": sorted(alts),
            "authors": sorted(authors),
            "languages": sorted(languages),
            "synopsis": (synopsis or "")[:600],
        }
