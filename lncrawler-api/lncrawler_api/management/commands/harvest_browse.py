"""One browse scan: discover novels and record them as harvest candidates.

Runs in a short-lived subprocess spawned by ``run_harvest`` so lncrawl's memory
is released on exit. Each browse-capable source's ``browse_novels(offset, limit)``
is called concurrently and the results are upserted into ``HarvestCandidate``.

Usage:
  python manage.py harvest_browse [--offset 0] [--limit 50] [--workers 12]
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("lncrawler_api")

BULK_CHUNK = 1000


def _load_browse_crawlers():
    from ...services.downloader_service import _load_app

    _load_app()
    from lncrawl.core.sources import get_browse_crawlers
    from lncrawl.models import SearchResult

    return get_browse_crawlers(), SearchResult


def _normalize(results, search_result_cls):
    out = []
    for item in results or []:
        result = item if isinstance(item, search_result_cls) else search_result_cls(**item)
        if result.url:
            out.append({"title": result.title or "", "url": result.url})
    return out


def _harvest_one(crawler_type, offset, limit, timeout, normalize, search_result_cls, retries=1):
    last_error = None
    for attempt in range(retries + 1):
        crawler = None
        try:
            crawler = crawler_type()
            crawler.request_timeout = (timeout, timeout)
            crawler.initialize()
            results = normalize(crawler.browse_novels(offset=offset, limit=limit), search_result_cls)
            if results or attempt == retries:
                return crawler_type, results, None if results else last_error
        except Exception as e:  # noqa: BLE001 - report and keep going
            last_error = f"{type(e).__name__}: {e}"
            logger.debug(
                "browse_novels attempt %d failed on %s: %s",
                attempt + 1,
                crawler_type.__name__,
                e,
            )
        finally:
            if crawler is not None:
                try:
                    crawler.close()
                except Exception:
                    pass
    return crawler_type, [], last_error


def _create_candidates(found):
    """Upsert (source_name, title, url) tuples, skipping known library URLs."""
    from ...models import HarvestCandidate, NovelFromSource

    urls = list({url for _, _, url in found})
    existing_db_urls = set()
    existing_candidate_urls = set()
    for start in range(0, len(urls), BULK_CHUNK):
        chunk = urls[start:start + BULK_CHUNK]
        existing_db_urls.update(
            NovelFromSource.objects.filter(source_url__in=chunk).values_list("source_url", flat=True)
        )
        existing_candidate_urls.update(
            HarvestCandidate.objects.filter(novel_url__in=chunk).values_list("novel_url", flat=True)
        )

    known = existing_db_urls | existing_candidate_urls
    to_create = [
        HarvestCandidate(source_name=source_name, title=title, novel_url=url)
        for source_name, title, url in found
        if url not in known
    ]
    created = 0
    for start in range(0, len(to_create), BULK_CHUNK):
        batch = to_create[start:start + BULK_CHUNK]
        HarvestCandidate.objects.bulk_create(batch, ignore_conflicts=True)
        created += len(batch)
    return created


class Command(BaseCommand):
    help = "One browse scan: record newly discovered novels as harvest candidates."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--timeout", type=float, default=45.0)
        parser.add_argument("--workers", type=int, default=12)

    def handle(self, *args, **options):
        crawlers, search_result_cls = _load_browse_crawlers()
        self.stdout.write(f"Browsing {len(crawlers)} source(s)")

        found = []
        errors = 0
        with ThreadPoolExecutor(max_workers=options["workers"]) as executor:
            futures = {
                executor.submit(
                    _harvest_one,
                    crawler_type,
                    options["offset"],
                    options["limit"],
                    options["timeout"],
                    _normalize,
                    search_result_cls,
                ): crawler_type
                for crawler_type in crawlers
            }
            for future in as_completed(futures):
                crawler_type, results, error = future.result()
                if error:
                    errors += 1
                for entry in results:
                    found.append((crawler_type.source_name, entry["title"], entry["url"]))

        created = _create_candidates(found)
        with transaction.atomic():
            from ...models import HarvestConfig

            config = HarvestConfig.get_solo()
            config.last_harvest_at = timezone.now()
            config.save(update_fields=["last_harvest_at", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Harvest scan: {len(found)} novel(s) found across "
            f"{len({s for s, _, _ in found})} source(s), {created} new candidate(s), "
            f"{errors} source error(s)"
        ))
