"""Find probable duplicate authors: merge the sure ones, queue the doubtful ones.

Three rules, run in this order. Every candidate is a pair of authors. A pair
whose signature already has a row, in any status, is skipped, so re-running is
safe. Rule A is the exception: it still merges such a pair, unless its row was
rejected or undone.

A. Normalized equality: authors that share one key ("I Eat Tomatoes" and
   "i eat  tomatoes") are merged at once, reason ``normalized``.
B. Mixed script: a name such as "Cuttlefish That Loves Diving 爱潜水的乌贼" whose
   Latin and CJK parts all resolve to existing authors. If they resolve to one
   author, the mixed name is merged into it at once. If they resolve to two, the
   pair is queued, reason ``mixed_script``. Resolving never creates an author.
C. Cross-source: in one novel, two sources that differ by exactly one author
   each probably credit the same person under two names. Queued, reason
   ``cross_source``.

Nothing here calls the LLM: ``judge_author_candidates`` (``AuthorMergeTask``)
decides the queued pairs. ``--dry-run`` reports what would happen and writes nothing.
"""
from collections import defaultdict
from itertools import combinations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from lncrawler_api.models import Author, AuthorMergeCandidate, NovelFromSource
from lncrawler_api.services.author_merge_service import merge_candidate, pick_target
from lncrawler_api.services.merge_common import ordered_pair, sorted_pk_signature
from lncrawler_api.utils.author_names import script_runs

# Candidate pairs keep at most this many novel ids in their signals.
NOVEL_IDS_CAP = 10


class Command(BaseCommand):
    help = "Merge duplicate authors by normalized name and queue doubtful pairs for LLM judging."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be merged or queued; write nothing.")

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.counts = defaultdict(int)

        self._rule_a()
        self._rule_b()
        self._rule_c()

        prefix = "dry run: nothing written, would " if self.dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}merge {self.counts['merged']}, queue {self.counts['queued']}; "
            f"skipped {self.counts['known']} known; "
            f"{self.counts['error']} error(s)"
        ))

    def _is_new_pair(self, a, b):
        """False for a pair that already has a row, in any status."""
        if AuthorMergeCandidate.objects.filter(signature=sorted_pk_signature([a.pk, b.pk])).exists():
            self.counts["known"] += 1
            return False
        return True

    def _store(self, a, b, reason, signals, merge_into=None):
        """Queue the pair as pending, or merge it at once into ``merge_into`` when given.

        A row of the same pair is reused instead of creating one. The row and the
        merge commit together, so a failed merge leaves no pending row.
        Returns the surviving author after a merge, or None when nothing was merged.
        """
        if self.dry_run:
            self.counts["merged" if merge_into is not None else "queued"] += 1
            return None
        first, second = ordered_pair(a, b, key=lambda author: author.pk)
        signature = sorted_pk_signature([first.pk, second.pk])
        with transaction.atomic():
            candidate = (
                AuthorMergeCandidate.objects.filter(signature=signature).first()
                or AuthorMergeCandidate(signature=signature)
            )
            candidate.author_ids = [first.pk, second.pk]
            candidate.author_names = [first.name, second.name]
            candidate.signals = signals
            candidate.reason = reason
            candidate.save()
            if merge_into is None:
                self.counts["queued"] += 1
                return None
            outcome = merge_candidate(candidate, target=merge_into)
        if outcome == "merged":
            self.counts["merged"] += 1
            return merge_into
        if outcome == "error":
            self.counts["error"] += 1
        return None

    def _rule_a(self):
        keys = list(
            Author.objects.exclude(normalized="")
            .order_by()
            .values("normalized")
            .annotate(n=Count("pk"))
            .filter(n__gt=1)
            .values_list("normalized", flat=True)
        )
        for key in keys:
            authors = list(Author.objects.filter(normalized=key).order_by("pk"))
            survivor = authors[0]
            for other in authors[1:]:
                existing = AuthorMergeCandidate.objects.filter(
                    signature=sorted_pk_signature([survivor.pk, other.pk])
                ).first()
                if existing is not None and existing.status in (
                    AuthorMergeCandidate.STATUS_REJECTED, AuthorMergeCandidate.STATUS_UNDONE,
                ):
                    self.counts["known"] += 1
                    continue
                merged_into = self._store(
                    survivor, other, "normalized", {"normalized": key},
                    merge_into=pick_target(survivor, other),
                )
                if merged_into is not None:
                    survivor = merged_into

    def _rule_b(self):
        for author in list(Author.objects.order_by("pk")):
            runs = script_runs(author.name)
            if len(runs) < 2:
                continue
            found = [Author.find(run) for run in runs]
            if any(match is None for match in found):
                continue
            resolved = {match.pk: match for match in found if match.pk != author.pk}
            signals = {"combined_name": author.name}
            if len(resolved) == 1:
                target = next(iter(resolved.values()))
                if self._is_new_pair(author, target):
                    self._store(author, target, "mixed_script", signals, merge_into=target)
            elif len(resolved) == 2:
                first, second = resolved.values()
                if self._is_new_pair(first, second):
                    self._store(first, second, "mixed_script", signals)

    def _rule_c(self):
        by_novel = defaultdict(lambda: defaultdict(set))
        rows = (
            NovelFromSource.authors.through.objects.order_by()
            .values_list("novelfromsource__novel_id", "novelfromsource_id", "author_id")
        )
        for novel_id, source_id, author_id in rows.iterator(chunk_size=20000):
            by_novel[novel_id][source_id].add(author_id)

        pairs = defaultdict(set)  # (low pk, high pk) -> novel ids
        for novel_id, sources in by_novel.items():
            for (_, first), (_, second) in combinations(sources.items(), 2):
                only_first, only_second = first - second, second - first
                if len(only_first) == 1 and len(only_second) == 1:
                    pairs[tuple(sorted(only_first | only_second))].add(novel_id)

        authors = Author.objects.in_bulk({pk for key in pairs for pk in key})
        for (low, high), novel_ids in sorted(pairs.items()):
            a, b = authors[low], authors[high]
            if not self._is_new_pair(a, b):
                continue
            ids = sorted(str(pk) for pk in novel_ids)  # novel pks are UUIDs, not JSON
            self._store(a, b, "cross_source", {"novels": len(ids), "novel_ids": ids[:NOVEL_IDS_CAP]})
