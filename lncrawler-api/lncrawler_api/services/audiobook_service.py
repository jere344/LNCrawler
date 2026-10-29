"""Audiobook parts: word counts, cutting whole chapters into parts, and the queue operations on them.

A part is a run of whole chapters of one source, cut by word count.
Chapter ranges are frozen when the part is created.
"""
import hashlib
import logging
import shutil
from datetime import timedelta
from functools import partial
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Sum
from django.utils import timezone

from ..models import Audiobook, AudiobookChapter, AudiobookPart, AudiobookWorker, Chapter
from ..models.sources_models import bulk_update_chunked
from ..utils import chapter_utils
from ..utils.crawler_path import ensure_crawler_on_path
from ..utils.query_helpers import preferred_source_key

ensure_crawler_on_path()
from lncrawl.utils.words import count_words  # noqa: E402

logger = logging.getLogger("lncrawler_api.audiobooks")

WORKER_LANGUAGE_DAYS = 7  # days since a worker's last ping or claim after which its languages are no longer announced
WORDS_PER_MINUTE = 155  # narration speed used to estimate a part's duration
MAX_ATTEMPTS = 3  # lease expiries before a part is failed
LEASE_SECONDS = 900  # how long a worker may hold a claimed part without renewing it
MAX_BITRATE_KBPS = 40  # encoded audio bitrate ceiling
TAIL_STABLE_DAYS = 14  # days without chapter updates before the last, short part of a finished source is cut

CUT_BATCH = 200


def _chapter_body(chapter):
    """Body text of a chapter, '' when the file has no body, None when the file is missing or unreadable."""
    parsed = chapter_utils.get_chapter(chapter.novel_from_source.absolute_source_path, chapter.chapter_id)
    if parsed is None:
        return None
    return parsed.get('body') or ''


def ensure_word_counts(chapters):
    """Count the words of the chapters that have content but no word count yet.

    A chapter whose file is missing or unreadable keeps word_count None, so it is counted later.
    Returns the number of chapter files read.
    """
    counted = []
    reads = 0
    for ch in chapters:
        if ch.word_count is not None or not ch.has_content:
            continue
        reads += 1
        body = _chapter_body(ch)
        if body is None:
            logger.debug("No readable file for chapter %s of source %s", ch.chapter_id, ch.novel_from_source_id)
            continue
        ch.word_count = count_words(body)
        counted.append(ch)
    bulk_update_chunked(counted, ['word_count'])
    return reads


def _counted_batches(source, last_id, counter):
    """The chapters with content after ``last_id`` in chapter order, in batches, each batch with its word counts
    stored. ``counter`` is an optional dict: its 'files_read' entry is increased by the chapter files read."""
    while True:
        batch = list(
            source.chapters.filter(has_content=True, chapter_id__gt=last_id)
            .select_related('novel_from_source')
            .order_by('chapter_id')[:CUT_BATCH]
        )
        if not batch:
            return
        last_id = batch[-1].chapter_id
        reads = ensure_word_counts(batch)
        if counter is not None:
            counter['files_read'] += reads
        yield batch


def store_word_counts(source, last_id=0, counter=None):
    """Store the word counts of the chapters a cut from ``last_id`` may take, up to the part target, without cutting.

    Meant to run before the cut's transaction, so the counts are kept even when no part is cut. Stops where the cut
    stops: at a chapter whose file is missing, or at the chapter that fills the target.
    """
    target = settings.AUDIOBOOK_PART_WORDS
    total = 0
    for batch in _counted_batches(source, last_id, counter):
        for ch in batch:
            if ch.word_count is None:
                return
            total += ch.word_count
            if total > target:
                return


def announced_languages():
    """Languages the workers seen in the last WORKER_LANGUAGE_DAYS announce they can narrate, sorted.
    Empty when no worker is seen, so no new audiobook is started."""
    since = timezone.now() - timedelta(days=WORKER_LANGUAGE_DAYS)
    languages = set()
    for worker_languages in AudiobookWorker.objects.filter(last_seen_at__gte=since).values_list('languages', flat=True):
        languages.update(worker_languages or [])
    return sorted(languages)


def pick_source(novel, language='en'):
    """The source the site shows for a novel in one language, or None when it has none in that language.

    Same choice as the site (preferred_source_key), so the audiobook is made from the version readers see.
    """
    chapters_with_content = Chapter.objects.filter(
        novel_from_source=OuterRef('pk'), has_content=True,
    ).values('novel_from_source').annotate(total=Count('*')).values('total')[:1]
    sources = list(
        novel.sources.filter(language=language)
        .annotate(annotated_available_chapters_count=Subquery(chapters_with_content))
    )
    if not sources:
        return None
    return min(sources, key=preferred_source_key)


def get_or_create_audiobook(novel, language='en', source=None):
    """Return (audiobook, created). Raises ValueError when the novel cannot have one in that language.

    ``source`` is the source to make the audiobook from; when not given, it is picked from the novel.
    """
    if novel.is_dmca:
        raise ValueError(f"{novel.title}: DMCA, no audiobook")
    audiobook = Audiobook.objects.filter(novel=novel, language=language).first()
    if audiobook is not None:
        return audiobook, False
    if source is None:
        source = pick_source(novel, language)
    if source is None:
        raise ValueError(f"{novel.title}: no {language} source")
    return Audiobook.objects.create(novel=novel, language=source.language, source=source), True


def _source_is_settled(source):
    """A completed source whose last chapter update is old enough to cut its tail."""
    if source.status != 'Completed':
        return False
    if source.last_chapter_update is None:
        return True
    return source.last_chapter_update < timezone.now() - timedelta(days=TAIL_STABLE_DAYS)


def cut_next_part(audiobook, allow_tail=False, counter=None):
    """Pick the next run of chapters for a part, or None when there is nothing to cut yet.

    ``counter`` is an optional dict: its 'files_read' entry is increased by the chapter files read.
    """
    source = audiobook.source
    last_part = audiobook.parts.order_by('-index').first()
    last_id = last_part.chapter_end if last_part else 0
    target = settings.AUDIOBOOK_PART_WORDS

    chosen = []
    total = 0
    full = False
    blocked = False
    for batch in _counted_batches(source, last_id, counter):
        for ch in batch:
            if ch.word_count is None:
                # Its file is missing for now: the run ends before it
                blocked = True
                break
            if ch.word_count == 0:
                continue
            # The first chapter is always taken, even when it is longer than the target
            if chosen and total + ch.word_count > target:
                full = True
                break
            chosen.append(ch)
            total += ch.word_count
        if full or blocked:
            break

    if not chosen:
        return None
    is_tail = not full and total < target
    if is_tail and not (allow_tail or _source_is_settled(source)):
        return None
    return {'chapters': chosen, 'word_count': total, 'is_tail': is_tail}


def content_hash(chapters):
    """sha256 of the chapter ids and bodies, to tell when a part's text has changed.

    None when the body of a chapter is unreadable: a missing file is never hashed as an empty one.
    """
    digest = hashlib.sha256()
    for ch in chapters:
        body = _chapter_body(ch)
        if body is None:
            return None
        digest.update(f"{ch.chapter_id}\n{body}\n".encode('utf-8'))
    return digest.hexdigest()


def part_chapters(part):
    """The Chapter rows of a part, in chapter_ids order. A chapter deleted since the cut is left out."""
    found = Chapter.objects.filter(pk__in=part.chapter_ids).select_related('novel_from_source').in_bulk()
    return [found[pk] for pk in part.chapter_ids if pk in found]


def enqueue_next_part(audiobook, priority=0, allow_tail=False, exclusive=False, counter=None):
    """Create the next queued part of an audiobook, or return None when nothing can be cut.

    With ``exclusive``, nothing is created while the audiobook already has a queued or claimed part.
    The check runs under the row lock, so two runs cannot both pass it.
    A cut with a chapter whose body cannot be read is not created either, and a warning is logged.
    The word counts are stored before the lock is taken, so the chapter files are not read under it.
    """
    current = Audiobook.objects.select_related('source').get(pk=audiobook.pk)
    last_part = current.parts.order_by('-index').first()
    store_word_counts(current.source, last_part.chapter_end if last_part else 0, counter)
    with transaction.atomic():
        audiobook = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
        if exclusive and audiobook.parts.filter(status__in=['queued', 'claimed']).exists():
            return None
        cut = cut_next_part(audiobook, allow_tail=allow_tail, counter=counter)
        if cut is None:
            return None
        last_part = audiobook.parts.order_by('-index').first()
        chapters = cut['chapters']
        digest = content_hash(chapters)
        if digest is None:
            logger.warning(
                "Part of %s not created: a chapter from %s to %s has no readable body",
                audiobook, chapters[0].chapter_id, chapters[-1].chapter_id,
            )
            return None
        now = timezone.now()
        part = AudiobookPart.objects.create(
            audiobook=audiobook,
            index=last_part.index + 1 if last_part else 1,
            chapter_start=chapters[0].chapter_id,
            chapter_end=chapters[-1].chapter_id,
            word_count=cut['word_count'],
            estimated_duration_s=cut['word_count'] / WORDS_PER_MINUTE * 60,
            priority=priority,
            content_hash=digest,
            chapter_ids=[ch.pk for ch in chapters],
        )
        audiobook.last_enqueued_at = now
        audiobook.save(update_fields=['last_enqueued_at', 'updated_at'])
        return part


def audio_dir(source):
    """Folder holding the audio files of a source."""
    return Path(source.absolute_source_path) / 'audio'


def is_inside_output_path(path):
    """True when ``path`` is strictly inside LNCRAWL_OUTPUT_PATH: the output root itself does not count."""
    output_root = Path(settings.LNCRAWL_OUTPUT_PATH).resolve()
    resolved = Path(path).resolve()
    return resolved != output_root and output_root in resolved.parents


def delete_audio_files(audiobook):
    """Delete the audio files of an audiobook and mark its done parts stale. Returns bytes freed.

    Only the audio folder of the source is removed, and only when the source folder is inside
    LNCRAWL_OUTPUT_PATH. Otherwise nothing is deleted and 0 is returned.
    The folder is removed on commit: when the surrounding transaction rolls back, the audio stays.
    """
    source = audiobook.source
    if not source.absolute_source_path:
        return 0
    if not is_inside_output_path(source.absolute_source_path):
        logger.warning(
            "Refusing to delete audio of %s: %s is not inside %s",
            audiobook, source.absolute_source_path, settings.LNCRAWL_OUTPUT_PATH,
        )
        return 0
    directory = audio_dir(source)
    freed = 0
    if directory.exists():
        freed = sum(f.stat().st_size for f in directory.rglob('*') if f.is_file())
        transaction.on_commit(partial(shutil.rmtree, directory))
    AudiobookChapter.objects.filter(part__audiobook=audiobook).delete()
    audiobook.parts.filter(status='done').update(status='stale', duration_s=0, size_bytes=0)
    audiobook.published = False
    audiobook.save(update_fields=['published', 'updated_at'])
    audiobook.refresh_totals()
    return freed


def _keep_key(audiobook):
    """Sort key of the audiobook to keep: longest, then most parts, then the oldest."""
    return (-audiobook.total_duration_s, -audiobook.parts_done, audiobook.created_at)


def follow_source(source):
    """Move the audiobooks of a source to the novel the source now belongs to. Returns how many moved.

    When the novel already has an audiobook in the same language, the longer one is kept
    (ties: more parts, then older). The other one loses its audio files, its parts and its
    listening progress; the progress is not carried over.
    """
    moved = 0
    with transaction.atomic():
        followers = list(
            Audiobook.objects.select_for_update()
            .filter(source=source)
            .exclude(novel_id=source.novel_id)
        )
        for audiobook in followers:
            existing = list(
                Audiobook.objects.select_for_update()
                .filter(novel_id=source.novel_id, language=audiobook.language)
            )
            if existing:
                winner = min([audiobook, existing[0]], key=_keep_key)
                loser = existing[0] if winner is audiobook else audiobook
                freed = delete_audio_files(loser)
                logger.warning(
                    "Audiobook %s deleted: source %s moved to novel %s, which already has %s (%s bytes freed)",
                    loser, source.pk, source.novel_id, winner, freed,
                )
                loser.delete()
                if winner is not audiobook:
                    continue
            audiobook.novel_id = source.novel_id
            audiobook.save(update_fields=['novel', 'updated_at'])
            moved += 1
            logger.info("Audiobook %s moved to novel %s with its source %s", audiobook, source.novel_id, source.pk)
    return moved


def _clear_claim(part):
    part.worker_id = ''
    part.claimed_at = None
    part.lease_until = None


def retry_part(part):
    """Put a failed part back in the queue with its attempts reset."""
    part.status = 'queued'
    part.attempts = 0
    part.error_message = ''
    _clear_claim(part)
    part.save()


def regenerate_part(part, priority=100):
    """Queue a finished, stale or failed part again. Its files stay until the new upload replaces them."""
    part.status = 'queued'
    part.priority = priority
    _clear_claim(part)
    part.attempts = 0
    part.qa_passed = None
    part.approved = False
    part.save()


def audio_disk_usage_bytes():
    """Total size of the audio files of all audiobooks."""
    return Audiobook.objects.aggregate(total=Sum('total_size_bytes'))['total'] or 0
