import os

from django.conf import settings

from ..utils import lncrawler_paths
from ..utils.title_signals import edition_label_from_title, same_work


# The editions of one work share a novel folder: a same-work check compares the work only.
_ANY_EDITION = "any"


def _folder_is_other_work(novel_rel, title):
    """Whether the novel folder ``novel_rel`` names a different work than ``title``.

    The novel is named by its canonical source. Only the work is compared, not the edition, so a
    "(WN)" and an "(LN)" source of one work still share a folder. A sequel title ("Dragon 2") does
    not match a novel named "Dragon", even when it was filed under the suffixed folder "dragon 2".
    """
    from ..models import Novel

    if not novel_rel:
        return False
    novel = (
        Novel.objects.filter(novel_path=novel_rel)
        .select_related('canonical_source')
        .order_by('pk')
        .first()
    )
    if novel is None or novel.canonical_source is None:
        return False
    return not same_work(novel.canonical_source.title, _ANY_EDITION, title, _ANY_EDITION)


def choose_crawl_output_path(source_host, title, edition="", source_url=""):
    """Absolute folder a new crawl of ``title`` from ``source_host`` writes into.

    A row already holding ``source_url`` keeps its recorded folder, even when
    that folder is missing on disk (the caller recreates it). Otherwise the
    default is ``<novel>/<site>``. When the default novel folder belongs to a
    different work, the crawl gets a free novel folder of its own. A folder
    owned by another source row is reused only when that row names the same
    work and no row holds ``source_url``; otherwise the crawl gets a free
    ``<site> [..]`` folder in the same novel folder. ``edition`` is the crawled
    edition label; the title marker is used when it is empty. No folder is
    created here.
    """
    from ..models import NovelFromSource

    url_known = False
    if source_url:
        url_rows = list(
            NovelFromSource.objects.filter(source_url=source_url).select_related('novel').order_by('pk')
        )
        url_row = next((row for row in url_rows if row.source_path), None)
        if url_row is not None:
            return os.path.join(settings.LNCRAWL_OUTPUT_PATH, url_row.source_path)
        url_known = bool(url_rows)

    default = lncrawler_paths.get_novel_output_path(
        source=source_host, novel=title
    )
    rel = os.path.relpath(default, settings.LNCRAWL_OUTPUT_PATH)
    novel_rel = os.path.dirname(rel)
    if not url_known and _folder_is_other_work(novel_rel, title):
        # A " 2" sibling folder of another work: the crawl starts a novel of its own. The folder is
        # created at once, so no other pick can take the name before the crawl writes into it.
        from .novel_naming import create_free_novel_folder

        return os.path.join(
            settings.LNCRAWL_OUTPUT_PATH, create_free_novel_folder(novel_rel), os.path.basename(default)
        )

    owner = NovelFromSource._folder_owner(rel)
    if owner is None or (
        not url_known and same_work(owner.title, owner.edition, title, edition)
    ):
        return default

    novel_abs = os.path.dirname(default)
    # The sources of the novel folder: their folder names are what is taken.
    taken = set(
        NovelFromSource.objects.filter(novel__novel_path=novel_rel, source_folder__isnull=False)
        .exclude(source_folder='')
        .values_list('source_folder', flat=True)
    )
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
            if source.get("cover"):
                entry["cover"] = source["cover"]
            sources.append(entry)
        results.append({
            "index": novel_index,
            "title": novel.get("title", ""),
            "sources": sources,
        })
    return results
