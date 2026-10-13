"""Progressively clean the library.

Phases, run in order, each bounded by ``--limit`` candidates *examined* per run
so the first pass over a large catalogue is spread over many invocations instead
of scanning the whole DB (and running for hours) at once:

0. unregistered library folders (a folder no ``Novel``/``NovelFromSource``/
   ``NovelAlias`` refers to) moved back to the import folder (filesystem sweep)
1. orphan novels (no NovelFromSource left)
2. empty sources (no chapter, or no chapter with content)
3. dead sources (no longer handled by the crawler) superseded by a live
   source of the same novel with at least as many chapters. Comments, reading history and
   votes attached to the discarded source are ported to the keeper first.

Each phase walks its candidates in primary-key order and remembers where it
stopped in ``<output>/.prune_trash/prune_cursor.json``, so repeated (or
scheduled) runs continue through the DB and wrap around once a pass is done.
Deletions are naturally capped by the same limit: at most one per candidate.

Deleting is destructive, so ``--apply`` is required; the default is a dry run.
Source folders are moved to ``<LNCRAWL_OUTPUT_PATH>/.prune_trash`` instead of
being removed in place, and every real deletion is appended to
``audit.jsonl`` there. A dry run never modifies the DB or moves/deletes files.
Reads may create the usual ``.lncrawler.lock`` file in a source folder, as any
chapter read does.
"""

import json
import logging
import os
import re
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import CharField, Count, Exists, OuterRef
from django.db.models.functions import Cast, MD5, Substr
from django.utils import timezone

from lncrawler_api.models import (
    Comment,
    Chapter,
    ExternalSource,
    Novel,
    NovelAlias,
    NovelFromSource,
    ReadingHistory,
    SourceVote,
    resolve_output_path,
)
from lncrawler_api.services.novel_operations import (
    recount_comment_count,
    recount_source_votes,
)
from lncrawler_api.utils import chapter_utils
from lncrawler_api.utils.lncrawler_paths import move_and_merge_directory, sanitize
from lncrawler_api.utils.slug import slugify

logger = logging.getLogger("lncrawler_api")

FAIL_MESSAGE = "Failed to download chapter body"

# A novel is never pruned before it has had time to settle, so a fresh crawl
# (or a bad first import) cannot be wiped before it is even reviewed.
MIN_NOVEL_AGE = timedelta(days=7)

# Phase 3 compares at most this many words per chapter. Translations of the same
# chapter share their prose either way, and the cap bounds SequenceMatcher's
# worst case on very long chapters.
MAX_COMPARE_WORDS = 4000

# Phase 3 verdicts ("kept, nothing changed") persisted between runs.
VERDICTS_FILE = "prune_phase3_kept.json"

# A sample shorter than this is a placeholder (a failed download leaves a short
# stub body), not content, so it is ignored instead of counted as a mismatch.
MIN_SAMPLE_WORDS = 50


def normalize_source_name(name: str) -> str:
    """Same normalization for registry names and DB source names."""
    if not name:
        return ""
    normalized = sanitize(str(name)).lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def normalize_body(body) -> str:
    if not body:
        return ""
    text = re.sub(r"(?is)<[^>]+>", " ", str(body))
    text = text.replace(FAIL_MESSAGE, "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def tokenize_body(text) -> list:
    """Word tokens of a normalized body, capped at ``MAX_COMPARE_WORDS``."""
    return (text or "").split()[:MAX_COMPARE_WORDS]


class _UnmappedComments(Exception):
    """Porting a source would lose comments (no --force), so its deletion is refused."""

    def __init__(self, count):
        super().__init__(f"{count} comment(s) cannot be mapped to the keeper")
        self.count = count


class Command(BaseCommand):
    help = "Progressively prune orphan novels, empty sources and superseded dead sources."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete. Without it the command only reports (dry run).",
        )
        parser.add_argument(
            "--limit", type=int, default=200,
            help=(
                "Max candidates each phase examines per run (0 = unlimited). "
                "Runs resume from a saved cursor, so the DB is walked in batches."
            ),
        )
        parser.add_argument(
            "--threshold", type=float, default=0.90,
            help="Min mean chapter-content similarity to treat a dead source as superseded.",
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
        # Accepted for compatibility only; phase 3 no longer skips compressed sources.
        parser.add_argument(
            "--include-compressed", action="store_true",
            help=(
                "No-op for phase 3: compressed sources are always examined, since "
                "chapters are read without extracting json.7z."
            ),
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Delete even when attached user data exists.",
        )
        parser.add_argument(
            "--recheck", action="store_true",
            help="Ignore stored phase 3 verdicts and compare every dead source again.",
        )
        parser.add_argument(
            "--source", type=str, default=None,
            help="Limit phase 3 to this ExternalSource name (normalized).",
        )
        parser.add_argument(
            "--percent", type=float, default=100.0,
            help=(
                "Only examine this share of novels (0-100) for a quick preview. "
                "Stable id-hash sample, so repeat runs check the same subset."
            ),
        )
        parser.add_argument(
            "--sweep-unregistered", action="store_true",
            help=(
                "Also move library folders no DB row points at back to the import "
                "folder. Off by default: a folder can belong to a download that is "
                "still in progress (the folder is created before the DB row), so "
                "this must never run on the scheduler."
            ),
        )

    # -- run ----------------------------------------------------------- #

    def handle(self, *args, **options):
        self.apply = options["apply"]
        self.limit = options["limit"]
        self.threshold = options["threshold"]
        self.samples = options["samples"]
        self.max_shift = max(0, options["max_shift"])
        self.min_chapters = options["min_chapters"]
        self.sleep = options["sleep"]
        self.force = options["force"]
        self.recheck = options["recheck"]
        self.source_filter = options["source"]
        self.percent = options["percent"]
        self.sweep_unregistered = options["sweep_unregistered"]
        if not 0 < self.percent <= 100:
            self.stdout.write(self.style.ERROR("--percent must be between 1 and 100"))
            return

        self.root = settings.LNCRAWL_OUTPUT_PATH
        self.trash_root = os.path.join(self.root, ".prune_trash")
        self.age_cutoff = timezone.now() - MIN_NOVEL_AGE
        self.deleted = 0
        self.examined = 0
        self.kept_phase3 = 0
        # Cursors are scoped by the filters that change the candidate set, so a
        # manual --source/--percent run cannot resume the scheduler's position.
        self.cursor_scope = f"{self.source_filter or '-'}|{self.percent:g}"
        self.cursor = self._load_cursor()
        self.verdicts = self._load_verdicts()

        mode = "APPLY" if self.apply else "DRY-RUN"
        self.stdout.write(self.style.WARNING(
            f"prune_library ({mode}) limit={self.limit or 'unlimited'} "
            f"threshold={self.threshold} percent={self.percent:g}"
        ))

        if self.sweep_unregistered:
            self._phase_unregistered_folders()
        self._phase_orphan_novels()
        self._phase_empty_sources()
        self._phase_dead_duplicates()

        self.stdout.write(self.style.SUCCESS(
            f"prune_library: {self.examined} candidate(s) examined, "
            f"{self.deleted} deletion(s) "
            f"({'applied' if self.apply else 'would happen'}), "
            f"{self.kept_phase3} dead source(s) kept"
        ))
        if self.limit:
            self.stdout.write(
                "  cursor saved; the next run resumes where this one stopped."
            )

    # -- phase 0: unregistered folders --------------------------------- #

    def _phase_unregistered_folders(self):
        """Move library folders the DB does not know about back to the import folder.

        ``run_import`` only ever moves into the library; nothing removes a folder
        whose DB rows were dropped (fresh DB, bad merge, manual cleanup). Those
        folders are invisible to the app yet keep taking space. This is a
        filesystem sweep, so it ignores the cursor/--limit/--percent/--source
        knobs, but it only runs when ``--sweep-unregistered`` is passed (a folder
        with no row may belong to a download that is still in progress) and only
        moves when ``--apply`` is set.
        """
        import_folder = settings.IMPORT_FOLDER_PATH
        if not import_folder:
            self.stdout.write(self.style.ERROR(
                "IMPORT_FOLDER_PATH is not defined; skipping unregistered-folder sweep"
            ))
            return

        known = self._known_top_level_folders()
        moved = 0
        for name in sorted(os.listdir(self.root)):
            src = os.path.join(self.root, name)
            if name.startswith(".") or not os.path.isdir(src):
                continue
            if name in known or slugify(name) in known:
                continue

            target = os.path.join(import_folder, name)
            if not self.apply:
                self.stdout.write(f"  [DRY-RUN] would move unregistered {name!r} -> {target}")
            else:
                os.makedirs(import_folder, exist_ok=True)
                if os.path.exists(target):
                    move_and_merge_directory(src, target)
                else:
                    shutil.move(src, target)
                self.stdout.write(self.style.SUCCESS(f"  moved unregistered {name!r} -> {target}"))
            moved += 1

        if moved:
            self.stdout.write(self.style.SUCCESS(
                f"  unregistered folders: {moved} "
                f"{'moved' if self.apply else 'would be moved'}"
            ))

    @staticmethod
    def _known_top_level_folders() -> set:
        """Top-level folder names any DB row points at (novel_path/source_path/alias)."""
        known = set()
        paths = list(Novel.objects.exclude(
            novel_path__isnull=True).values_list("novel_path", flat=True))
        paths += list(NovelFromSource.objects.exclude(
            source_path__isnull=True).values_list("source_path", flat=True))
        for path in paths:
            if path:
                known.add(path.split(os.sep, 1)[0])
        known.update(NovelAlias.objects.values_list("slug", flat=True))
        return known

    # -- bounded run helpers ------------------------------------------- #

    def _load_cursor(self) -> dict:
        try:
            with open(os.path.join(self.trash_root, "prune_cursor.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_cursor(self):
        if not self.apply:
            return
        os.makedirs(self.trash_root, exist_ok=True)
        path = os.path.join(self.trash_root, "prune_cursor.json")
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.cursor, fh)
        os.replace(tmp, path)

    def _verdicts_path(self):
        return os.path.join(self.trash_root, VERDICTS_FILE)

    def _load_verdicts(self) -> dict:
        try:
            with open(self._verdicts_path(), encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_verdicts(self):
        if not self.apply:
            return
        os.makedirs(self.trash_root, exist_ok=True)
        path = self._verdicts_path()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.verdicts, fh)
        os.replace(tmp, path)

    def _cursor_key(self, phase):
        return f"{phase}:{self.cursor_scope}"

    def _window(self, queryset, phase, order="pk"):
        """Return the next batch of candidates, continuing from the saved cursor.

        Candidates are walked in ``order``; if ``--limit`` is set only that many
        are fetched, starting after the last pk seen for this phase. The cursor
        is updated by ``_advance`` once the batch is processed.
        """
        queryset = queryset.order_by(order)
        if not self.limit:
            return queryset
        start = self.cursor.get(self._cursor_key(phase))
        if start is not None:
            queryset = queryset.filter(**{f"{order}__gt": start})
        return queryset[: self.limit]

    def _advance(self, phase, last_pk, examined):
        """Record how far this phase got, wrapping to the start after a pass."""
        self.examined += examined
        if not self.limit:
            return
        key = self._cursor_key(phase)
        if examined < self.limit:
            self.cursor.pop(key, None)
        elif last_pk is not None:
            self.cursor[key] = last_pk if isinstance(last_pk, int) else str(last_pk)
        self._save_cursor()

    def _sample(self, queryset, field="id"):
        """Keep an MD5-bucket slice of the rows, so --percent N examines ~N%.

        Keys are UUIDs, so hash the key to a uniform hex bucket instead of
        sorting randomly: the subset is stable across runs. The bucket is a
        computed predicate, so it cannot use an index.
        """
        if self.percent >= 100:
            return queryset
        bucket = Substr(MD5(Cast(field, CharField())), 1, 2)
        threshold = format(int(self.percent / 100 * 256), "02x")
        return queryset.annotate(_bucket=bucket).filter(_bucket__lt=threshold)

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
        if SourceVote.objects.filter(source=source).exists():
            return True
        return False

    # -- file handling -------------------------------------------------- #

    def _move_to_trash(self, rel):
        """Move a source folder under ``.prune_trash``; returns the new path or None.

        ``rel`` comes from the DB, so it is resolved the same way the model
        resolves it, and refused unless it lies strictly inside the library root
        and outside the trash itself.
        """
        if not rel:
            return None
        root = os.path.realpath(self.root)
        trash = os.path.realpath(self.trash_root)
        abs_src = resolve_output_path(rel)
        if (
            abs_src is None
            or abs_src == root
            or abs_src == trash
            or abs_src.startswith(trash + os.sep)
        ):
            logger.error("prune_library: refusing to trash %r: outside the library", rel)
            return None
        if not os.path.isdir(abs_src):
            return None
        clean_rel = os.path.relpath(abs_src, root)
        dest = os.path.join(self.trash_root, clean_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = os.path.join(self.trash_root, f"{stamp}_{clean_rel}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(abs_src, dest)
        return dest

    def _audit(self, entry):
        os.makedirs(self.trash_root, exist_ok=True)
        entry = {"ts": datetime.now().isoformat(), **entry}
        with open(os.path.join(self.trash_root, "audit.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    # -- phase 1: orphan novels ---------------------------------------- #

    def _phase_orphan_novels(self):
        self.stdout.write("Phase 1: orphan novels")
        orphans = self._sample(
            Novel.objects.filter(
                ~Exists(NovelFromSource.objects.filter(novel_id=OuterRef("pk"))),
                created_at__lt=self.age_cutoff,
            )
        )
        examined, last_pk = 0, None
        for novel in self._window(orphans, "novel").iterator():
            last_pk = novel.pk
            examined += 1
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
        self._advance("novel", last_pk, examined)

    # -- phase 2: empty sources ---------------------------------------- #

    def _chapter_files_on_disk(self, base) -> bool:
        """Whether the source folder holds chapter files (loose json or archive)."""
        root = Path(base)
        if (root / "json.7z").is_file():
            return True
        json_dir = root / "json"
        return json_dir.is_dir() and any(json_dir.glob("*.json"))

    def _repair_has_content(self, source, base) -> bool:
        """Re-check the flagged chapters on disk; repair has_content only on --apply.

        Strict read: an archive that cannot be read raises ChapterReadError, so
        the caller keeps the source instead of treating it as empty.
        """
        pending = list(source.chapters.filter(has_content=False).values_list("pk", "chapter_id"))
        if not pending:
            return True  # every chapter already has content
        # One batch read; archived chapters are never extracted into the library.
        data = chapter_utils.read_chapters_no_extract(
            base, [cid for _, cid in pending], strict=True
        )
        repaired = [
            pk for pk, cid in pending
            if cid in data and chapter_utils.chapter_dict_has_content(data[cid])
        ]
        if repaired and self.apply:
            Chapter.objects.filter(pk__in=repaired).update(has_content=True)
        return bool(repaired)

    def _keep_reason(self, source):
        """Why a source flagged empty must be kept, or None when it may be deleted.

        ``has_content`` is a cached column written at import time, so an import
        that ran before the bodies landed leaves it False while the files are on
        disk. Deletion is destructive, so the files are re-checked first.
        """
        base = source.absolute_source_path
        if not base:
            return None
        if not source.chapters.exists():
            if self._chapter_files_on_disk(base):
                return "chapter files on disk but no rows"
            return None
        try:
            found = self._repair_has_content(source, base)
        except chapter_utils.ChapterReadError as exc:
            return f"unreadable ({exc})"
        return "content present on disk" if found else None

    def _phase_empty_sources(self):
        self.stdout.write("Phase 2: empty sources")
        empties = self._sample(
            NovelFromSource.objects.filter(
                ~Exists(Chapter.objects.filter(novel_from_source_id=OuterRef("pk"), has_content=True))
            )
            .filter(novel__created_at__lt=self.age_cutoff)
            .select_related("novel", "external_source"),
            field="novel_id",
        )
        examined, last_pk = 0, None
        for source in self._window(empties, "empty").iterator():
            last_pk = source.pk
            examined += 1
            keep = self._keep_reason(source)
            if keep:
                self.stdout.write(f"  KEEP source {source.id} {source.title!r}: {keep}")
                continue
            if not self.force and self._source_has_user_data(source):
                self.stdout.write(
                    f"  SKIP source {source.id} {source.title!r}: has user data"
                )
                continue
            self._delete_source_named(source, "empty source")
        self._advance("empty", last_pk, examined)

    # -- phase 3: dead-source duplicates ------------------------------- #

    def _load_handled_sources(self):
        """Names and hosts served by an enabled crawler.

        Disabled crawlers (``is_disabled`` / ``disable_reason``, same test as
        ``crawler_registry.has_crawler``) are skipped entirely, so their sources
        count as dead. A host also served by an enabled crawler stays live.
        """
        handled = set()
        try:
            crawler_dir = Path(settings.BASE_DIR).parent / "lncrawler-crawler"
            if str(crawler_dir) not in sys.path:
                sys.path.insert(0, str(crawler_dir))
            from lncrawl.core.sources import crawler_list, load_sources

            load_sources()
            for cls in crawler_list:
                if getattr(cls, "is_disabled", False) or getattr(cls, "disable_reason", None):
                    continue
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
        self.stdout.write("Phase 3: superseded dead sources")
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
        live_ext_ids = [pk for pk, name in ext_names.items() if name in handled]
        if not dead_ids or not live_ext_ids:
            self.stdout.write("  no dead sources to examine")
            return

        # Only dead sources whose novel has a live sibling can be superseded, so
        # the others are filtered out here and never use up --limit.
        has_live_sibling = Exists(NovelFromSource.objects.filter(
            novel_id=OuterRef("novel_id"), external_source_id__in=live_ext_ids,
        ))
        dead_qs = self._sample(
            NovelFromSource.objects.filter(external_source_id__in=dead_ids)
            .filter(novel__created_at__lt=self.age_cutoff)
            .filter(has_live_sibling)
            .select_related("novel", "external_source"),
            field="novel_id",
        )

        examined, last_pk = 0, None
        for dead in self._window(dead_qs, "dead").iterator():
            last_pk = dead.pk
            examined += 1
            self._consider_dead_source(dead, handled, ext_names)
        self._advance("dead", last_pk, examined)
        self._save_verdicts()
        self.stdout.write(f"  examined {examined} dead source(s)")

    def _is_live(self, source, handled, ext_names) -> bool:
        name = ext_names.get(source.external_source_id)
        if name is None:
            name = normalize_source_name(source.external_source.source_name)
        return name in handled

    def _find_keepers(self, dead, handled, ext_names):
        """Live sources of the same novel that hold at least as many chapters as ``dead``.

        A dead source can never grow, so an equal-length live source with
        matching content is a valid replacement.

        Only siblings are considered: a different novel is a different story,
        even when metadata similarity says otherwise, so its sources are never
        used to justify deleting one of this novel's sources.
        """
        count = self._chapter_count(dead)
        siblings = (
            dead.novel.sources.exclude(pk=dead.pk)
            .select_related("external_source")
            .annotate(_chapters=Count("chapters"))
        )
        return [
            sibling
            for sibling in siblings
            if self._is_live(sibling, handled, ext_names)
            and sibling._chapters >= count
        ]

    @staticmethod
    def _chapter_count(source) -> int:
        """Chapter count from the query annotation when present (no N+1)."""
        count = getattr(source, "_chapters", None)
        return count if count is not None else source.chapters_count

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

    @staticmethod
    def _updated_key(source):
        updated = source.last_chapter_update
        return updated.isoformat() if updated else None

    def _verdict_signature(self, dead, keepers) -> dict:
        """What a kept verdict depends on; any change re-runs the comparison."""
        return {
            "dead_chapters": self._chapter_count(dead),
            "dead_updated": self._updated_key(dead),
            "threshold": self.threshold,
            "samples": self.samples,
            "max_shift": self.max_shift,
            "keepers": sorted(
                [sibling.pk, self._chapter_count(sibling), self._updated_key(sibling)]
                for sibling in keepers
            ),
        }

    def _consider_dead_source(self, dead, handled, ext_names):
        if self._chapter_count(dead) < self.min_chapters:
            return

        # Never delete the only source of a novel here; it is still readable.
        if dead.novel.sources.count() <= 1:
            self.kept_phase3 += 1
            return

        keepers = self._find_keepers(dead, handled, ext_names)
        key = str(dead.pk)
        signature = self._verdict_signature(dead, keepers)
        # Nothing changed since the last kept verdict: skip without reading chapters.
        if not self.recheck and self.verdicts.get(key) == signature:
            self.kept_phase3 += 1
            return
        if not keepers:
            self.verdicts[key] = signature
            self.kept_phase3 += 1
            return

        dead_ctx = self._dead_context(dead)
        for keeper in keepers:
            mean, shift, count = self._content_similarity(dead_ctx, keeper)
            if not (count and mean >= self.threshold):
                continue
            offset = f", shift {shift:+d}" if shift else ""
            self.verdicts.pop(key, None)
            if self._delete_source_named(
                dead,
                f"superseded by {keeper.external_source.source_name} "
                f"(similarity {mean:.3f}{offset})",
                keeper=keeper,
                shift=shift,
            ):
                return
            # Refused (unmapped comments) or failed: try the next keeper.

        self.verdicts[key] = signature
        self.kept_phase3 += 1

    # -- deletion ------------------------------------------------------- #

    def _chapter_mapper(self, loser, keeper, shift=0):
        """Map a loser chapter to its keeper chapter, or None when there is none.

        Chapter identity across sources is positional (ids are per-source). A
        shared url is the strongest match, so try it first; otherwise map loser
        position -> keeper position + shift, the same alignment
        ``_content_similarity`` uses. Chapters that are not the loser's are left
        untouched.
        """
        loser_pos = {
            cid: pos for pos, cid in enumerate(
                loser.chapters.order_by("chapter_id").values_list("chapter_id", flat=True)
            )
        }
        keeper_chapters = list(keeper.chapters.order_by("chapter_id"))
        keeper_ids = [c.chapter_id for c in keeper_chapters]
        keeper_by_id = {c.chapter_id: c for c in keeper_chapters}
        keeper_by_url = {c.url: c for c in keeper_chapters if c.url}

        def map_chapter(chapter):
            if chapter is None:
                return None
            if chapter.novel_from_source_id != loser.pk:
                return chapter
            if chapter.url:
                by_url = keeper_by_url.get(chapter.url)
                if by_url is not None:
                    return by_url
            pos = loser_pos.get(chapter.chapter_id)
            if pos is not None:
                kpos = pos + shift
                if 0 <= kpos < len(keeper_ids):
                    return keeper_by_id[keeper_ids[kpos]]
            return None

        return map_chapter

    def _unmapped_comments(self, loser, keeper, shift=0) -> list:
        """Comments on ``loser`` that would have no chapter on ``keeper`` (read only)."""
        map_chapter = self._chapter_mapper(loser, keeper, shift)
        comments = Comment.objects.filter(chapter__novel_from_source=loser).select_related("chapter")
        return [comment for comment in comments if map_chapter(comment.chapter) is None]

    def _port_user_data(self, loser, keeper, shift=0) -> int:
        """Hand a discarded source's user data to the keeper before deletion.

        Votes and reading history would otherwise cascade away with the source,
        and chapter comments with its chapters. Because the keeper is a sibling
        of the same novel, reading history stays unique per (user, novel).

        ``shift`` is the positional offset ``_content_similarity`` found (the
        dead source may prepend an intro chapter, moving every chapter by one),
        so chapter-keyed data lands on the right chapter instead of off by N.

        A comment with no keeper chapter is lost if it is deleted, so without
        ``--force`` this raises ``_UnmappedComments`` before writing anything.
        Returns the number of comments dropped (only non-zero with ``--force``).
        """
        map_chapter = self._chapter_mapper(loser, keeper, shift)
        comments = list(
            Comment.objects.filter(chapter__novel_from_source=loser).select_related("chapter")
        )
        unmapped = [comment for comment in comments if map_chapter(comment.chapter) is None]
        if unmapped and not self.force:
            raise _UnmappedComments(len(unmapped))

        existing_voters = set(keeper.votes.values_list("ip_address", flat=True))
        SourceVote.objects.filter(source=loser).exclude(
            ip_address__in=existing_voters
        ).update(source=keeper)
        SourceVote.objects.filter(source=loser).delete()

        # Move the history row and repoint its progress marker: last_read_chapter
        # points at one of the loser's chapters, which is about to be deleted
        # (SET_NULL), so without this the user keeps the history but loses their
        # place.
        for history in ReadingHistory.objects.filter(source=loser).select_related(
            "last_read_chapter"
        ):
            history.source = keeper
            history.last_read_chapter = map_chapter(history.last_read_chapter)
            history.save(update_fields=["source", "last_read_chapter"])

        dropped = 0
        for comment in comments:
            target = map_chapter(comment.chapter)
            if target is None:
                comment.delete()
                dropped += 1
            else:
                comment.chapter = target
                comment.save(update_fields=["chapter"])

        keeper.refresh_from_db()
        recount_source_votes(keeper)
        recount_comment_count(keeper.novel)
        return dropped

    def _delete_source_named(self, source, reason, keeper=None, shift=0) -> bool:
        """Delete one source, porting its user data to ``keeper`` first.

        Returns True when the source is (or in a dry run would be) deleted. The
        row goes first, inside a transaction. The folder is moved to the trash
        only after the commit, so a failed delete never leaves a folder moved for
        a row that still exists. If the move itself fails the row is already
        gone and the folder stays where it is, for the opt-in unregistered sweep.
        """
        title = source.title
        source_name = source.external_source.source_name
        source_id = source.id
        port = " and port user data" if keeper is not None else ""
        if not self.apply:
            if keeper is not None:
                unmapped = len(self._unmapped_comments(source, keeper, shift))
                if unmapped and not self.force:
                    self.stdout.write(
                        f"  [DRY-RUN] would KEEP source {source_id} {title!r}: "
                        f"{unmapped} comment(s) cannot be mapped (--force would drop them)"
                    )
                    return False
                if unmapped:
                    port += f" (would drop {unmapped} unmapped comment(s))"
            self.stdout.write(
                f"  [DRY-RUN] would delete source {source_id} {title!r} "
                f"({source_name}){port}: {reason}"
            )
        else:
            rel = source.source_path
            dropped = 0
            try:
                with transaction.atomic():
                    if keeper is not None:
                        dropped = self._port_user_data(source, keeper, shift)
                    # Unlink the folder first: delete() would rmtree it otherwise.
                    source.source_path = None
                    source.save(update_fields=["source_path"])
                    source.delete()
            except _UnmappedComments as exc:
                self.stdout.write(
                    f"  KEEP source {source_id} {title!r}: {exc} (--force would drop them)"
                )
                return False
            except Exception as exc:
                logger.error("prune_library: failed deleting source %s: %s", source_id, exc)
                return False

            trash_path = None
            try:
                trash_path = self._move_to_trash(rel)
            except Exception as exc:
                logger.error(
                    "prune_library: deleted source %s but could not move %s to trash: %s",
                    source_id, rel, exc,
                )
            self._audit({
                "kind": "source",
                "id": source_id,
                "title": title,
                "source_name": source_name,
                "reason": reason,
                "keeper_id": keeper.id if keeper else None,
                "dropped_comments": dropped,
                "trash_path": trash_path,
            })
            self.stdout.write(
                self.style.SUCCESS(f"  deleted source {source_id} {title!r} ({source_name}): {reason}")
            )
        self.deleted += 1
        self._maybe_sleep()
        return True

    def _maybe_sleep(self):
        if self.apply and self.sleep > 0:
            time.sleep(self.sleep)
