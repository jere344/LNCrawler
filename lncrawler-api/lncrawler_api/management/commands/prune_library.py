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

import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from lncrawler_api.services.prune.common import MIN_NOVEL_AGE
from lncrawler_api.services.prune.cursor import CursorMixin
from lncrawler_api.services.prune.dead import DeadDuplicatesMixin
from lncrawler_api.services.prune.deletion import DeletionMixin
from lncrawler_api.services.prune.empty import EmptySourcesMixin
from lncrawler_api.services.prune.orphans import OrphanNovelsMixin
from lncrawler_api.services.prune.porting import PortingMixin
from lncrawler_api.services.prune.similarity import SimilarityMixin
from lncrawler_api.services.prune.trash import TrashMixin
from lncrawler_api.services.prune.unregistered import UnregisteredFoldersMixin


class Command(
    UnregisteredFoldersMixin,
    OrphanNovelsMixin,
    EmptySourcesMixin,
    DeadDuplicatesMixin,
    SimilarityMixin,
    PortingMixin,
    DeletionMixin,
    TrashMixin,
    CursorMixin,
    BaseCommand,
):
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
