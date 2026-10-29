"""Scheduled audiobook tasks: topping up the part queue, reaping expired leases, and housekeeping.

Every public function returns a small summary dict for logging. AUDIOBOOK_ENABLED=false only stops the
enqueue: published audiobooks stay live, so leases are still reaped and housekeeping still runs.
"""
import logging
import shutil
import time
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, Max, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Audiobook, AudiobookChapter, AudiobookPart, Novel, NovelFromSource
from . import audiobook_cover, audiobook_m4b, audiobook_media, audiobook_service

logger = logging.getLogger("lncrawler_api.audiobooks")

GB = 1024 ** 3
QUEUED_STATUSES = ['queued', 'claimed']
SKIPPED_DISABLED = {'skipped': 'disabled'}
NEW_BOOK_READ_LIMIT = 2000  # chapter files read per run by the new-book slot, before it gives up for the run
NEW_BOOK_NOVEL_LIMIT = 500  # novels examined per run by the new-book slot, before it gives up for the run
NEVER = datetime(1, 1, 1, tzinfo=dt_timezone.utc)  # waited-since date when there is no audiobook yet
UPLOAD_LEFTOVER_AGE = 24 * 3600  # seconds after which a .part upload is taken for a leftover
GEN_DIR_MIN_AGE = 3600  # seconds a generation folder must have been untouched before it can be removed


class _NoPartCut(Exception):
    """A new audiobook has no part to cut yet, so its row is rolled back."""


def _queued_words():
    """Words of the parts that are queued or claimed: what the queue budget counts."""
    return AudiobookPart.objects.filter(status__in=QUEUED_STATUSES).aggregate(words=Sum('word_count'))['words'] or 0


def _budget_stop():
    """Why the enqueue run must stop now, or None when the budgets allow one more part."""
    if _queued_words() >= settings.AUDIOBOOK_QUEUE_WORDS:
        return 'queue_full'
    used = audiobook_service.audio_disk_usage_bytes()
    if used >= settings.AUDIOBOOK_DISK_BUDGET_GB * GB:
        logger.warning(
            "Audio disk budget reached: %.2f GB used of %s GB, no new parts enqueued",
            used / GB, settings.AUDIOBOOK_DISK_BUDGET_GB,
        )
        return 'disk_budget'
    return None


def _pair_views(novel_ref, language_ref):
    """Total views of the sources of a novel in one language, as a subquery over the two outer references."""
    return Subquery(
        NovelFromSource.objects.filter(novel=novel_ref, language=language_ref)
        .values('novel')
        .annotate(total=Sum('total_views'))
        .values('total')[:1]
    )


def _started_rows(languages):
    """Started books that can take a part now, as plain values: active, not DMCA, in one of the ``languages``,
    with at least one part and nothing queued or claimed. ``waited_since`` is the last time one of their parts
    was queued, and ``pair_views`` the popularity of their novel in their language."""
    queued = AudiobookPart.objects.filter(audiobook=OuterRef('pk'), status__in=QUEUED_STATUSES)
    return list(
        Audiobook.objects.filter(status='active', novel__is_dmca=False, language__in=languages)
        .filter(Exists(AudiobookPart.objects.filter(audiobook=OuterRef('pk'))))
        .filter(~Exists(queued))
        .annotate(
            waited_since=Coalesce('last_enqueued_at', 'created_at'),
            pair_views=Coalesce(_pair_views(OuterRef('novel'), OuterRef('language')), Value(0)),
        )
        .values('id', 'waited_since', 'pair_views')
    )


def _unstarted_pairs(languages):
    """(novel id, language, views) of the non-DMCA novels with a source in one of the languages and no audiobook
    in that language yet. A pair with an audiobook is skipped, so the other language of its novel can still start.
    Most popular first, then by novel id."""
    if not languages:
        return iter(())
    has_book = Audiobook.objects.filter(novel=OuterRef('novel'), language=OuterRef('language'))
    return (
        NovelFromSource.objects.filter(language__in=languages, novel__is_dmca=False)
        .filter(~Exists(has_book))
        .values('novel', 'language')
        .annotate(views=Sum('total_views'))
        .order_by(F('views').desc(nulls_last=True), 'novel')
        .values_list('novel', 'language', 'views')
        .iterator()
    )


def _started_key(row):
    """Round-robin order of a started book: waited longest first, then the more popular novel in its language."""
    return (
        row['waited_since'],
        0,
        -(row['pair_views'] or 0),
    )


def _start_book(novel, language, counter):
    """Create the audiobook of a novel in a language with its first part, all or nothing.

    Returns the audiobook, or None when no part can be cut yet, or when the book already exists
    (created concurrently, so it is not counted as a new one). ``counter`` gets the chapter files read.
    """
    source = audiobook_service.pick_source(novel, language)
    if source is None:
        return None
    # Stored before the transaction, so the counts stay when the rollback below drops the book
    audiobook_service.store_word_counts(source, counter=counter)
    try:
        with transaction.atomic():
            audiobook, created = audiobook_service.get_or_create_audiobook(novel, language, source=source)
            if not created:
                return None
            if audiobook_service.enqueue_next_part(audiobook, priority=0, exclusive=True, counter=counter) is None:
                raise _NoPartCut()
    except _NoPartCut:
        return None
    except IntegrityError:
        logger.warning("Audiobook of %s (%s) was created at the same time, skipped", novel.title, language)
        return None
    return audiobook


def _start_next_new_book(pairs, scan):
    """Start the most popular novel-language pair without an audiobook. None when the scan gives up.

    ``scan`` counts, across the whole run, the pairs examined and the chapter files read. The scan
    gives up once either reaches its limit, so short novels already counted only cost a query.
    """
    for novel_id, language, _views in pairs:
        if scan['novels'] >= NEW_BOOK_NOVEL_LIMIT or scan['files_read'] >= NEW_BOOK_READ_LIMIT:
            return None
        scan['novels'] += 1
        novel = Novel.objects.only('id', 'title', 'is_dmca').get(pk=novel_id)
        audiobook = _start_book(novel, language, scan)
        if audiobook is not None:
            return audiobook
    return None


def _round_robin():
    """Serve the participants in turn until a budget stops the run or none is eligible.

    Each step serves whoever has waited longest: a started book since its last part, the new-book
    slot since the newest audiobook was created. Ties go to the more popular novel in its language, and the new-book
    slot loses ties. A started book served here has a queued part now, so it is not picked again in this run.
    Returns (parts for started books, new books, stop reason).
    """
    languages = audiobook_service.announced_languages()
    books = _started_rows(languages)
    pairs = _unstarted_pairs(languages)
    scan = {'novels': 0, 'files_read': 0}
    slot_open = True
    slot_date = Audiobook.objects.aggregate(newest=Max('created_at'))['newest'] or NEVER
    started = new = 0
    while True:
        stopped = _budget_stop()
        if stopped:
            return started, new, stopped
        best = min(books, key=_started_key, default=None)
        slot_key = (slot_date, 1, 0, 0) if slot_open else None
        if best is None and slot_key is None:
            return started, new, None
        if slot_key is None or (best is not None and _started_key(best) < slot_key):
            books.remove(best)
            # enqueue_next_part reloads the audiobook under its lock, so the pk is enough here
            if audiobook_service.enqueue_next_part(Audiobook(pk=best['id']), priority=0, exclusive=True) is not None:
                started += 1
            continue
        audiobook = _start_next_new_book(pairs, scan)
        if audiobook is None:
            slot_open = False
            continue
        slot_date = audiobook.created_at
        new += 1


def enqueue_audiobooks():
    """Top the part queue up to AUDIOBOOK_QUEUE_WORDS, serving started books and new books in turn."""
    if not settings.AUDIOBOOK_ENABLED:
        return dict(SKIPPED_DISABLED)

    started, new, stopped = _round_robin()
    queued_words = _queued_words()
    disk_gb = audiobook_service.audio_disk_usage_bytes() / GB
    logger.info(
        "Audiobook enqueue: %s part(s) for started books, %s new book(s), %s queued words, %.2f GB audio, stopped: %s",
        started, new, queued_words, disk_gb, stopped,
    )
    return {
        'started_parts': started,
        'new_books': new,
        'queued_words': queued_words,
        'disk_gb': round(disk_gb, 2),
        'stopped': stopped,
    }


def reap_expired_leases():
    """Give back the parts whose worker stopped renewing its lease, or fail them after too many attempts."""
    now = timezone.now()
    requeued = failed = 0
    with transaction.atomic():
        expired = list(
            AudiobookPart.objects.select_for_update(skip_locked=True)
            .filter(status='claimed', lease_until__lt=now)
        )
        for part in expired:
            part.attempts += 1
            part.worker_id = ''
            part.claimed_at = None
            part.lease_until = None
            part.progress = 0
            part.stage = ''
            if part.attempts >= audiobook_service.MAX_ATTEMPTS:
                part.status = 'failed'
                part.error_message = 'Lease expired: the worker stopped responding'
                failed += 1
            else:
                part.status = 'queued'
                requeued += 1
            part.save()
    if expired:
        logger.info("Audiobook leases reaped: %s requeued, %s failed", requeued, failed)
    return {'requeued': requeued, 'failed': failed}


def _follow_moved_sources(counts):
    """Safety net: audiobooks whose source now sits in another novel follow that source."""
    moved = Audiobook.objects.exclude(source__novel_id=F('novel_id')).select_related('source')
    for source in {audiobook.source.pk: audiobook.source for audiobook in moved}.values():
        counts['followed'] += audiobook_service.follow_source(source)


def _mark_stale_parts(counts):
    """Mark done parts stale when their source was re-imported and their text changed.

    A part is checked once per re-import: ``checked_at`` records the check, so a source that has not
    changed since is not read again. A part with an unreadable chapter file is left as it is, and
    checked again on the next run.
    """
    due = (
        AudiobookPart.objects.filter(
            status='done',
            completed_at__isnull=False,
            audiobook__source__last_chapter_update__gt=Coalesce(F('checked_at'), F('completed_at')),
        )
        .exclude(audiobook__status='retired')
        .select_related('audiobook__source')
    )
    for part in due:
        checked_at = timezone.now()
        chapters = audiobook_service.part_chapters(part)
        # A chapter that was deleted from the source makes the part stale without reading any text
        changed = len(chapters) != len(part.chapter_ids)
        if not changed:
            digest = audiobook_service.content_hash(chapters)
            if digest is None:
                continue
            changed = digest != part.content_hash
        if changed:
            part.status = 'stale'
            counts['stale'] += 1
        part.checked_at = checked_at
        part.save(update_fields=['status', 'checked_at'])


def _live_generations(audiobook):
    """(part folder, generation folder) names to keep: the ones the chapter files point to, and the claimed parts'."""
    keep = {
        (Path(file_path).parts[-3], Path(file_path).parts[-2])
        for file_path in AudiobookChapter.objects.filter(part__audiobook=audiobook).values_list('file_path', flat=True)
    }
    keep |= {
        (f'part-{index:03}', f'g{generation}')
        for index, generation in audiobook.parts.filter(status='claimed').values_list('index', 'generation')
    }
    return keep


def _remove_orphan_generation(audiobook, part_dir, gen_dir, counts):
    """Remove a generation folder that no chapter file and no claim uses. The folder must be untouched for
    GEN_DIR_MIN_AGE seconds, and the part is checked again under its row lock, since a claim may have just
    started or a complete may have just stored its files."""
    if time.time() - gen_dir.stat().st_mtime < GEN_DIR_MIN_AGE:
        return
    try:
        index = int(part_dir.name[len('part-'):])
        generation = int(gen_dir.name[len('g'):])
    except ValueError:
        return
    with transaction.atomic():
        claimed = (
            AudiobookPart.objects.select_for_update(of=('self',))
            .filter(audiobook=audiobook, index=index, status='claimed', generation=generation)
            .first()
        )
        referenced = AudiobookChapter.objects.filter(
            part__audiobook=audiobook, file_path__contains=f'{part_dir.name}/{gen_dir.name}/',
        ).exists()
        if claimed or referenced:
            return
        counts['leftovers'] += sum(1 for entry in gen_dir.rglob('*') if entry.is_file())
        shutil.rmtree(gen_dir)


def _clean_upload_leftovers(audiobook, counts):
    """Delete the leftovers of worker uploads under audio/part-*/: old .part files, and old generation folders
    that neither the chapter files nor a claimed part point to."""
    audio = audiobook_service.audio_dir(audiobook.source)
    keep = _live_generations(audiobook)
    cutoff = time.time() - UPLOAD_LEFTOVER_AGE
    for part_dir in audio.glob('part-*'):
        if not part_dir.is_dir():
            continue
        for gen_dir in part_dir.glob('g*'):
            if not gen_dir.is_dir():
                continue
            if (part_dir.name, gen_dir.name) in keep:
                for leftover in gen_dir.glob('*.part'):
                    if leftover.stat().st_mtime < cutoff:
                        leftover.unlink()
                        counts['leftovers'] += 1
            else:
                _remove_orphan_generation(audiobook, part_dir, gen_dir, counts)


def _refresh_media(audiobook, counts):
    """Retag the chapter files when the tags hash changed, and rebuild the cover when it is stale."""
    if not AudiobookChapter.objects.filter(part__audiobook=audiobook).exists():
        return
    try:
        with audiobook_media.retag_lock(audiobook):
            if audiobook_media.compute_tags_hash(audiobook) != audiobook.tags_hash:
                audiobook_media.retag_audiobook(audiobook)
                counts['retagged'] += 1
    except Exception:
        logger.exception("Could not retag audiobook %s", audiobook.pk)
    if audiobook.parts.filter(status='done').exists() and audiobook_cover.cover_is_stale(audiobook):
        try:
            audiobook_cover.build_cover(audiobook)
            counts['covers'] += 1
        except Exception:
            logger.exception("Could not build the cover of audiobook %s", audiobook.pk)


def audiobook_housekeeping():
    """Daily checks: audiobooks follow their moved sources, parts whose text changed are flagged stale,
    leftovers of worker uploads are removed, files are retagged and covers rebuilt when needed, and the
    .m4b cache is pruned."""
    counts = {'followed': 0, 'stale': 0, 'leftovers': 0, 'retagged': 0, 'covers': 0}
    _follow_moved_sources(counts)
    _mark_stale_parts(counts)
    for audiobook in Audiobook.objects.select_related('source', 'novel'):
        # Only the audio folder of each audiobook's own source is walked, never the library
        source_path = audiobook.source.absolute_source_path
        if source_path and audiobook_service.is_inside_output_path(source_path):
            if audiobook_service.audio_dir(audiobook.source).is_dir():
                _clean_upload_leftovers(audiobook, counts)
        _refresh_media(audiobook, counts)
    try:
        counts['prune'] = audiobook_m4b.prune_m4b_cache()
    except Exception:
        logger.exception("Could not prune the .m4b cache")
    logger.info("Audiobook housekeeping: %s", counts)
    return counts
