"""Progressively clean the library.

Three phases, run in order, each bounded by ``--limit`` deletions per run so
the first pass over a large catalogue can be spread over many invocations:

1. orphan novels (no NovelFromSource left)
2. empty sources (no chapter, or no chapter with content)
3. dead-source duplicates (source no longer handled by the crawler but a
   better, live counterpart exists on a sibling or similar novel)

Deleting is destructive, so ``--apply`` is required; the default is a dry run.
Source folders are moved to ``<LNCRAWL_OUTPUT_PATH>/.prune_trash`` instead of
being removed in place, and every real deletion is appended to ``audit.jsonl``
there. Neither the DB nor the files are ever modified by a dry run.
"""

import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from lncrawler_api.models import (
    Comment,
    ExternalSource,
    Novel,
    NovelFromSource,
    NovelSimilarity,
    ReadingHistory,
)
from lncrawler_api.utils import chapter_utils
from lncrawler_api.utils.lncrawler_paths import sanitize

logger = logging.getLogger("lncrawler_api")

FAIL_MESSAGE = "Failed to download chapter body"

# A novel is never pruned before it has had time to settle, so a fresh crawl
# (or a bad first import) cannot be wiped before it is even reviewed.
MIN_NOVEL_AGE = timedelta(days=7)


def normalize_source_name(name: str) -> str:
    """Same normalization for registry names and DB source names."""
    if not name:
        return ""
    normalized = sanitize(str(name)).lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def normalize_title(title: str) -> str:
    return "".join(ch for ch in (title or "").lower() if ch.isalnum())


def normalize_body(body) -> str:
    if not body:
        return ""
    text = re.sub(r"(?is)<[^>]+>", " ", str(body))
    text = text.replace(FAIL_MESSAGE, "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


class Command(BaseCommand):
    help = "Progressively prune orphan novels, empty sources and dead-source duplicates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete. Without it the command only reports (dry run).",
        )
        parser.add_argument(
            "--limit", type=int, default=200,
            help="Max deletions per run across all phases (0 = unlimited).",
        )
        parser.add_argument(
            "--threshold", type=float, default=0.90,
            help="Min mean chapter-content similarity to treat a dead source as a duplicate.",
        )
        parser.add_argument(
            "--meta-threshold", type=float, default=0.60,
            help="Min NovelSimilarity score to consider a cross-novel keeper.",
        )
        parser.add_argument(
            "--samples", type=int, default=6,
            help="Chapters to sample per source for content similarity.",
        )
        parser.add_argument(
            "--max-shift", type=int, default=5,
            help=(
                "Search +/- this many chapters for the best alignment, so a "
                "source that prepends an intro/synopsis chapter still matches."
            ),
        )
        parser.add_argument(
            "--min-chapters", type=int, default=0,
            help="Ignore dead sources with fewer chapters than this in phase 3.",
        )
        parser.add_argument(
            "--sleep", type=float, default=0.2,
            help="Seconds to sleep between deletions.",
        )
        parser.add_argument(
            "--max-scan", type=int, default=5000,
            help="Max dead sources phase 3 examines per run (0 = unlimited).",
        )
        parser.add_argument(
            "--include-compressed", action="store_true",
            help="Also examine compressed sources (extracts json.7z as a side effect).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Delete even when attached user data exists.",
        )
        parser.add_argument(
            "--source", type=str, default=None,
            help="Limit phase 3 to this ExternalSource name (normalized).",
        )

    # -- run ----------------------------------------------------------- #

    def handle(self, *args, **options):
        self.apply = options["apply"]
        self.limit = options["limit"]
        self.threshold = options["threshold"]
        self.meta_threshold = options["meta_threshold"]
        self.samples = options["samples"]
        self.max_shift = max(0, options["max_shift"])
        self.min_chapters = options["min_chapters"]
        self.sleep = options["sleep"]
        self.max_scan = options["max_scan"]
        self.include_compressed = options["include_compressed"]
        self.force = options["force"]
        self.source_filter = options["source"]

        self.root = settings.LNCRAWL_OUTPUT_PATH
        self.trash_root = os.path.join(self.root, ".prune_trash")
        self.age_cutoff = timezone.now() - MIN_NOVEL_AGE
        self.deleted = 0
        self.kept_phase3 = 0

        mode = "APPLY" if self.apply else "DRY-RUN"
        self.stdout.write(self.style.WARNING(
            f"prune_library ({mode}) limit={self.limit or 'unlimited'} "
            f"threshold={self.threshold} max-scan={self.max_scan}"
        ))

        self._phase_orphan_novels()
        self._phase_empty_sources()
        self._phase_dead_duplicates()

        self.stdout.write(self.style.SUCCESS(
            f"prune_library: {self.deleted} deletion(s) "
            f"({'applied' if self.apply else 'would happen'}), "
            f"{self.kept_phase3} dead source(s) kept"
        ))
        if self.limit and self.deleted >= self.limit:
            self.stdout.write(self.style.WARNING("--limit reached; run again for the next batch."))

    # -- bounded run helpers ------------------------------------------- #

    def _stopped(self) -> bool:
        return bool(self.limit) and self.deleted >= self.limit

    # -- user data guards ---------------------------------------------- #

    def _novel_has_user_data(self, novel) -> bool:
        try:
            if novel.comments.exists():
                return True
            if novel.bookmarked_by_users.exists():
                return True
            if novel.ratings.exists():
                return True
            if novel.reading_histories.exists():
                return True
            if novel.in_reading_lists.exists():
                return True
            # OneToOne reverse raises DoesNotExist, not AttributeError.
            if getattr(novel, "featured", None):
                return True
        except Exception:
            # A missing reverse relation must never crash the prune run.
            return True
        return False

    @staticmethod
    def _source_has_user_data(source) -> bool:
        if Comment.objects.filter(chapter__novel_from_source=source).exists():
            return True
        if ReadingHistory.objects.filter(source=source).exists():
            return True
        return False

    # -- file handling -------------------------------------------------- #

    def _trash_source_folder(self, source):
        """Move the source folder aside and null the path so delete() won't rmtree it."""
        rel = source.source_path
        if not rel:
            return None
        abs_src = os.path.join(self.root, rel)
        if not os.path.isdir(abs_src):
            source.source_path = None
            source.save(update_fields=["source_path"])
            return None

        dest = os.path.join(self.trash_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = os.path.join(self.trash_root, f"{stamp}_{rel}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(abs_src, dest)
        source.source_path = None
        source.save(update_fields=["source_path"])
        return dest

    def _audit(self, entry):
        os.makedirs(self.trash_root, exist_ok=True)
        entry = {"ts": datetime.now().isoformat(), **entry}
        with open(os.path.join(self.trash_root, "audit.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    # -- phase 1: orphan novels ---------------------------------------- #

    def _phase_orphan_novels(self):
        self.stdout.write("Phase 1: orphan novels")
        orphans = Novel.objects.annotate(_n=Count("sources")).filter(
            _n=0, created_at__lt=self.age_cutoff
        )
        for novel in orphans.iterator():
            if self._stopped():
                return
            if not self.force and self._novel_has_user_data(novel):
                self.stdout.write(f"  SKIP novel {novel.id} {novel.title!r}: has user data")
                continue
            if not self.apply:
                self.stdout.write(f"  [DRY-RUN] would delete novel {novel.id} {novel.title!r}")
            else:
                try:
                    with transaction.atomic():
                        nid, ntitle = novel.id, novel.title
                        novel.delete()
                        self._audit({"kind": "novel", "id": nid, "title": ntitle, "reason": "orphan"})
                    self.stdout.write(self.style.SUCCESS(f"  deleted novel {nid} {ntitle!r}"))
                except Exception as exc:
                    logger.error("prune_library: failed deleting novel %s: %s", novel.id, exc)
                    continue
            self.deleted += 1
            self._maybe_sleep()

    # -- phase 2: empty sources ---------------------------------------- #

    def _phase_empty_sources(self):
        self.stdout.write("Phase 2: empty sources")
        with_content = NovelFromSource.objects.filter(chapters__has_content=True).values("pk")
        empties = (
            NovelFromSource.objects.exclude(pk__in=with_content)
            .filter(novel__created_at__lt=self.age_cutoff)
            .select_related("novel", "external_source")
        )
        for source in empties.iterator():
            if self._stopped():
                return
            if not self.force and self._source_has_user_data(source):
                self.stdout.write(
                    f"  SKIP source {source.id} {source.title!r}: has user data"
                )
                continue
            self._delete_source_named(source, "empty source")

    # -- phase 3: dead-source duplicates ------------------------------- #

    def _load_handled_sources(self):
        handled = set()
        try:
            crawler_dir = Path(settings.BASE_DIR).parent / "lncrawler-crawler"
            if str(crawler_dir) not in sys.path:
                sys.path.insert(0, str(crawler_dir))
            from lncrawl.core.sources import crawler_list, load_sources

            load_sources()
            for cls in crawler_list:
                name = getattr(cls, "source_name", "") or ""
                if name:
                    handled.add(normalize_source_name(name))
                base_urls = getattr(cls, "base_url", []) or []
                if isinstance(base_urls, str):
                    base_urls = [base_urls]
                for url in base_urls:
                    host = urlparse(str(url)).netloc
                    if host:
                        handled.add(normalize_source_name(host))
        except Exception as exc:
            logger.warning("prune_library: could not load crawler registry: %s", exc)
            return set()
        return {name for name in handled if name}

    def _phase_dead_duplicates(self):
        self.stdout.write("Phase 3: dead-source duplicates")
        handled = self._load_handled_sources()
        if not handled:
            self.stdout.write(self.style.WARNING(
                "  SKIP phase 3: handled source set is empty (registry failed to load)"
            ))
            return

        ext_names = {
            ext.id: normalize_source_name(ext.source_name)
            for ext in ExternalSource.objects.all()
        }
        filter_name = normalize_source_name(self.source_filter) if self.source_filter else None

        dead_ids = [
            pk for pk, name in ext_names.items()
            if name and name not in handled and (filter_name is None or name == filter_name)
        ]
        if not dead_ids:
            self.stdout.write("  no dead sources to examine")
            return

        dead_qs = (
            NovelFromSource.objects.filter(external_source_id__in=dead_ids)
            .filter(novel__created_at__lt=self.age_cutoff)
            .select_related("novel", "external_source")
            .order_by("id")
        )
        if self.max_scan and self.max_scan > 0:
            dead_qs = dead_qs[: self.max_scan]

        examined = 0
        for dead in dead_qs:
            if self._stopped():
                return
            examined += 1
            self._consider_dead_source(dead, handled, ext_names)
        self.stdout.write(f"  examined {examined} dead source(s)")

    def _is_live(self, source, handled, ext_names) -> bool:
        name = ext_names.get(source.external_source_id)
        if name is None:
            name = normalize_source_name(source.external_source.source_name)
        return name in handled

    def _find_keepers(self, dead, handled, ext_names):
        count = dead.chapters_count
        keepers = []

        for sibling in dead.novel.sources.exclude(pk=dead.pk):
            if self._is_live(sibling, handled, ext_names) and sibling.chapters_count > count:
                keepers.append((sibling, False))

        links = NovelSimilarity.objects.filter(
            Q(from_novel=dead.novel) | Q(to_novel=dead.novel),
            similarity__gte=self.meta_threshold,
        ).select_related("from_novel", "to_novel")
        for link in links:
            other = link.to_novel if link.from_novel_id == dead.novel_id else link.from_novel
            for source in other.sources.all():
                if self._is_live(source, handled, ext_names) and source.chapters_count > count:
                    keepers.append((source, True))

        seen = set()
        unique = []
        for source, cross in keepers:
            if source.pk in seen:
                continue
            seen.add(source.pk)
            unique.append((source, cross))
        return unique

    def _same_story(self, dead, keeper) -> bool:
        dead_title = normalize_title(dead.title)
        if dead_title and dead_title in (
            normalize_title(keeper.title),
            normalize_title(keeper.novel.title),
        ):
            return True
        dead_authors = {a.name.strip().lower() for a in dead.authors.all() if a.name}
        keeper_authors = {a.name.strip().lower() for a in keeper.authors.all() if a.name}
        return bool(dead_authors & keeper_authors)

    def _is_compressed(self, source) -> bool:
        base = source.absolute_source_path
        if not base:
            return False
        return (
            not os.path.isdir(os.path.join(base, "json"))
            and os.path.isfile(os.path.join(base, "json.7z"))
        )

    @staticmethod
    def _sample_positions(total: int, samples: int):
        if total <= 0:
            return []
        if samples <= 1 or total == 1:
            return [0]
        if samples >= total:
            return list(range(total))
        return sorted({round(i * (total - 1) / (samples - 1)) for i in range(samples)})

    def _read_body(self, cache, source, chapter_id) -> str:
        key = (source.pk, chapter_id)
        if key not in cache:
            data = chapter_utils.get_chapter(source.absolute_source_path, chapter_id)
            cache[key] = normalize_body(data.get("body") if data else None)
        return cache[key]

    def _content_similarity(self, dead, keeper):
        """Best content match over a small chapter alignment window.

        Sources rarely align 1:1 (an intro/synopsis chapter prepended to one of
        them shifts every position), so instead of comparing ``dead[pos]`` to
        ``keeper[pos]`` we try every shift in ``[-max_shift, max_shift]`` and
        keep the best mean.  A shift must still be backed by at least half the
        samples, so a single lucky pair cannot pass on its own.
        """
        dead_ids = list(dead.chapters.order_by("chapter_id").values_list("chapter_id", flat=True))
        keeper_ids = list(keeper.chapters.order_by("chapter_id").values_list("chapter_id", flat=True))
        total = min(len(dead_ids), len(keeper_ids))
        base = self._sample_positions(total, self.samples)
        if not base:
            return 0.0, 0, 0

        cache: dict = {}
        dead_texts = {pos: self._read_body(cache, dead, dead_ids[pos]) for pos in base}
        min_pairs = max(2, len(base) // 2 + 1)

        best_mean, best_shift, best_pairs = 0.0, 0, 0
        for shift in range(-self.max_shift, self.max_shift + 1):
            ratios = []
            for pos in base:
                kpos = pos + shift
                if not 0 <= kpos < len(keeper_ids):
                    continue
                a = dead_texts[pos]
                b = self._read_body(cache, keeper, keeper_ids[kpos])
                if a and b:
                    ratios.append(SequenceMatcher(None, a[:20000], b[:20000]).ratio())
            if len(ratios) >= min_pairs:
                mean = sum(ratios) / len(ratios)
                if mean > best_mean:
                    best_mean, best_shift, best_pairs = mean, shift, len(ratios)
        return best_mean, best_shift, best_pairs

    def _consider_dead_source(self, dead, handled, ext_names):
        if dead.chapters_count < self.min_chapters:
            return

        # Never delete the only source of a novel here; it is still readable.
        if dead.novel.sources.count() <= 1:
            self.kept_phase3 += 1
            self.stdout.write(
                f"  KEEP {dead.external_source.source_name} {dead.title!r}: last source of novel"
            )
            return

        if not self.include_compressed and self._is_compressed(dead):
            self.kept_phase3 += 1
            self.stdout.write(
                f"  KEEP {dead.external_source.source_name} {dead.title!r}: compressed source"
            )
            return

        for keeper, cross in self._find_keepers(dead, handled, ext_names):
            if not self.include_compressed and (
                self._is_compressed(dead) or self._is_compressed(keeper)
            ):
                continue
            if cross and not self._same_story(dead, keeper):
                continue
            mean, shift, count = self._content_similarity(dead, keeper)
            if count and mean >= self.threshold:
                offset = f", shift {shift:+d}" if shift else ""
                self._delete_source_named(
                    dead,
                    f"dead duplicate of {keeper.external_source.source_name} "
                    f"(similarity {mean:.3f}{offset})",
                )
                return

        self.kept_phase3 += 1
        self.stdout.write(
            f"  KEEP {dead.external_source.source_name} {dead.title!r}: no better live counterpart"
        )

    # -- deletion ------------------------------------------------------- #

    def _delete_source_named(self, source, reason):
        title = source.title
        source_name = source.external_source.source_name
        source_id = source.id
        if not self.apply:
            self.stdout.write(
                f"  [DRY-RUN] would delete source {source_id} {title!r} "
                f"({source_name}): {reason}"
            )
        else:
            try:
                with transaction.atomic():
                    trash_path = self._trash_source_folder(source)
                    source.delete()
                    self._audit({
                        "kind": "source",
                        "id": source_id,
                        "title": title,
                        "source_name": source_name,
                        "reason": reason,
                        "trash_path": trash_path,
                    })
                self.stdout.write(
                    self.style.SUCCESS(f"  deleted source {source_id} {title!r} ({source_name}): {reason}")
                )
            except Exception as exc:
                logger.error("prune_library: failed deleting source %s: %s", source_id, exc)
                return
        self.deleted += 1
        self._maybe_sleep()

    def _maybe_sleep(self):
        if self.apply and self.sleep > 0:
            time.sleep(self.sleep)
