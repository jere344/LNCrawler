# =========================================================================
#  ONE-TIME SCRIPT -- DELETE THIS FILE AFTER RUNNING IT ON PRODUCTION.
# =========================================================================
#  The API used to derive ``Novel.slug`` with Django's ``slugify``, which
#  strips anything non-ASCII. A folder named after a Korean or Russian title
#  therefore collapsed to a stray Latin letter ("s급 헌터" -> "s") or to an
#  empty string, so those novels had an unusable slug in their URLs.
#
#  New imports now slugify with python-slugify (see utils/slug.py), which
#  transliterates instead. This command repairs the rows that were created the
#  old way: for every novel whose on-disk folder holds non-ASCII characters, it
#  recomputes the slug from the folder name and records the old slug as a
#  ``NovelAlias`` so existing links keep resolving.
#
#  The folder itself is left alone on purpose: the crawler names folders with
#  ``sanitize(title).lower()`` (lncrawler_paths.get_novel_output_path), which
#  keeps non-Latin characters, so a future crawl of the same title recreates
#  the exact same folder and reattaches by ``novel_path``. Renaming the folder
#  would diverge from that and risk a duplicate novel.
#
#  Run it once on prod (dry run by default, then --apply), then delete this
#  whole file.
# =========================================================================
"""Repair Novel slugs that lost their non-Latin characters to Django slugify."""

import json
import logging
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from lncrawler_api.models import Novel, NovelAlias
from lncrawler_api.utils.slug import slugify

logger = logging.getLogger("lncrawler_api")


def _has_non_ascii(text):
    return any(ord(ch) > 127 for ch in text)


def _allocate(base, taken):
    """Return ``base`` or ``base-2``/``base-3``/... not present in ``taken``."""
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


class Command(BaseCommand):
    help = (
        "ONE-TIME: recompute slugs that lost non-Latin characters to Django "
        "slugify. Delete this command after running it on production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually rewrite slugs. Without it: dry run.",
        )
        parser.add_argument(
            "--slug",
            default=None,
            help="Only process the novel with this current slug.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max novels to examine (0 = all).",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.0,
            help="Seconds to sleep between processed novels.",
        )

    def handle(self, *args, **options):
        import time

        self.apply = options["apply"]
        self.limit = options["limit"]
        self.sleep = options["sleep"]

        taken = set(Novel.objects.values_list("slug", flat=True))
        taken.update(NovelAlias.objects.values_list("slug", flat=True))

        qs = Novel.objects.order_by("created_at", "pk")
        if options["slug"]:
            qs = qs.filter(slug=options["slug"])
        if self.limit:
            qs = qs[: self.limit]

        mode = "APPLY" if self.apply else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"=== {mode} ==="))

        examined = 0
        changed = 0
        unfixable = 0
        for novel in qs.iterator():
            examined += 1
            source = os.path.basename(novel.novel_path) if novel.novel_path else novel.title
            if not _has_non_ascii(source):
                continue

            target = slugify(source)
            if not target:
                unfixable += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"[UNFIXABLE] {novel.slug!r} folder={source!r} -> empty slug"
                    )
                )
                continue
            # Allocate against everything except this novel's own slug, so an
            # already-suffixed slug maps back to itself and a re-run is a no-op.
            target = _allocate(target, taken - {novel.slug})
            if target == novel.slug:
                continue

            changed += 1
            self.stdout.write(
                f"{novel.slug!r} -> {target!r}   ({novel.title!r} / {source!r})"
            )

            taken.add(target)
            if self.apply:
                self._rewrite(novel, target)
            if self.sleep:
                time.sleep(self.sleep)

        self.stdout.write("")
        self.stdout.write(
            f"Examined {examined} novels, {changed} to rewrite, {unfixable} unfixable."
        )
        if not self.apply and changed:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing changed. Re-run with --apply.")
            )
        self.stdout.write(self.style.ERROR("Remember: delete this command file after use."))

    def _rewrite(self, novel, target):
        with transaction.atomic():
            old_slug = novel.slug
            if old_slug and not NovelAlias.objects.filter(slug=old_slug).exists():
                NovelAlias.objects.create(slug=old_slug, novel=novel)
            Novel.objects.filter(pk=novel.pk).update(slug=target)

        self._audit({"novel_id": str(novel.pk), "old_slug": old_slug, "new_slug": target})

    def _audit(self, entry):
        path = os.path.join(
            settings.LNCRAWL_OUTPUT_PATH, ".slug_repair_audit.jsonl"
        )
        entry = {"ts": datetime.now().isoformat(), **entry}
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        except OSError as exc:
            logger.warning("Could not write slug audit log %s: %s", path, exc)
