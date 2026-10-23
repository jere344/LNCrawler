"""Find probable duplicate authors and queue each pair for LLM judging.

Nothing is merged here. Every pair found by one of three rules becomes a pending
``author_merge`` candidate, and the ``run_llm`` command (``AuthorMergeTask``) decides it. The rule is kept in the candidate's ``signals``.

A. Normalized equality: authors that share one key ("I Eat Tomatoes" and
   "i eat  tomatoes"), rule ``normalized``.
B. Mixed script: a name such as "Cuttlefish That Loves Diving 爱潜水的乌贼" whose
   Latin parts all resolve to existing authors. An unresolved CJK part is ignored.
   If the resolved parts are one author, the pair is that author and the mixed name.
   If they are two, the pair is those two. Rule ``mixed_script``. Resolving never
   creates an author.
C. Cross-source: in one novel, two sources that differ by exactly one author
   each probably credit the same person under two names. Rule ``cross_source``.

A pair that already has a candidate in an open status only has its signals refreshed. A
pair with a candidate that is decided (rejected, applied, undone) or blocked by a
merge chain (``candidate_blocks``) is skipped. Re-running is safe.
"""
from collections import defaultdict
from itertools import combinations

from django.core.management.base import BaseCommand
from django.db.models import Count

from lncrawler_api.models import Author, Candidate, NovelFromSource
from lncrawler_api.services.candidate_blocks import blocked_pairs, pair_key
from lncrawler_api.services.merge_common import ordered_pair, sorted_pk_signature
from lncrawler_api.utils.author_names import script_runs_with_kind

# Candidate pairs keep at most this many novel ids in their signals.
NOVEL_IDS_CAP = 10


class Command(BaseCommand):
    help = "Queue probable duplicate authors for LLM judging."

    def handle(self, *args, **options):
        self.counts = defaultdict(int)
        self.blocked = blocked_pairs(Candidate.KIND_AUTHOR_MERGE)

        self._rule_a()
        self._rule_b()
        self._rule_c()

        self.stdout.write(self.style.SUCCESS(
            f"queued {self.counts['queued']}; "
            f"skipped {self.counts['known']} known"
        ))

    def _store(self, a, b, rule, signals):
        """Queue the pair as a pending candidate, or refresh the open one that names it."""
        first, second = ordered_pair(a, b, key=lambda author: author.pk)
        signature = sorted_pk_signature([first.pk, second.pk])
        row = Candidate.objects.filter(kind=Candidate.KIND_AUTHOR_MERGE, signature=signature).first()
        decided = row is not None and row.status not in Candidate.OPEN_STATUSES
        if decided or pair_key(first.pk, second.pk) in self.blocked:
            self.counts["known"] += 1
            return
        self.counts["queued"] += 1
        signals = {"rule": rule, **signals}
        names = [first.name, second.name]
        if row is None:
            Candidate.objects.create(
                kind=Candidate.KIND_AUTHOR_MERGE,
                signature=signature,
                target_ids=[first.pk, second.pk],
                target_names=names,
                signals=signals,
            )
        else:
            row.target_names = names
            row.signals = signals
            row.save(update_fields=["target_names", "signals", "updated_at"])

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
                self._store(survivor, other, "normalized", {"normalized": key})

    def _rule_b(self):
        for author in list(Author.objects.order_by("pk")):
            runs = script_runs_with_kind(author.name)
            if len(runs) < 2:
                continue
            found = [(kind, Author.find(run)) for kind, run in runs]
            # An unresolved Latin run skips the name; an unresolved CJK run is ignored.
            if any(match is None for kind, match in found if kind == "latin"):
                continue
            resolved = {
                match.pk: match for _kind, match in found
                if match is not None and match.pk != author.pk
            }
            signals = {"combined_name": author.name}
            if len(resolved) == 1:
                self._store(author, next(iter(resolved.values())), "mixed_script", signals)
            elif len(resolved) == 2:
                first, second = resolved.values()
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
            if low not in authors or high not in authors:
                continue  # blocked author
            ids = sorted(str(pk) for pk in novel_ids)  # novel pks are UUIDs, not JSON
            self._store(
                authors[low], authors[high], "cross_source",
                {"novels": len(ids), "novel_ids": ids[:NOVEL_IDS_CAP]},
            )
