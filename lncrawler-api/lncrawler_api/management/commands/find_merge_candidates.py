"""Find probable duplicate novels across sources and queue them for review.

Cheap deterministic funnel:

1. Block — group novels by normalized title, alternative title, author,
   ``novelupdates_url``, source URL, folder on disk (``novel_path``) and cover
   dHash (exact or within a few bits). Only novels sharing a block are ever
   compared, so this is not O(N^2).
2. Score — combine the per-signal matches into a single 0..1 ``certainty``
   (noisy-OR, so independent signals corroborate each other). Penalty signals
   (sequel mismatch) then scale it down, since titles are folded for blocking
   and lose the sequel number.
3. Store — write a ``novel_merge`` Candidate per pair. Nothing is merged here: the
   LLM judge merges the pairs it is sure about, the rest wait for the admin
   review page.

Re-running is safe: pairs a human already decided are left untouched, pairs blocked
by a rejected or undone candidate (``candidate_blocks``) are never proposed again.
"""
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from lncrawler_api.models import Candidate, Novel, NovelFromSource, NovelSimilarity
from lncrawler_api.services.candidate_blocks import blocked_pairs, pair_key
from lncrawler_api.services.merge_common import ordered_pair, sorted_pk_signature
from lncrawler_api.utils.title_signals import normalize_text, sequel_number

# Per-signal weights fed into the noisy-OR. ``src`` (same source URL) and ``nu``
# (novelupdates URL) are the strongest: both identify the exact same work, the
# former because a source URL maps to exactly one story. ``path`` is the same
# folder on disk, which the crawler only produces for one novel.
SIGNAL_WEIGHTS = {
    "src": 0.99,
    "path": 0.99,
    "nu": 0.95,
    # Same weight as an author: sites reuse covers and placeholder detection cannot
    # catch every default image, so a cover match alone must stay below review_low.
    "phash": 0.45,
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

# A dHash with this few bits set (or unset) comes from a near-flat cover (blank,
# solid colour, plain text): it says nothing about which novel it is, so such a
# hash is a placeholder and never matches, not even exactly.
PHASH_MIN_BITS = 12


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
    help = "Find probable duplicate novels and queue novel_merge candidates."

    def add_arguments(self, parser):
        parser.add_argument("--review-low", type=float, default=None,
                            help="certainty >= this is queued for review (default settings.MERGE_REVIEW_LOW).")
        parser.add_argument("--max-block-size", type=int, default=None,
                            help="Skip title/alt/author blocks larger than this.")
        parser.add_argument("--trigram-min", type=float, default=None,
                            help="Fuzzy title similarity floor; <0 disables the trigram pass.")
        parser.add_argument("--limit", type=int, default=0, help="Only consider N novels (0 = all).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        self.review_low = options["review_low"]
        if self.review_low is None:
            self.review_low = settings.MERGE_REVIEW_LOW
        self.max_block_size = options["max_block_size"] or settings.MERGE_MAX_BLOCK_SIZE
        self.placeholder_min = settings.MERGE_PLACEHOLDER_MIN_NOVELS
        self.phash_max_distance = settings.MERGE_PHASH_MAX_DISTANCE
        trigram_min = options["trigram_min"]
        if trigram_min is None:
            trigram_min = settings.MERGE_TRIGRAM_MIN
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

        stats = self._store(pair_signals, allowed)
        self.stdout.write(self.style.SUCCESS(
            "merge candidates: {candidates} pair(s), "
            "{blocked} blocked, {stale} stale removed, {gone} open row(s) of missing novels removed, "
            "out of {novels} novel(s), {blocks} block key(s)".format(
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

        pair_signals = defaultdict(dict)
        for (kind, _key), ids in blocks.items():
            ids = list(ids)
            if kind in ("title", "alt", "author") and len(ids) > self.max_block_size:
                continue
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pair = ordered_pair(ids[i], ids[j])
                    pair_signals[pair][kind] = 1.0
        self._phash_pairs(data, pair_signals)
        return pair_signals

    def _phash_pairs(self, data, pair_signals):
        # Cover dHashes are compared by Hamming distance, so a re-encoded or
        # resized copy of the same cover still matches.
        hash_novels = defaultdict(set)
        for nid, values in data["phashes"].items():
            for key in values:
                try:
                    hash_novels[int(key, 16)].add(nid)
                except ValueError:
                    continue

        # 8 bands of 8 bits: two hashes up to 7 bits apart leave at least one
        # band untouched (pigeonhole), so they share a bucket and every pair
        # within the max distance (capped at 7) is found.
        buckets = defaultdict(set)
        for value in hash_novels:
            if not PHASH_MIN_BITS <= value.bit_count() <= 64 - PHASH_MIN_BITS:
                continue
            for i in range(8):
                buckets[(i, (value >> (8 * i)) & 0xFF)].add(value)

        # A pair sharing several bands is compared once per band: cheaper than
        # remembering every compared pair.
        near = defaultdict(dict)
        for members in buckets.values():
            members = list(members)
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    distance = (a ^ b).bit_count()
                    if distance <= self.phash_max_distance:
                        near[a][b] = distance
                        near[b][a] = distance

        # A site's default cover re-encoded slightly is still a placeholder, so
        # the count covers the exact hash and every hash within the max distance.
        self.placeholder_hashes = set()
        for value, ids in hash_novels.items():
            around = set(ids)
            for other in near.get(value, {}):
                around |= hash_novels[other]
            if len(around) >= self.placeholder_min:
                self.placeholder_hashes.add(value)
            # Near-flat covers are placeholders outright, even when they are unique.
            if not PHASH_MIN_BITS <= value.bit_count() <= 64 - PHASH_MIN_BITS:
                self.placeholder_hashes.add(value)

        def add_phash(a_id, b_id, score):
            if a_id == b_id:
                return
            pair = ordered_pair(a_id, b_id)
            pair_signals[pair]["phash"] = max(pair_signals[pair].get("phash", 0.0), score)

        for value, ids in hash_novels.items():
            if value in self.placeholder_hashes:
                continue
            ids = list(ids)
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    add_phash(ids[i], ids[j], 1.0)
            # Blocks are kept for the stdout count only; pairs come from above.
            for nid in ids:
                data["blocks"][("phash", format(value, "016x"))].add(nid)

        # A near cover is weighted by its distance, then by the phash weight. Even
        # an exact cover stays below review_low on its own, so it needs a
        # corroborating signal such as title or author.
        for value, others in near.items():
            for other, distance in others.items():
                if value >= other or value in self.placeholder_hashes or other in self.placeholder_hashes:
                    continue
                score = 1.0 - distance / 16
                for a_id in hash_novels[value]:
                    for b_id in hash_novels[other]:
                        add_phash(a_id, b_id, score)

    def _trigram_pairs(self, data, pair_signals, allowed):
        # Titles are already normalized in Python (brackets, punctuation and case
        # dropped), so they go into a temp table with its own trigram index rather
        # than the raw Novel.title one. Every source and alternative title is
        # compared. For each row the lateral subquery keeps the 20 closest titles
        # under the trigram operator, so generic titles stay bounded.
        rows = sorted({
            (str(novel_id), title, kind)
            for kind, source in (("title", data["titles"]), ("alt", data["alts"]))
            for novel_id, titles in source.items()
            if novel_id in allowed
            for title in titles
            if len(title) >= 4
        })
        if not rows:
            return
        with transaction.atomic(), connection.cursor() as cursor:
            # SET cannot take bind parameters, so set_config is used. is_local
            # scopes it to this transaction: the % operator then prunes at our
            # floor through the index instead of pg_trgm's 0.3 default, and the
            # setting does not leak into the session.
            cursor.execute(
                "SELECT set_config('pg_trgm.similarity_threshold', %s, true)",
                [str(self.trigram_min)],
            )
            # Dropped first so a second run inside the same transaction (tests)
            # does not fail on the existing temp table.
            cursor.execute("DROP TABLE IF EXISTS pg_temp.merge_titles")
            cursor.execute(
                "CREATE TEMP TABLE merge_titles "
                "(novel_id uuid NOT NULL, title text NOT NULL, kind text NOT NULL) "
                "ON COMMIT DROP"
            )
            cursor.execute(
                "INSERT INTO merge_titles "
                "SELECT * FROM unnest(%s::uuid[], %s::text[], %s::text[])",
                [[r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]],
            )
            cursor.execute("CREATE INDEX ON merge_titles USING gin (title gin_trgm_ops)")
            cursor.execute("ANALYZE merge_titles")
            cursor.execute(
                """
                SELECT a.novel_id, near.novel_id, a.kind, near.kind, near.sim
                FROM merge_titles AS a
                CROSS JOIN LATERAL (
                    SELECT b.novel_id, b.kind, similarity(b.title, a.title) AS sim
                    FROM merge_titles AS b
                    WHERE b.novel_id <> a.novel_id
                      AND b.title %% a.title
                    ORDER BY sim DESC
                    LIMIT 20
                ) AS near
                WHERE near.sim >= %s
                """,
                [self.trigram_min],
            )
            found = cursor.fetchall()
        for novel_id, other_id, kind, other_kind, sim in found:
            # A source title matching another novel's alternative title is evidence
            # the exact blocks never see (they only match title to title and alt to
            # alt). Alt-involved matches keep the lower alt weight.
            signal = "title" if kind == other_kind == "title" else "alt"
            pair = ordered_pair(novel_id, other_id)
            pair_signals[pair][signal] = max(pair_signals[pair].get(signal, 0.0), float(sim))

    def _add_novel_similarity(self, pair_signals, allowed):
        qs = NovelSimilarity.objects.filter(
            from_novel_id__in=allowed, to_novel_id__in=allowed
        ).values_list("from_novel_id", "to_novel_id", "similarity")
        for from_id, to_id, similarity in qs:
            if from_id == to_id:
                continue
            pair = ordered_pair(from_id, to_id)
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

    # ---------------------------------------------------------------- store
    def _store(self, pair_signals, allowed):
        stats = {"candidates": 0, "stale": 0, "blocked": 0, "gone": 0}
        blocked = blocked_pairs(Candidate.KIND_NOVEL_MERGE)

        # An open row naming a novel that no longer exists can never be judged or applied:
        # the merge or delete that removed the novel should have deleted it already.
        known = {str(pk) for pk in Novel.objects.values_list("pk", flat=True)}
        rows = list(Candidate.objects.filter(kind=Candidate.KIND_NOVEL_MERGE))
        gone = [
            row for row in rows
            if row.status in Candidate.OPEN_STATUSES
            and row.claimed_at is None  # in flight: the runner drops it when it finds the novel gone
            and any(str(pk) not in known for pk in row.target_ids)
        ]
        stats["gone"] = len(gone)
        if gone and not self.dry_run:
            Candidate.objects.filter(pk__in=[row.pk for row in gone]).delete()
        gone_pks = {row.pk for row in gone}
        # One preload keyed by signature replaces a lookup per pair.
        existing = {row.signature: row for row in rows if row.pk not in gone_pks}

        involved = {nid for pair in pair_signals for nid in pair}
        novels = {n.pk: n for n in Novel.objects.filter(pk__in=involved)}

        to_create = []
        to_update = []
        kept = set()
        now = timezone.now()
        for (a_id, b_id), signals in pair_signals.items():
            certainty = combo_certainty(signals)
            if certainty < self.review_low:
                continue
            key = pair_key(a_id, b_id)
            kept.add(key)
            if key in blocked:
                stats["blocked"] += 1
                continue
            signature = sorted_pk_signature([str(a_id), str(b_id)])
            row = existing.get(signature)
            # A pair a human or the LLM already decided stays as it is.
            if row is not None and row.status not in Candidate.OPEN_STATUSES:
                continue
            stats["candidates"] += 1
            if self.dry_run:
                continue
            novel_a, novel_b = novels.get(a_id), novels.get(b_id)
            if novel_a is None or novel_b is None:
                continue
            names = [novel_a.title, novel_b.title]
            if row is not None:
                row.certainty = certainty
                row.signals = signals
                row.target_names = names
                row.updated_at = now
                to_update.append(row)
                continue
            to_create.append(Candidate(
                kind=Candidate.KIND_NOVEL_MERGE,
                signature=signature,
                target_ids=[str(a_id), str(b_id)],
                target_names=names,
                certainty=certainty,
                signals=signals,
            ))

        # Undecided rows the machine queued go stale once their pair no longer reaches
        # review_low. Only pairs this run looked at (both novels in ``allowed``) are judged,
        # so a --limit run leaves the rest alone. Claimed rows are left to the runner.
        # A pair that comes back is re-created and re-judged by the LLM.
        allowed_str = {str(pk) for pk in allowed}
        stale = [
            row.pk for row in existing.values()
            if row.status in (Candidate.STATUS_PENDING, Candidate.STATUS_REVIEW)
            and not row.decided_by
            and row.claimed_at is None
            and len(row.target_ids) == 2
            and all(pk in allowed_str for pk in pair_key(*row.target_ids))
            and pair_key(*row.target_ids) not in kept
        ]
        stats["stale"] = len(stale)
        if stale and not self.dry_run:
            Candidate.objects.filter(pk__in=stale).delete()

        if to_create:
            Candidate.objects.bulk_create(to_create)
        if to_update:
            Candidate.objects.bulk_update(
                to_update, ["certainty", "signals", "target_names", "updated_at"]
            )

        return stats
