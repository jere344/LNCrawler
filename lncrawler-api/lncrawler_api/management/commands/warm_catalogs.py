"""Warm the on-disk catalog caches of sources that define ``warm_catalog``.

A source whose catalog is built through ``cached_catalog`` takes minutes to build
cold. Running ``warm_catalog`` ahead of time (from the scheduler) means a user
search hits a warm cache. Sources are warmed one at a time on purpose: their
catalog fetches are polite, sequential requests.

Usage:
  python manage.py warm_catalogs [--source mvlempyr | --source www.mvlempyr.io]
"""

import logging
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("lncrawler_api")


def _load_warmable_crawlers(source_filter):
    from ...services.downloader_service import _load_app

    _load_app()
    from lncrawl.core.sources import load_sources

    selected = []
    for cls in load_sources():
        if cls.is_disabled or cls.disable_reason:
            continue
        if not callable(getattr(cls, "warm_catalog", None)):
            continue
        if source_filter and not _matches(cls, source_filter):
            continue
        selected.append(cls)
    return selected


def _matches(cls, name):
    name = name.lower()
    if cls.source_name.lower() == name:
        return True
    return any((urlparse(url).hostname or "") == name for url in cls.base_url)


class Command(BaseCommand):
    help = "Build or refresh the catalog caches of sources that define warm_catalog()."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=None,
            help="Only warm this source (source name or hostname)",
        )

    def handle(self, *args, **options):
        crawlers = _load_warmable_crawlers(options["source"])
        if not crawlers:
            self.stdout.write("No source to warm")
            return
        self.stdout.write(f"Warming {len(crawlers)} source(s)")

        failed = 0
        for crawler_type in crawlers:
            name = crawler_type.source_name
            crawler = None
            try:
                crawler = crawler_type()
                crawler.initialize()
                count = crawler.warm_catalog()
                logger.info("Catalog warmed for %s: %d entries", name, count)
                self.stdout.write(f"{name}: {count} entr(ies)")
            except Exception as e:  # noqa: BLE001 - report and keep going
                failed += 1
                logger.warning("Catalog warm failed for %s: %s", name, e)
                self.stdout.write(self.style.WARNING(f"{name}: failed ({type(e).__name__}: {e})"))
            finally:
                if crawler is not None:
                    try:
                        crawler.close()
                    except Exception:
                        pass

        total = len(crawlers)
        if failed == total and total > 0:
            raise CommandError(f"Catalog warm failed for all {total} source(s)")
        self.stdout.write(self.style.SUCCESS(
            f"Catalog warm: {total - failed} ok, {failed} failed"
        ))
