"""JSON of the public audiobooks: the cards of the lists and home page, and the detail page.

Plain functions rather than DRF serializers: the payloads are assembled from several queries that the views
run once for a whole page.
"""
from django.conf import settings
from django.db.models import Q

from ..models import AudiobookChapter, Chapter
from ..services import audiobook_m4b, audiobook_media
from ..services.audiobook_public import LISTENABLE_PART_Q, chapter_audio_url, cover_urls

CAST_ROLE_ORDER = {'narrator': 0, 'main': 1, 'minor': 2}


def _iso(value):
    return value.isoformat() if value else None


def progress_dict(progress):
    """The viewer's progress on an audiobook, None when they have none."""
    if progress is None:
        return None
    chapter = progress.chapter
    return {
        'chapter_id': chapter.pk if chapter else None,
        'chapter_number': chapter.chapter_id if chapter else None,
        'chapter_title': chapter.title if chapter else None,
        'position_s': progress.position_s,
        'speed': progress.speed,
        'finished': progress.finished,
        'updated_at': _iso(progress.updated_at),
    }


def audiobook_card(audiobook, progress=None):
    """A list or home card. ``audiobook`` carries the ``annotate_public_totals`` annotations."""
    cover_url, cover_jpg_url = cover_urls(audiobook)
    last_part_at = audiobook.last_part_at
    return {
        'slug': audiobook.novel.slug,
        'language': audiobook.language,
        'title': audiobook.novel.title,
        'authors': sorted(author.name for author in audiobook.source.authors.all()),
        'cover_url': cover_url,
        'cover_jpg_url': cover_jpg_url,
        'duration_s': audiobook.public_duration_s,
        'parts': audiobook.public_parts,
        'chapters': audiobook.public_chapters,
        'first_published_at': _iso(audiobook.first_published_at),
        'last_part_at': _iso(last_part_at),
        'featured': audiobook.featured,
        'is_adult': audiobook.is_adult,
        'progress': progress_dict(progress),
    }


def _description(value):
    """The description of a cast member, stripped and capped; None when there is none."""
    if not isinstance(value, str):
        return None
    return value.strip()[:300] or None


def cast_list(cast):
    """The cast of an audiobook as a list, narrator first, then main, minor and the rest, by name.
    Entries that are not objects are ignored."""
    if not isinstance(cast, dict):
        return []
    entries = [
        {
            'name': name,
            'role': entry.get('role'),
            'engine': entry.get('engine'),
            'voice': entry.get('voice'),
            'gender': entry.get('gender'),
            'description': _description(entry.get('description')),
        }
        for name, entry in cast.items()
        if isinstance(entry, dict)
    ]
    entries.sort(key=lambda entry: (CAST_ROLE_ORDER.get(entry['role'], 3), entry['name']))
    return entries


def _part_downloads(part):
    return {
        fmt: {'cached': audiobook_m4b.cached_m4b(part, fmt, touch=False) is not None}
        for fmt in audiobook_m4b.FORMATS
    }


def _has_volumes(audiobook):
    """Whether the chapters of the source span more than one volume."""
    volumes = Chapter.objects.filter(novel_from_source_id=audiobook.source_id).order_by().values('volume').distinct()
    return len(volumes[:2]) > 1


def _volumes_by_part(audiobook, parts):
    """The volumes of each part (by part pk): its distinct volumes in chapter order, with the first title of each.
    A part's chapters are its frozen ``chapter_ids``, or its chapter range when they are missing. One query for all
    the parts."""
    if not parts:
        return {}
    pks = {pk for part in parts for pk in part.chapter_ids}
    ranged = [part for part in parts if not part.chapter_ids]
    query = Q(pk__in=pks)
    if ranged:
        query |= Q(
            chapter_id__gte=min(part.chapter_start for part in ranged),
            chapter_id__lte=max(part.chapter_end for part in ranged),
        )
    chapters = list(
        Chapter.objects.filter(query, novel_from_source_id=audiobook.source_id)
        .order_by('chapter_id').values_list('pk', 'chapter_id', 'volume', 'volume_title')
    )
    result = {}
    for part in parts:
        members = set(part.chapter_ids)
        volumes = {}
        for pk, number, volume, title in chapters:
            if pk in members if members else part.chapter_start <= number <= part.chapter_end:
                entry = volumes.setdefault(volume, {'number': volume, 'title': None})
                entry['title'] = entry['title'] or title or None
        result[part.pk] = list(volumes.values())
    return result


def audiobook_parts(audiobook):
    """Listenable parts (available) and the queued or claimed ones (in_production), by index. Failed parts and
    parts awaiting QA are left out. Two queries for the whole audiobook: the parts and their chapters, plus one for
    the volumes of the chapters in their range."""
    parts = list(
        audiobook.parts.filter(LISTENABLE_PART_Q | Q(status__in=['queued', 'claimed'])).order_by('index')
    )
    available_parts = [part for part in parts if part.is_listenable()]
    volumes_by_part = _volumes_by_part(audiobook, parts)
    chapters_by_part = {}
    rows = (
        AudiobookChapter.objects.filter(part__in=available_parts)
        .select_related('chapter', 'part')
        .order_by('part__index', 'chapter__chapter_id')
    )
    for row in rows:
        chapters_by_part.setdefault(row.part_id, []).append({
            'chapter_id': row.chapter_id,
            'number': row.chapter.chapter_id,
            'title': row.chapter.title,
            'audio_url': chapter_audio_url(row),
            'duration_s': row.duration_s,
            'offset_s': row.offset_s,
            'volume': row.chapter.volume,
            'volume_title': row.chapter.volume_title,
        })

    result = []
    for part in parts:
        available = part.is_listenable()
        result.append({
            'index': part.index,
            'state': 'available' if available else 'in_production',
            'chapter_start': part.chapter_start,
            'chapter_end': part.chapter_end,
            'word_count': part.word_count,
            'duration_s': part.duration_s,
            'estimated_duration_s': part.estimated_duration_s,
            'engine': part.engine if available else None,
            'size_bytes': part.size_bytes,
            'progress': None if available else part.progress,
            'downloads': _part_downloads(part) if available else None,
            'chapters': chapters_by_part.get(part.pk, []) if available else None,
            'volumes': volumes_by_part.get(part.pk, []),
        })
    return result


def audiobook_detail(audiobook, progress=None):
    """The detail page: the card, plus the synopsis, links, credits, feed, cast and parts."""
    narrator = audiobook_media.audiobook_metadata(audiobook)['narrator']
    return {
        **audiobook_card(audiobook, progress),
        'synopsis': audiobook.source.synopsis or '',
        'novel_slug': audiobook.novel.slug,
        'is_dmca': audiobook.novel.is_dmca,
        'source_slug': audiobook.source.source_slug,
        'credits': {'narrator': narrator, **(audiobook.credits or {})},
        'feed_url': f"{settings.SITE_API_URL}/audiobooks/{audiobook.novel.slug}/feed.xml?lang={audiobook.language}",
        'cast': cast_list(audiobook.cast),
        'parts': audiobook_parts(audiobook),
        'has_volumes': _has_volumes(audiobook),
    }
