"""Deleting a novel, and what happens to its novel when a source of it is deleted.

A novel always has a source: deleting its last one deletes the novel (``after_source_deleted``).
Every novel deletion goes through ``delete_novel``, which deletes the sources one by one (so each
source folder is handled by ``NovelFromSource.delete()``) and then removes the novel folder.

Folders are never removed inside the transaction: each is renamed aside (``.deleting-<uuid>``)
and only the renamed copy is removed once the deletion commits. Pass the ``files`` journal of
the surrounding operation when its transaction can roll back after the call returns, so the
renames are undone with it.
"""

import logging
import os
import time
from collections import namedtuple
from contextlib import nullcontext
from functools import partial

from django.conf import settings
from django.db import transaction

from ..models import Novel, NovelFromSource
from ..utils import lncrawler_paths
from ..utils.chapter_utils import SOURCE_LOCK_FILE
from .epub_service import CACHE_DIRNAME
from .folder_guard import locked_move
from .novel_naming import refresh_naming_by_id
from .novel_operations import file_journal

logger = logging.getLogger('lncrawler_api')

# What ``after_source_deleted`` returns when it deleted the novel: ``trash_path`` is where prune
# moved the novel folder (None when the folder was not moved).
NovelDeletion = namedtuple("NovelDeletion", "trash_path")

# A quarantined folder younger than this may belong to a deletion whose transaction is still open:
# a rollback renames it back. The sweep leaves it alone.
STALE_QUARANTINE_SECONDS = 24 * 3600


def _removable_novel_folder(folder, own_source_folders, novel_pk):
    """Absolute path of the novel folder ``folder`` when it may be removed, else None.

    It must lie strictly inside the library root, exist, be claimed by no other novel row
    (``novel_pk``, the novel being deleted, is not counted), and hold nothing but lock and cache
    leftovers, the source folders ``own_source_folders`` of that novel, and the ones already
    renamed aside. Filesystem errors are logged and mean None: the folder is kept on disk.
    """
    if not folder:
        return None
    try:
        base = os.path.realpath(settings.LNCRAWL_OUTPUT_PATH)
        target = os.path.realpath(os.path.join(base, folder))
        if not target.startswith(base + os.sep) or not os.path.isdir(target):
            return None
        if Novel.objects.filter(novel_path=folder).exclude(pk=novel_pk).exists():
            logger.warning("Novel folder '%s' is still claimed by another novel: kept on disk", folder)
            return None
        with os.scandir(target) as entries:
            for entry in entries:
                if entry.name in own_source_folders:
                    continue
                # A source of this novel already renamed aside by this deletion: removed on commit.
                if entry.name.startswith(lncrawler_paths.DELETING_PREFIX) and entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name == SOURCE_LOCK_FILE and entry.is_file(follow_symlinks=False):
                    continue
                if entry.name == CACHE_DIRNAME and entry.is_dir(follow_symlinks=False):
                    continue
                logger.warning("Novel folder '%s' holds more than leftovers: kept on disk", folder)
                return None
    except OSError:
        logger.exception("Could not inspect novel folder '%s': kept on disk", folder)
        return None
    return target


def delete_novel(novel, trash=None, files=None):
    """Delete ``novel`` with its sources, and remove its folder once the deletion commits.

    Holds the folder guard of the novel: ``FolderBusy`` propagates when a crawl or another move
    holds it, and nothing is deleted. Each source goes through ``NovelFromSource.delete()``, which
    renames its folder aside. The novel folder is renamed aside too when it holds only lock and
    cache leftovers (or its sources); otherwise it stays on disk for the unregistered-folder prune.

    ``trash`` (prune) is a callable ``trash(folder)`` that moves the novel folder into the prune
    trash, under ``files``; it is used only for a folder without sources, and its result (the
    trash path) is returned. Without ``trash`` the renamed folder is removed on commit.
    """
    with (nullcontext(files) if files is not None else file_journal()) as journal, locked_move(novel):
        novel.refresh_from_db(fields=["novel_path"])
        folder, novel_pk = novel.novel_path, novel.pk
        sources = list(NovelFromSource.objects.filter(novel_id=novel_pk).order_by("pk"))
        removable = _removable_novel_folder(folder, {s.source_folder for s in sources if s.source_folder}, novel_pk)
        for source in sources:
            source.delete(files=journal)
        novel.delete()
        if removable is None:
            return None
        if trash is not None:
            return trash(folder)
        quarantine = lncrawler_paths.new_quarantine_path()
        journal.move(removable, quarantine)
        transaction.on_commit(partial(lncrawler_paths.remove_quarantined, quarantine), robust=True)
        return None


def after_source_deleted(novel_id, trash=None, files=None):
    """Call after a source of ``novel_id`` was deleted.

    A novel with a source left gets its naming refreshed and None is returned. A novel left without
    sources is deleted with ``delete_novel``, and a ``NovelDeletion`` (with the trash path, for
    prune's audit) is returned. Raises ``FolderBusy`` when the novel cannot be locked now.
    """
    if NovelFromSource.objects.filter(novel_id=novel_id).exists():
        refresh_naming_by_id(novel_id)
        return None
    novel = Novel.objects.filter(pk=novel_id).first()
    if novel is None:
        return None
    return NovelDeletion(delete_novel(novel, trash=trash, files=files))


def sweep_stale_quarantine(now=None):
    """Remove the ``.deleting-*`` folders that a crash left behind, older than a day.

    They all sit at the library root. Only the entries named with the prefix are looked at. A folder counts as old when its last change (the later of
    mtime and ctime, the rename aside) is older than STALE_QUARANTINE_SECONDS. Returns the number
    removed. Errors are logged and the folder is kept.
    """
    cutoff = (time.time() if now is None else now) - STALE_QUARANTINE_SECONDS
    removed = 0
    try:
        with os.scandir(settings.LNCRAWL_OUTPUT_PATH) as top:
            for entry in top:
                if entry.name.startswith(lncrawler_paths.DELETING_PREFIX) and entry.is_dir(follow_symlinks=False):
                    removed += _remove_if_stale(entry.path, cutoff)
    except OSError:
        logger.exception("Could not scan the library root for quarantined folders")
    return removed


def _remove_if_stale(path, cutoff):
    try:
        stat = os.stat(path, follow_symlinks=False)
    except OSError:
        logger.exception("Could not inspect quarantined folder '%s'", path)
        return 0
    if max(stat.st_mtime, stat.st_ctime) > cutoff:
        return 0
    logger.info("Removing stale quarantined folder '%s'", path)
    lncrawler_paths.remove_quarantined(path)
    # remove_quarantined logs its own errors: the folder is counted only when it is gone.
    return 0 if os.path.lexists(path) else 1
