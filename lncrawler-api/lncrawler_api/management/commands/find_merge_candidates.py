"""Find probable duplicate novels across sources and queue them for review.

Cheap deterministic funnel:

1. Block — group novels by normalized title, alternative title, author,
   ``novelupdates_url`` and cover dHash. Only novels sharing a block are ever
   compared, so this is not O(N^2).
2. Score — combine the per-signal matches into a single 0..1 ``certainty``
   (noisy-OR, so independent signals corroborate each other).
3. Store — write a ``MergeCandidate`` per pair. Nothing is merged unless
   ``certainty`` clears ``MERGE_AUTO_SCORE`` (default >1, so auto-merge is off
   until the threshold is tuned against real data); the rest wait for the admin
   review page.

Re-running is safe: pairs a human already rejected/merged are left untouched.
"""
import re
import unicodedata
from collections import defaultdict

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models.functions import Upper
from django.core.management.base import BaseCommand
from django.db import transaction

from lncrawler_api.models import MergeCandidate, Novel, NovelFromSource, NovelSimilarity

_PAREN_RE = re.compile(r"[\(\[\{][^)\]\}]*[\)\]\}]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Per-signal weights fed into the noisy-OR. ``nu`` (novelupdates URL) is the
# strongest because it identifies the original work regardless of language.
SIGNAL_WEIGHTS = {
    "nu": 0.95,
    "phash": 0.75,
    "title": 0.60,
    "alt": 0.55,
    "author": 0.45,
    "text": 0.40,
}


def normalize_text(value):
    """Case/accent-fold, drop bracketed suffixes and punctuation."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    stripped = _PAREN_RE.sub(" ", stripped)
    stripped = _NON_WORD_RE.sub(" ", stripped.casefold())
    return " ".join(stripped.split())


def normalize_url(value):
    return (value or "").strip().rstrip("/").casefold()


def combo_certainty(signals):
    """Noisy-OR over the matched signals -> 0..1 certainty."""
    remaining = 1.0
    for kind, score in signals.items():
        weight = SIGNAL_WEIGHTS.get(kind, 0.0)
        remaining *= 1.0 - weight * max(0.0, min(1.0, score))
    return round(1.0 - remaining, 4)


class Command(BaseCommand):
    help = "Find probable duplicate novels and queue MergeCandidate rows."

    def add_arguments(self, parser):
        parser.add_argument("--auto-score", type=float, default=None,
                            help="certainty >= this auto-merges (default settings.MERGE_AUTO_SCORE).")
        parser.add_argument("--review-low", type=float, default=None,
                            help="certainty >= this is queued for review (default settings.MERGE_REVIEW_LOW).")
        parser.add_argument("--max-block-size", type=int, default=None,
                            help="Skip title/alt/author blocks larger than this.")
        parser.add_argument("--trigram-min", type=float, default=None,
                            help="Fuzzy title similarity floor; <0 disables the trigram pass.")
        parser.add_argument("--limit", type=int, default=0, help="Only consider N novels (0 = all).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        self.auto_score = options["auto_score"]
        if self.auto_score is None:
            self.auto_score = getattr(settings, "MERGE_AUTO_SCORE", 1.01)
        self.review_low = options["review_low"]
        if self.review_low is None:
            self.review_low = getattr(settings, "MERGE_REVIEW_LOW", 0.5)
        self.max_block_size = options["max_block_size"] or getattr(settings, "MERGE_MAX_BLOCK_SIZE", 50)
        self.placeholder_min = getattr(settings, "MERGE_PLACEHOLDER_MIN_NOVELS", 5)
        trigram_min = options["trigram_min"]
        if trigram_min is None:
            trigram_min = getattr(settings, "MERGE_TRIGRAM_MIN", 0.4)
        self.trigram_min = trigram_min
        self.dry_run = options["dry_run"]
        limit = options["limit"]

        data = self._load(limit)
        pair_signals = self._block_pairs(data)
        allowed = data["allowed"]
        if self.trigram_min >= 0:
            self._trigram_pairs(data, pair_signals, allowed)
        self._add_novel_similarity(pair_signals, allowed)

        stats = self._store(pair_signals)
        self.stdout.write(self.style.SUCCESS(
            "merge candidates: {candidates} pair(s), {review} review, {auto} auto, "
            "{merged} merged out of {novels} novel(s), {blocks} block key(s)".format(
                novels=len(data["titles"]), blocks=len(data["blocks"]), **stats
            )
        ))

    # ------------------------------------------------------------------ load
    def _load(self, limit):
        novel_ids = list(Novel.objects.values_list("id", flat=True))
        if limit:
            novel_ids = novel_ids[:limit]
        allowed = set(novel_ids)

        titles = defaultdict(set)
        alts = defaultdict(set)
        authors = defaultdict(set)
        nus = defaultdict(set)
        phashes = defaultdict(set)

        for novel_id, title in Novel.objects.filter(pk__in=allowed).values_list("id", "title"):
            if title:
                titles[novel_id].add(normalize_text(title))

        qs = NovelFromSource.objects.filter(novel_id__in=allowed).prefetch_related(
            "authors", "alternative_titles"
        )
        for src in qs.iterator(chunk_size=2000):
            nid = src.novel_id
            if src.title:
                titles[nid].add(normalize_text(src.title))
            if src.novelupdates_url:
                nus[nid].add(normalize_url(src.novelupdates_url))
            if src.cover_phash:
                phashes[nid].add(src.cover_phash)
            for author in src.authors.all():
                authors[nid].add(normalize_text(author.name))
            for alt in src.alternative_titles.all():
                alts[nid].add(normalize_text(alt.name))

        return {
            "titles": titles,
            "alts": alts,
            "authors": authors,
            "nus": nus,
            "phashes": phashes,
            "novel_title": dict(Novel.objects.filter(pk__in=allowed).values_list("id", "title")),
            "allowed": allowed,
            "blocks": defaultdict(set),
        }

    # ---------------------------------------------------------------- block
    def _block_pairs(self, data):
        blocks = data["blocks"]

        def add(kind, key, novel_id):
            if key:
                blocks[(kind, key)].add(novel_id)

        for nid, values in data["titles"].items():
            for key in values:
                add("title", key, nid)
        for nid, values in data["alts"].items():
            for key in values:
                add("alt", key, nid)
        for nid, values in data["authors"].items():
            for key in values:
                add("author", key, nid)
        for nid, values in data["nus"].items():
            for key in values:
                add("nu", key, nid)

        # A cover hash shared by too many novels is a site default placeholder,
        # not evidence of a duplicate -> drop it entirely.
        shared = defaultdict(set)
        for nid, values in data["phashes"].items():
            for key in values:
                shared[key].add(nid)
        self.placeholder_hashes = {
            key for key, ids in shared.items() if len(ids) >= self.placeholder_min
        }
        for nid, values in data["phashes"].items():
            for key in values:
                if key not in self.placeholder_hashes:
                    add("phash", key, nid)

        pair_signals = defaultdict(dict)
        for (kind, _key), ids in blocks.items():
            ids = list(ids)
            if kind in ("title", "alt", "author") and len(ids) > self.max_block_size:
                continue
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pair = self._order(ids[i], ids[j])
                    pair_signals[pair][kind] = 1.0
        return pair_signals

    def _trigram_pairs(self, data, pair_signals, allowed):
        for novel_id, title in data["novel_title"].items():
            if not title or len(title) < 4:
                continue
            # Match against UPPER(title) so the GIN trigram index on
            # Upper('title') can be used; filtering the raw column forces a
            # sequential scan per novel.
            upper = title.upper()
            qs = (
                Novel.objects.filter(pk__in=allowed)
                .annotate(upper_title=Upper("title"))
                .filter(upper_title__trigram_similar=upper)
                .exclude(pk=novel_id)
                .annotate(sim=TrigramSimilarity("upper_title", upper))
                .order_by("-sim")
                .values_list("id", "sim")[:20]
            )
            for other_id, sim in qs:
                if sim < self.trigram_min:
                    continue
                pair = self._order(novel_id, other_id)
                pair_signals[pair]["title"] = max(pair_signals[pair].get("title", 0.0), float(sim))

    def _add_novel_similarity(self, pair_signals, allowed):
        qs = NovelSimilarity.objects.filter(
            from_novel_id__in=allowed, to_novel_id__in=allowed
        ).values_list("from_novel_id", "to_novel_id", "similarity")
        for from_id, to_id, similarity in qs:
            if from_id == to_id:
                continue
            pair = self._order(from_id, to_id)
            pair_signals[pair]["text"] = max(
                pair_signals[pair].get("text", 0.0), float(similarity)
            )

    @staticmethod
    def _order(a, b):
        return (a, b) if str(a) <= str(b) else (b, a)

    # ---------------------------------------------------------------- store
    def _store(self, pair_signals):
        stats = {"candidates": 0, "review": 0, "auto": 0, "merged": 0}

        if not self.dry_run:
            # Drop candidates whose novel was merged away outside this command.
            MergeCandidate.objects.filter(status=MergeCandidate.STATUS_PENDING).filter(
                novel_a__isnull=True
            ).update(status=MergeCandidate.STATUS_SKIPPED)
            MergeCandidate.objects.filter(status=MergeCandidate.STATUS_PENDING).filter(
                novel_b__isnull=True
            ).update(status=MergeCandidate.STATUS_SKIPPED)

        terminal = {(str(a), str(b)) for a, b in MergeCandidate.objects.exclude(
            status=MergeCandidate.STATUS_PENDING
        ).values_list("novel_a_id", "novel_b_id")}

        involved = {nid for pair in pair_signals for nid in pair}
        novels = {n.pk: n for n in Novel.objects.filter(pk__in=involved)}

        auto_pairs = []
        for (a_id, b_id), signals in pair_signals.items():
            certainty = combo_certainty(signals)
            if certainty < self.review_low:
                continue
            if (str(a_id), str(b_id)) in terminal:
                continue
            decision = (
                MergeCandidate.DECISION_AUTO if certainty >= self.auto_score
                else MergeCandidate.DECISION_REVIEW
            )
            stats["candidates"] += 1
            stats["auto" if decision == MergeCandidate.DECISION_AUTO else "review"] += 1
            if decision == MergeCandidate.DECISION_AUTO:
                auto_pairs.append((a_id, b_id))
            if self.dry_run:
                continue
            self._upsert(novels.get(a_id), novels.get(b_id), certainty, signals, decision)

        if auto_pairs and not self.dry_run:
            stats["merged"] = self._auto_merge(auto_pairs)
        return stats

    def _upsert(self, novel_a, novel_b, certainty, signals, decision):
        if novel_a is None or novel_b is None:
            return
        existing = MergeCandidate.objects.filter(
            novel_a=novel_a, novel_b=novel_b
        ).first() or MergeCandidate.objects.filter(novel_a=novel_b, novel_b=novel_a).first()
        if existing is not None and existing.status != MergeCandidate.STATUS_PENDING:
            return
        if existing is not None:
            existing.certainty = certainty
            existing.signals = signals
            existing.decision = decision
            existing.save(update_fields=["certainty", "signals", "decision", "updated_at"])
            return
        MergeCandidate.objects.create(
            novel_a=novel_a,
            novel_b=novel_b,
            novel_a_id_snapshot=novel_a.pk,
            novel_b_id_snapshot=novel_b.pk,
            title_a=novel_a.title,
            title_b=novel_b.title,
            certainty=certainty,
            signals=signals,
            decision=decision,
        )

    def _auto_merge(self, auto_pairs):
        """Merge only isolated pairs; multi-hop clusters are demoted to review."""
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for a_id, b_id in auto_pairs:
            union(a_id, b_id)

        groups = defaultdict(set)
        for a_id, b_id in auto_pairs:
            groups[find(a_id)].update((a_id, b_id))

        from lncrawler_api.services.merge_service import MergeError, merge_novels

        def pick_survivor(x, y):
            cx, cy = x.sources.count(), y.sources.count()
            if cx != cy:
                return x if cx > cy else y
            return x if str(x.pk) <= str(y.pk) else y

        merged = 0
        for members in groups.values():
            if len(members) != 2:
                # Ambiguous chain -> leave for a human.
                MergeCandidate.objects.filter(
                    novel_a_id_snapshot__in=members, novel_b_id_snapshot__in=members
                ).update(decision=MergeCandidate.DECISION_REVIEW)
                continue
            a_id, b_id = members
            a = Novel.objects.filter(pk=a_id).first()
            b = Novel.objects.filter(pk=b_id).first()
            if a is None or b is None:
                continue
            target = pick_survivor(a, b)
            source = b if target.pk == a.pk else a
            try:
                with transaction.atomic():
                    merge_novels(source, target)
                    # Match on the snapshots: merge_novels deleted the source
                    # novel, so its live FK is now NULL and would never match.
                    MergeCandidate.objects.filter(
                        novel_a_id_snapshot__in=(a_id, b_id),
                        novel_b_id_snapshot__in=(a_id, b_id),
                    ).update(status=MergeCandidate.STATUS_MERGED)
            except MergeError as exc:
                self.stderr.write(f"Auto-merge {a_id}/{b_id} failed: {exc}")
                continue
            merged += 1
        return merged
