"""Recompute novel sources' effective adult flag: own flag OR any R18 tag.

Tag changes already refresh it (import, admin edits, merges, the R18
classifier); run this after bulk edits made outside those paths.

With --from-meta, first restore each source's own flag (``adult_from_source``)
from its meta.json, i.e. the crawler's value. Use it to undo adult flags that an
R18 tag wrote before the own flag was stored separately (migration 0086).
"""

import json
import os

from django.core.management.base import BaseCommand

from ...models.sources_models import NovelFromSource, refresh_adult
from ...models.source_helpers import resolve_output_path

BATCH = 500


class Command(BaseCommand):
    help = "Recompute is_adult on novel sources (own flag OR an R18 tag)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-meta",
            action="store_true",
            help="Restore each source's own adult flag from its meta.json first.",
        )

    def handle(self, *args, **options):
        if options["from_meta"]:
            self._restore_from_meta()
        flagged, cleared = refresh_adult()
        self.stdout.write(f"is_adult: {flagged} source(s) flagged, {cleared} cleared.")

    def _restore_from_meta(self):
        changed, missing = [], 0
        # Only an own flag that is set can be wrong (tags only ever set it, via
        # the copy migration 0086 made): unset ones need no file read.
        rows = NovelFromSource.objects.filter(adult_from_source=True).only(
            "pk", "source_path", "adult_from_source"
        )
        for source in rows.iterator(chunk_size=BATCH):
            path = resolve_output_path(source.source_path, "meta.json") if source.source_path else None
            if not path or not os.path.isfile(path):
                missing += 1
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    novel = (json.load(f) or {}).get("novel") or {}
            except (OSError, ValueError):
                missing += 1
                continue
            own = bool(novel.get("is_adult", False))
            if own != source.adult_from_source:
                source.adult_from_source = own
                changed.append(source)
        NovelFromSource.objects.bulk_update(changed, ["adult_from_source"], batch_size=BATCH)
        self.stdout.write(
            f"adult_from_source: {len(changed)} source(s) restored from meta.json; "
            f"{missing} without a readable meta.json kept their current value."
        )
