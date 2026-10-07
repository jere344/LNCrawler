"""One-time repair of ``Chapter.has_content`` from the on-disk metadata.

``has_content`` is cached at import time. Imports that ran before the crawler
started persisting a reliable ``success`` flag (or before bodies landed) can
leave it wrong, which hides readable chapters from the reader, EPUB export and
navigation. New imports set it from ``meta.json`` directly; this command fixes
the historical backlog and is idempotent, so it is safe to run repeatedly.
"""
import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from lncrawler_api.models import Chapter, NovelFromSource
from lncrawler_api.utils import chapter_utils

BATCH_SIZE = 500
MARKER_NAME = ".has_content_backfilled_v1"
# Arbitrary fixed key for pg_try_advisory_lock, so concurrent API replicas do
# not run the same repair twice.
ADVISORY_LOCK_KEY = 0x68617363  # "hasc"


class Command(BaseCommand):
    help = "Recompute Chapter.has_content from meta.json success flags."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=BATCH_SIZE,
            help="NovelFromSource rows loaded per batch.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Run even if the completion marker already exists.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        marker = os.path.join(settings.LNCRAWL_OUTPUT_PATH, MARKER_NAME)
        if os.path.exists(marker) and not options["force"]:
            self.stdout.write("has_content backfill already done; skipping.")
            return

        # Only one replica should run this at a time.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
            acquired = cursor.fetchone()[0]
        if not acquired:
            self.stdout.write("has_content backfill already running elsewhere; skipping.")
            return

        try:
            self._run(options, marker)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])

    def _run(self, options, marker):
        dry_run = options["dry_run"]
        batch_size = max(1, options["batch_size"])
        sources = changed = 0
        last_pk = 0

        qs = (
            NovelFromSource.objects.exclude(source_path__isnull=True)
            .prefetch_related("chapters")
            .order_by("pk")
        )
        while True:
            batch = list(qs.filter(pk__gt=last_pk)[:batch_size])
            if not batch:
                break
            for source in batch:
                last_pk = source.pk
                sources += 1
                changed += self._backfill_source(source, dry_run)
            self.stdout.write(f"  {sources} source(s), {changed} chapter(s) updated")

        if not dry_run:
            Path(marker).touch()

        verb = "would update" if dry_run else "updated"
        self.stdout.write(self.style.SUCCESS(
            f"has_content backfill: {sources} source(s), {changed} chapter(s) {verb}"
        ))

    def _backfill_source(self, source, dry_run):
        base = source.absolute_source_path
        if not base:
            return 0

        # meta.json stores chapters without bodies and its `success` values are
        # only accurate once the crawl completed (the crawler writes an
        # all-False meta.json at the start of every crawl). So trust True
        # always, trust False only when completed, else read the file.
        meta_success = {}
        completed = False
        try:
            with open(Path(base) / "meta.json", "r", encoding="utf-8") as fh:
                data = json.load(fh)
            completed = bool(data.get("session", {}).get("completed", False))
            for chapter in data.get("novel", {}).get("chapters", []):
                if chapter.get("id") is not None and "success" in chapter:
                    meta_success[chapter["id"]] = bool(chapter.get("success"))
        except (OSError, ValueError):
            pass

        changed = []
        for chapter in source.chapters.all():
            if chapter.chapter_id in meta_success and (
                meta_success[chapter.chapter_id] or completed
            ):
                has_content = meta_success[chapter.chapter_id]
            else:
                has_content = chapter_utils.check_chapter_has_content(
                    base, chapter.chapter_id
                )
            if chapter.has_content != has_content:
                chapter.has_content = has_content
                changed.append(chapter)

        if changed and not dry_run:
            Chapter.objects.bulk_update(changed, ["has_content"])
        return len(changed)
