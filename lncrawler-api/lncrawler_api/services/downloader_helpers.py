import os

from django.conf import settings

from ..utils import lncrawler_paths
from ..utils.title_signals import edition_label_from_title, same_work


def choose_crawl_output_path(source_host, title, edition="", source_url=""):
    """Absolute folder a new crawl of ``title`` from ``source_host`` writes into.

    A row already holding ``source_url`` keeps its recorded folder, even when
    that folder is missing on disk (the caller recreates it). Otherwise the
    default is ``<novel>/<site>``. A folder owned by another source row is reused
    only when that row names the same work and no row holds ``source_url``;
    otherwise the crawl gets a free ``<site> [..]`` folder in the same novel
    folder. ``edition`` is the crawled edition label; the title marker is used
    when it is empty. No folder is created here.
    """
    from ..models import NovelFromSource

    url_known = False
    if source_url:
        url_rows = NovelFromSource.objects.filter(source_url=source_url).order_by('pk')
        url_row = (
            url_rows.exclude(source_path__isnull=True).exclude(source_path='').first()
        )
        if url_row is not None:
            return os.path.join(settings.LNCRAWL_OUTPUT_PATH, url_row.source_path)
        url_known = url_rows.exists()

    default = lncrawler_paths.get_novel_output_path(
        source=source_host, novel=title, create=False
    )
    rel = os.path.relpath(default, settings.LNCRAWL_OUTPUT_PATH)
    owner = NovelFromSource.objects.filter(source_path=rel).order_by('pk').first()
    if owner is None or (
        not url_known and same_work(owner.title, owner.edition, title, edition)
    ):
        return default

    novel_abs = os.path.dirname(default)
    novel_rel = os.path.dirname(rel)
    taken = {
        os.path.basename(path)
        for path in NovelFromSource.objects.filter(
            source_path__startswith=novel_rel + os.sep
        ).values_list('source_path', flat=True)
        if os.path.dirname(path) == novel_rel
    }
    folder = lncrawler_paths.free_source_folder(
        novel_abs, os.path.basename(default), edition or edition_label_from_title(title), taken
    )
    return os.path.join(novel_abs, folder)


def _is_expected_crawler_error(exc) -> bool:
    """True for failures that are not bugs in our code: source-level
    ``LNException``s (novel unavailable: removed from the site, no downloads,
    bad URL) and transport errors (HTTP 5xx / network / IO) that exhausted their
    retries. Chapter-level failures are classified inside the crawler, so an
    exception reaching the download loop is either one of these or a real bug."""
    try:
        from lncrawl.core.exeptions import LNException, RetryErrorGroup
    except Exception:
        return False
    # An unsupported/disabled host is a user error, not a bug in our code.
    if isinstance(exc, ValueError) and "No crawler available for host" in str(exc):
        return True
    return isinstance(exc, (LNException, *RetryErrorGroup))


def _format_search_results(app):
    """Convert App.search_results into the shape stored on Job.search_results."""
    results = []
    for novel_index, novel in enumerate(app.search_results):
        sources = []
        for source_index, source in enumerate(novel.get("novels", [])):
            entry = {"index": source_index, "url": source.get("url", "")}
            if source.get("info"):
                entry["info"] = source["info"]
            sources.append(entry)
        results.append({
            "index": novel_index,
            "title": novel.get("title", ""),
            "sources": sources,
        })
    return results
