"""Chapter content comparison between a dead source and a keeper."""

from collections import Counter
from difflib import SequenceMatcher

from lncrawler_api.utils import chapter_utils

from .common import MIN_SAMPLE_WORDS, normalize_body, tokenize_body


class SimilarityMixin:
    @staticmethod
    def _sample_positions(total: int, samples: int):
        if total <= 0:
            return []
        if samples <= 1 or total == 1:
            return [0]
        if samples >= total:
            return list(range(total))
        return sorted({round(i * (total - 1) / (samples - 1)) for i in range(samples)})

    def _prefetch_bodies(self, cache, source, chapter_ids):
        """Read ``chapter_ids`` of ``source`` in one batch into ``cache`` as word tokens."""
        data = chapter_utils.read_chapters_no_extract(source.absolute_source_path, chapter_ids)
        for chapter_id in chapter_ids:
            chapter = data.get(chapter_id)
            cache[(source.pk, chapter_id)] = tokenize_body(
                normalize_body(chapter.get("body") if chapter else None)
            )

    def _read_body(self, cache, source, chapter_id) -> list:
        return cache.get((source.pk, chapter_id), [])

    def _dead_context(self, dead) -> dict:
        """Tokenize the dead source once: its sampled chapters that are real content."""
        dead_ids = list(dead.chapters.order_by("chapter_id").values_list("chapter_id", flat=True))
        base = self._sample_positions(len(dead_ids), self.samples)
        cache: dict = {}
        self._prefetch_bodies(cache, dead, [dead_ids[pos] for pos in base])
        samples = []
        for pos in base:
            tokens = self._read_body(cache, dead, dead_ids[pos])
            if len(tokens) >= MIN_SAMPLE_WORDS:
                samples.append((pos, tokens))
        return {"chapters": len(dead_ids), "base": base, "samples": samples}

    def _shift_order(self):
        """Alignments to try, nearest first: 0, +1, -1, +2, -2, ... up to ``max_shift``."""
        order = [0]
        for distance in range(1, self.max_shift + 1):
            order.extend((distance, -distance))
        return order

    def _content_similarity(self, dead_ctx, keeper):
        """Mean content match of a dead source's samples against one keeper.

        Each sample is aligned on its own, since keeper chapters can be inserted,
        dropped or prepended: sample ``pos`` is compared with keeper positions
        ``pos + shift`` for every shift in ``_shift_order()`` and keeps its best
        ratio, stopping early once that reaches ``self.threshold``. The result is
        the mean of those per-sample bests, so one bad sample is not hidden by
        the others and a single lucky pair cannot pass on its own.

        Returns ``(mean, shift, count)``. ``count`` is the number of valid
        samples (dead chapters with at least ``MIN_SAMPLE_WORDS`` words).
        Only samples whose best ratio reaches the threshold vote for ``shift``,
        and the winning shift needs a strict majority of those votes. Samples are
        not required to agree (chapters drift), but with no majority the result is
        ``(mean, 0, 0)``: the caller keeps the source. At least
        ``min(sampled, max(2, sampled // 2 + 1))`` samples must be valid, so a
        one-chapter source passes on its single sample, while six sampled
        positions need four valid ones; otherwise ``(0.0, 0, 0)``.

        Chapters are compared as word tokens with ``autojunk=False``: the
        character-level matcher scores identical translations too low. A
        ``quick_ratio`` upper bound skips a pair that cannot beat the sample's
        current best without the exact comparison.
        """
        samples = dead_ctx["samples"]
        sampled = len(dead_ctx["base"])
        min_pairs = min(sampled, max(2, sampled // 2 + 1))
        if not samples or len(samples) < min_pairs:
            return 0.0, 0, 0

        keeper_ids = list(keeper.chapters.order_by("chapter_id").values_list("chapter_id", flat=True))
        keeper_needed = sorted({
            keeper_ids[pos + shift]
            for pos, _ in samples
            for shift in self._shift_order()
            if 0 <= pos + shift < len(keeper_ids)
        })
        cache: dict = {}
        self._prefetch_bodies(cache, keeper, keeper_needed)

        bests, matched_shifts = [], []
        for pos, a in samples:
            best, best_shift = 0.0, None
            for shift in self._shift_order():
                kpos = pos + shift
                if not 0 <= kpos < len(keeper_ids):
                    continue
                b = self._read_body(cache, keeper, keeper_ids[kpos])
                if len(b) < MIN_SAMPLE_WORDS:
                    continue
                matcher = SequenceMatcher(None, a, b, autojunk=False)
                if matcher.real_quick_ratio() <= best or matcher.quick_ratio() <= best:
                    continue
                ratio = matcher.ratio()
                if ratio > best:
                    best, best_shift = ratio, shift
                if best >= self.threshold:
                    break
            bests.append(best)
            if best_shift is not None and best >= self.threshold:
                matched_shifts.append(best_shift)

        mean = sum(bests) / len(bests)
        if not matched_shifts:
            return mean, 0, 0
        # Only samples that matched vote, and the winner needs a strict majority of
        # them. Without one there is no consistent alignment, so the positional
        # user-data mapping would be unreliable: report count=0 so the caller keeps.
        votes = Counter(matched_shifts)
        top_shift, top_votes = min(votes.items(), key=lambda kv: (-kv[1], abs(kv[0]), kv[0]))
        if top_votes * 2 <= len(matched_shifts):
            return mean, 0, 0
        return mean, top_shift, len(samples)
