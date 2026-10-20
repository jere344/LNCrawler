"""Phase 3: dead sources superseded by a live sibling source."""

from urllib.parse import urlparse

from django.db.models import Count, Exists, OuterRef

from lncrawler_api.models import ExternalSource, NovelFromSource
from lncrawler_api.utils.crawler_path import ensure_crawler_on_path

from .common import logger, normalize_source_name


class DeadDuplicatesMixin:
    def _load_handled_sources(self):
        """Names and hosts served by an enabled crawler.

        Disabled crawlers (``is_disabled`` / ``disable_reason``, same test as
        ``crawler_registry.has_crawler``) are skipped entirely, so their sources
        count as dead. A host also served by an enabled crawler stays live.
        """
        handled = set()
        try:
            ensure_crawler_on_path()
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
