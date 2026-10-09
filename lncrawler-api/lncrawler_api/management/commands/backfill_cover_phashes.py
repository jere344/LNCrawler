"""Backfill ``NovelFromSource.cover_phash`` for the covers already on disk.

New covers get their dHash at import (see ``cover_service.generate_cover_min``).
This fills in the historical backlog so cross-source cover matching has data.
Idempotent: only rows with a NULL hash are touched.
"""
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from lncrawler_api.models import NovelFromSource
from lncrawler_api.services.cover_service import dhash_file

BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Compute cover dHash for sources that do not have one yet."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
        parser.add_argument("--limit", type=int, default=0, help="Stop after N sources (0 = no limit).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        limit = options["limit"]
        dry_run = options["dry_run"]

        qs = (
            NovelFromSource.objects.filter(cover_phash__isnull=True)
            .exclude(cover_min_path__isnull=True)
            .order_by("pk")
        )

        base = Path(settings.LNCRAWL_OUTPUT_PATH)
        done = updated = missing = 0
        last_pk = 0
        while True:
            batch = list(qs.filter(pk__gt=last_pk)[:batch_size])
            if not batch:
                break
            to_update = []
            for source in batch:
                last_pk = source.pk
                if limit and done >= limit:
                    break
                done += 1
                path = base / source.cover_min_path
                if not path.is_file():
                    missing += 1
                    continue
                try:
                    source.cover_phash = dhash_file(path)
                except Exception as exc:  # unreadable/corrupt image
                    self.stderr.write(f"  {source.pk}: {exc}")
                    missing += 1
                    continue
                to_update.append(source)
                updated += 1
            if to_update and not dry_run:
                NovelFromSource.objects.bulk_update(to_update, ["cover_phash"])
            self.stdout.write(f"  {done} seen, {updated} hashed, {missing} missing")
            if limit and done >= limit:
                break

        verb = "would hash" if dry_run else "hashed"
        self.stdout.write(self.style.SUCCESS(
            f"cover phash backfill: {verb} {updated}/{done} source(s), {missing} unreadable/missing"
        ))
