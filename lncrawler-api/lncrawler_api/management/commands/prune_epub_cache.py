"""
Delete expired and orphaned EPUB cache files under ``epub_cache/`` folders.

EPUBs are cached inside each source folder and reused for ``MAX_CACHE_AGE``.
Nothing else removes them once they expire, so this command does it:

- ``*.epub`` older than ``MAX_CACHE_AGE`` are deleted (they would be rebuilt).
- ``*.tmp`` older than one hour are leftovers from an interrupted build.
- ``*.lock`` files are never deleted. Removing a lock file while another process
  waits on its flock lets two builds run at once, so the lock stays in place.
"""

import logging
import os
import time

from django.core.management.base import BaseCommand

from ...models import NovelFromSource
from ...models.source_helpers import resolve_output_path
from ...services.epub_service import CACHE_DIRNAME, LOCK_SUFFIX, MAX_CACHE_AGE

logger = logging.getLogger(__name__)

STALE_PARTIAL_AGE = 3600  # seconds


def _human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


class Command(BaseCommand):
    help = "Delete expired EPUB cache files, stale temp files and unused locks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = time.time()
        max_age = MAX_CACHE_AGE.total_seconds()

        self.count = 0
        self.bytes = 0
        self.dry_run = dry_run

        # Visit only each source's epub_cache folder; walking the whole library
        # would stat every chapter file of every novel.
        source_paths = (
            NovelFromSource.objects.exclude(source_folder__isnull=True)
            .exclude(source_folder="")
            .exclude(novel__novel_path="")
            .values_list("novel__novel_path", "source_folder")
            .iterator()
        )
        for novel_path, source_folder in source_paths:
            source_path = os.path.join(novel_path, source_folder)
            cache_dir = os.path.join(resolve_output_path(source_path), CACHE_DIRNAME)
            try:
                names = os.listdir(cache_dir)
            except OSError:
                continue
            for name in names:
                path = os.path.join(cache_dir, name)
                try:
                    self._prune_file(path, name, now, max_age)
                except OSError as e:
                    logger.warning("Could not prune %s: %s", path, e)

        verb = "Would delete" if dry_run else "Deleted"
        self.stdout.write(
            f"{verb} {self.count} EPUB cache file(s), freeing {_human(self.bytes)}."
        )

    def _prune_file(self, path, name, now, max_age):
        age = now - os.path.getmtime(path)

        if name.endswith(".epub"):
            expired = age > max_age
        elif name.endswith(".tmp"):
            expired = age > STALE_PARTIAL_AGE
        elif name.endswith(LOCK_SUFFIX):
            # Lock files stay (see the module docstring).
            return
        else:
            return

        if expired:
            self._remove(path, os.path.getsize(path))

    def _remove(self, path, size):
        if not self.dry_run:
            os.remove(path)
        self.count += 1
        self.bytes += size

