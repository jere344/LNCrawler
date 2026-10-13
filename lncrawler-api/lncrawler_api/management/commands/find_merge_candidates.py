"""Find probable duplicate novels across sources and queue them for review.

Cheap deterministic funnel:

1. Block — group novels by normalized title, alternative title, author,
   ``novelupdates_url``, source URL, folder on disk (``novel_path``) and cover
   dHash. Only novels sharing a block are ever compared, so this is not O(N^2).
2. Score — combine the per-signal matches into a single 0..1 ``certainty``
   (noisy-OR, so independent signals corroborate each other). Penalty signals
   (sequel mismatch) then scale it down, since titles are folded for blocking
   and lose the sequel number.
3. Store — write a ``MergeCandidate`` per pair. Nothing is merged unless
   ``certainty`` clears ``MERGE_AUTO_SCORE`` (default >1, so auto-merge is off
   until the threshold is tuned against real data); the rest wait for the admin
   review page.

Re-running is safe: pairs a human already rejected/merged are left untouched.
"""
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count
from django.utils import timezone

from lncrawler_api.models import MergeCandidate, Novel, NovelFromSource, NovelSimilarity
from lncrawler_api.utils.title_signals import normalize_text, sequel_number

# Per-signal weights fed into the noisy-OR. ``src`` (same source URL) and ``nu``
# (novelupdates URL) are the strongest: both identify the exact same work, the
# former because a source URL maps to exactly one story. ``path`` is the same
# folder on disk, which the crawler only produces for one novel.
SIGNAL_WEIGHTS = {
    "src": 0.99,
    "path": 0.99,
    "nu": 0.95,
    "phash": 0.75,
    "title": 0.60,
    "alt": 0.55,
    "author": 0.45,
    "text": 0.40,
    # Only meaningful next to an author or cover match: matching lengths alone
    # say nothing about identity.
    "chapters": 0.30,
}

# Penalties scale the certainty down instead of adding to it. They read the raw
# (unfolded) titles, which the title block ignores on purpose.
PENALTY_WEIGHTS = {
    "sequel_mismatch": 0.7,
}

# A chapter count this low is too noisy to say two novels have the same length.
CHAPTER_MATCH_MIN = 10
CHAPTER_MATCH_RATIO = 0.9


def normalize_url(value):
    return (value or "").strip().rstrip("/").casefold()


def combo_certainty(signals):
    """Noisy-OR over the matched signals, then penalties -> 0..1 certainty.

    Penalties are skipped when the pair shares a definitive identity signal
    (``src`` or ``path``): the same source URL or the same folder is the same
    novel even when one raw title carries a different sequel number.
    """
    remaining = 1.0
    for kind, score in signals.items():
        weight = SIGNAL_WEIGHTS.get(kind, 0.0)
        remaining *= 1.0 - weight * max(0.0, min(1.0, score))
    certainty = 1.0 - remaining

    if "src" not in signals and "path" not in signals:
        for kind, score in signals.items():
            weight = PENALTY_WEIGHTS.get(kind, 0.0)
            certainty *= 1.0 - weight * max(0.0, min(1.0, score))
    return round(certainty, 4)


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
        self._add_discriminants(pair_signals, data)

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
        # Raw (unfolded) titles keep the sequel numbers that the folded ones
        # drop; they feed the sequel penalty only.
        raw_titles = defaultdict(set)
        alts = defaultdict(set)
        authors = defaultdict(set)
        nus = defaultdict(set)
        urls = defaultdict(set)
        phashes = defaultdict(set)
        paths = {}

        for novel_id, title, novel_path in Novel.objects.filter(pk__in=allowed).values_list(
            "id", "title", "novel_path"
        ):
            if title:
                titles[novel_id].add(normalize_text(title))
                raw_titles[novel_id].add(title)
            if novel_path and novel_path.strip():
                paths[novel_id] = novel_path.strip()

        qs = NovelFromSource.objects.filter(novel_id__in=allowed).prefetch_related(
            "authors", "alternative_titles"
        )
        for src in qs.iterator(chunk_size=2000):
            nid = src.novel_id
            if src.title:
                titles[nid].add(normalize_text(src.title))
                raw_titles[nid].add(src.title)
            if src.novelupdates_url:
                nus[nid].add(normalize_url(src.novelupdates_url))
            if src.source_url:
                urls[nid].add(normalize_url(src.source_url))
            if src.cover_phash:
                phashes[nid].add(src.cover_phash)
            for author in src.authors.all():
                authors[nid].add(normalize_text(author.name))
            for alt in src.alternative_titles.all():
                alts[nid].add(normalize_text(alt.name))

        # One aggregate for every novel instead of a COUNT per novel. A novel's
        # length is its longest source: the others are often partial copies.
        chapters = defaultdict(int)
        totals = NovelFromSource.objects.filter(novel_id__in=allowed).annotate(
            chapter_total=Count("chapters")
        ).values_list("novel_id", "chapter_total")
        for novel_id, total in totals:
            chapters[novel_id] = max(chapters[novel_id], total)

        return {
            "titles": titles,
            "raw_titles": raw_titles,
            "alts": alts,
            "authors": authors,
            "nus": nus,
            "urls": urls,
            "phashes": phashes,
            "paths": paths,
            "chapters": chapters,
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
        for nid, values in data["urls"].items():
            for key in values:
                add("src", key, nid)
        for nid, path in data["paths"].items():
            add("path", path, nid)

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
        # One set-based query instead of a round trip per novel. For each novel
        # the lateral subquery keeps the 20 closest titles among those matching
        # under the trigram operator. The operator runs on UPPER(title) so the
        # GIN trigram index on Upper('title') is usable; the raw column would
        # force a sequential scan per novel.
        if not allowed:
            return
        table = connection.ops.quote_name(Novel._meta.db_table)
        pk = connection.ops.quote_name(Novel._meta.pk.column)
        title = connection.ops.quote_name(Novel._meta.get_field("title").column)
        sql = f"""
            SELECT a.{pk}, near.other_id, near.sim
            FROM {table} AS a
            CROSS JOIN LATERAL (
                SELECT b.{pk} AS other_id,
                       similarity(UPPER(b.{title}), UPPER(a.{title})) AS sim
                FROM {table} AS b
                WHERE b.{pk} = ANY(%s::uuid[])
                  AND b.{pk} <> a.{pk}
                  AND UPPER(b.{title}) %% UPPER(a.{title})
                ORDER BY sim DESC
                LIMIT 20
            ) AS near
            WHERE a.{pk} = ANY(%s::uuid[])
              AND LENGTH(a.{title}) >= 4
              AND near.sim >= %s
        """
        ids = [str(novel_id) for novel_id in allowed]
        with connection.cursor() as cursor:
            cursor.execute(sql, [ids, ids, self.trigram_min])
            rows = cursor.fetchall()
        for novel_id, other_id, sim in rows:
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

    def _add_discriminants(self, pair_signals, data):
        """Add the chapter-length match and the penalty signals to every pair.

        Penalties are written into ``signals`` rather than only applied, so the
        reviewer can see why a pair was pushed down.
        """
        sequels = {
            nid: {sequel_number(t) or 1 for t in titles}
            for nid, titles in data["raw_titles"].items()
        }
        chapters = data["chapters"]

        for (a_id, b_id), signals in pair_signals.items():
            if "author" in signals or "phash" in signals:
                low, high = sorted((chapters.get(a_id, 0), chapters.get(b_id, 0)))
                if low >= CHAPTER_MATCH_MIN and low >= CHAPTER_MATCH_RATIO * high:
                    signals["chapters"] = 1.0

            # A title without a number counts as sequel 1 (see ``sequel_number``
            # and the ``or 1`` above), so "Foo" against "Foo 2" is a mismatch on
            # purpose. A mismatch is penalised only when the two sides share no
            # sequel number at all.
            sequel_a, sequel_b = sequels.get(a_id, set()), sequels.get(b_id, set())
            if sequel_a and sequel_b and not (sequel_a & sequel_b):
                signals["sequel_mismatch"] = 1.0

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

        # One preload keyed by the unordered pair replaces a lookup per pair.
        # Rows whose FK was SET_NULL by a merge are not live pairs.
        existing = {
            self._order(row.novel_a_id, row.novel_b_id): row
            for row in MergeCandidate.objects.filter(novel_a__isnull=False, novel_b__isnull=False)
        }

        involved = {nid for pair in pair_signals for nid in pair}
        novels = {n.pk: n for n in Novel.objects.filter(pk__in=involved)}

        auto_pairs = []
        to_create = []
        to_update = []
        now = timezone.now()
        for (a_id, b_id), signals in pair_signals.items():
            certainty = combo_certainty(signals)
            if certainty < self.review_low:
                continue
            row = existing.get((a_id, b_id))
            # A pair a human (or the LLM dismissal) already settled stays as is.
            if row is not None and row.status != MergeCandidate.STATUS_PENDING:
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
            if row is not None:
                row.certainty = certainty
                row.signals = signals
                row.decision = decision
                row.updated_at = now
                to_update.append(row)
                continue
            novel_a, novel_b = novels.get(a_id), novels.get(b_id)
            if novel_a is None or novel_b is None:
                continue
            to_create.append(MergeCandidate(
                novel_a=novel_a,
                novel_b=novel_b,
                novel_a_id_snapshot=novel_a.pk,
                novel_b_id_snapshot=novel_b.pk,
                title_a=novel_a.title,
                title_b=novel_b.title,
                certainty=certainty,
                signals=signals,
                decision=decision,
            ))

        if to_create:
            MergeCandidate.objects.bulk_create(to_create)
        if to_update:
            MergeCandidate.objects.bulk_update(
                to_update, ["certainty", "signals", "decision", "updated_at"]
            )

        if auto_pairs and not self.dry_run:
            stats["merged"] = self._auto_merge(auto_pairs)
        return stats

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

        from lncrawler_api.services.merge_service import (
            MergeError,
            merge_novels,
            pick_merge_survivor,
        )

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
            target = pick_merge_survivor(a, b)
            source = b if target.pk == a.pk else a
            # merge_novels is atomic and moves files immediately (with its own
            # undo journal), so no outer transaction here: a rollback of ours
            # would leave the moved files behind.
            try:
                merge_novels(source, target)
            except MergeError as exc:
                self.stderr.write(f"Auto-merge {a_id}/{b_id} failed: {exc}")
                continue
            # Match on the snapshots: merge_novels deleted the source novel, so
            # its live FK is now NULL and would never match.
            MergeCandidate.objects.filter(
                novel_a_id_snapshot__in=(a_id, b_id),
                novel_b_id_snapshot__in=(a_id, b_id),
            ).update(status=MergeCandidate.STATUS_MERGED)
            merged += 1
        return merged
