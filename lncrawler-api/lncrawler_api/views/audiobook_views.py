"""The public audiobook API: the list and the detail page, reading progress, plays, and the .m4b downloads.

An audiobook is addressed by its novel's slug and a language (``?lang=``, default 'en').

Only the reading position is throttled, per logged-in user. Plays and downloads are not limited. The detail, play,
progress and download do not apply the DMCA and adult rules: those only hide an audiobook from listings.
"""
import os
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotAuthenticated
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import SimpleRateThrottle

from ..models import Audiobook, AudiobookDailyStat, ListeningProgress
from ..serializers.audiobook_serializers import audiobook_card, audiobook_detail, progress_dict
from ..services import audiobook_m4b
from ..services.audiobook_feed import catalog_feed_xml, podcast_feed_xml
from ..services.audiobook_public import (
    LISTENABLE_PART_Q,
    annotate_public_totals,
    get_visible_audiobook_or_404,
    listenable_chapter,
    playable_audiobook_or_404,
    progress_by_audiobook,
    visible_audiobooks,
)
from ..services.reading_history import advance_reading_history
from ..utils.pagination import paginate
from ..utils.query_helpers import (
    _canonical_tag_names,
    filter_authors,
    filter_novel_ids,
    filter_tags,
    text_match_ids,
)
from .audiobook_worker_views import _flag, _number

LISTEN_SECONDS_MAX = 300  # longest listening time one play request may report
BUILD_RETRY_SECONDS = 5  # Retry-After while a .m4b is being built
PAGE_SIZE = 24
MAX_PAGE_SIZE = 50
CATALOG_ADULT_MODES = ('exclude', 'include', 'only')  # ?adult= of the catalog feed, exclude by default
SORTS = {
    'popular': ('-popularity', '-novel__rank_total_views', 'novel__title'),
    'new': (F('first_published_at').desc(nulls_last=True), 'novel__title'),
    'updated': (F('last_part_at').desc(nulls_last=True), 'novel__title'),
    'longest': ('-public_duration_s', 'novel__title'),
}


class AudiobookProgressThrottle(SimpleRateThrottle):
    """Rate limit of the reading position, per logged-in user: the endpoint requires one."""
    scope = 'audiobook_progress'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}


def _language(request):
    return request.GET.get('lang', 'en')


def _body_object(request):
    """The JSON body as a dict, or None when it is not an object."""
    data = request.data
    return data if isinstance(data, dict) else None


def _progress_of(user, audiobook):
    return ListeningProgress.objects.filter(user=user, audiobook=audiobook).select_related('chapter').first()


def _visible_languages(user, audiobooks=None):
    """The sorted distinct languages of the visible audiobooks (all of them when no queryset is given)."""
    audiobooks = visible_audiobooks(user, None) if audiobooks is None else audiobooks
    return list(audiobooks.order_by('language').values_list('language', flat=True).distinct())


@api_view(['GET'])
def list_audiobooks(request):
    """
    Visible audiobooks, paginated. ``sort`` is popular (default), new, updated or longest. ``q`` searches
    the novels as novel search does, with ``tag``, ``exclude_tag`` and ``author`` filters. ``listening=1``
    lists the authenticated viewer's unfinished audiobooks, most recently listened first.
    """
    user = request.user
    listening = request.GET.get('listening') == '1'
    if listening and not user.is_authenticated:
        raise NotAuthenticated()
    sort = request.GET.get('sort', 'popular')
    if sort not in SORTS:
        sort = 'popular'

    audiobooks = annotate_public_totals(visible_audiobooks(user, request.GET.get('lang') or None))
    query = request.GET.get('q', '').strip()
    if query:
        _nq, _title_ids, matching_ids = text_match_ids(query)
        audiobooks = filter_novel_ids(audiobooks, matching_ids, 'novel__')
    audiobooks = filter_tags(
        audiobooks,
        _canonical_tag_names(request.GET.getlist('tag', [])),
        _canonical_tag_names(request.GET.getlist('exclude_tag', [])),
        'novel__',
    )
    audiobooks = filter_authors(audiobooks, request.GET.getlist('author', []), 'novel__')
    if listening:
        audiobooks = audiobooks.filter(progress__user=user, progress__finished=False)
        audiobooks = audiobooks.order_by('-progress__updated_at', 'pk')
    else:
        audiobooks = audiobooks.order_by(*SORTS[sort], 'pk')

    paginator, page = paginate(request, audiobooks, PAGE_SIZE, MAX_PAGE_SIZE)
    page_audiobooks = list(page.object_list)
    progress = progress_by_audiobook(user, page_audiobooks)
    return Response({
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page.number,
        'catalog_feed_url': f"{settings.SITE_API_URL}/audiobooks/feed.xml",
        'languages': _visible_languages(user),
        'results': [audiobook_card(audiobook, progress.get(audiobook.pk)) for audiobook in page_audiobooks],
    })


@api_view(['GET'])
def audiobook_detail_by_slug(request, slug):
    """A playable audiobook with its parts, chapters, cast, credits and the viewer's progress. A DMCA or adult
    audiobook keeps its detail: those only hide it from listings."""
    audiobook = annotate_public_totals(
        Audiobook.objects.filter(pk=playable_audiobook_or_404(slug, _language(request)).pk)
        .select_related('novel', 'source').prefetch_related('source__authors'),
    ).get()
    progress = progress_by_audiobook(request.user, [audiobook]).get(audiobook.pk)
    detail = audiobook_detail(audiobook, progress)
    other = visible_audiobooks(request.user, None).filter(novel_id=audiobook.novel_id).exclude(pk=audiobook.pk)
    detail['other_languages'] = _visible_languages(request.user, other)
    return Response(detail)


def audiobook_feed(request, slug):
    """The podcast RSS feed of a visible audiobook. A plain Django view: the XML is not negotiated, and it is
    public, so it is never throttled or counted."""
    audiobook = get_visible_audiobook_or_404(None, slug, _language(request), adult='include')
    response = HttpResponse(podcast_feed_xml(audiobook), content_type='application/rss+xml; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def audiobook_catalog_feed(request):
    """
    The site-wide RSS feed of the newest audiobook parts. ``?adult=`` is exclude (default), include or only; any
    other value is exclude. Public, so it is never throttled or counted.
    """
    adult = request.GET.get('adult', 'exclude')
    if adult not in CATALOG_ADULT_MODES:
        adult = 'exclude'
    response = HttpResponse(catalog_feed_xml(adult), content_type='application/rss+xml; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


@api_view(['GET', 'PUT', 'POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AudiobookProgressThrottle])
def audiobook_progress(request, slug):
    """
    The viewer's listening position. PUT and POST (sent with keepalive on page hide) take
    ``{chapter_id, position_s, speed?, finished?}``: ``chapter_id`` is a chapter of a listenable part of this
    audiobook, ``position_s`` is clamped to the chapter, ``speed`` to 0.5..3. Reaching 90 % of a chapter moves
    the reading history of the novel forward to it.
    """
    audiobook = playable_audiobook_or_404(slug, _language(request))
    if request.method == 'GET':
        return Response({'progress': progress_dict(_progress_of(request.user, audiobook))})

    data = _body_object(request)
    if data is None:
        return Response({'detail': 'Expected a JSON object.'}, status=400)
    chapter_pk = data.get('chapter_id')
    if isinstance(chapter_pk, bool) or not isinstance(chapter_pk, int):
        return Response({'detail': 'chapter_id must be an integer.'}, status=400)
    audio = listenable_chapter(audiobook, chapter_pk)
    if audio is None:
        return Response({'detail': 'chapter_id is not a chapter of this audiobook.'}, status=400)
    position = _number(data.get('position_s'), None)
    if position is None or position < 0:
        return Response({'detail': 'position_s must be a number, 0 or more.'}, status=400)
    speed = None
    if data.get('speed') is not None:
        speed = _number(data['speed'], None)
        if speed is None:
            return Response({'detail': 'speed must be a number.'}, status=400)
        speed = min(max(speed, 0.5), 3.0)
    finished = _flag(data, 'finished', False)
    if finished is None:
        return Response({'detail': 'finished must be true or false.'}, status=400)

    position = min(position, audio.duration_s)
    fields = {'chapter': audio.chapter, 'position_s': position, 'finished': finished}
    if speed is not None:
        fields['speed'] = speed
    with transaction.atomic():
        progress, _created = ListeningProgress.objects.update_or_create(
            user=request.user, audiobook=audiobook, defaults=fields,
        )
        # Listening does not count words read: only the reading position moves.
        if finished or (audio.duration_s > 0 and position >= 0.9 * audio.duration_s):
            advance_reading_history(request.user, audiobook.novel, audiobook.source, audio.chapter)
    return Response({'progress': progress_dict(progress)})


@api_view(['POST'])
def audiobook_play(request, slug):
    """
    Count a listening session of a chapter: ``{chapter_id, listened_s?}``. Each call counts one play.
    ``listened_s`` (0 to 300) adds to the listening time.
    """
    audiobook = playable_audiobook_or_404(slug, _language(request))
    data = _body_object(request)
    if data is None:
        return Response({'detail': 'Expected a JSON object.'}, status=400)
    chapter_pk = data.get('chapter_id')
    if isinstance(chapter_pk, bool) or not isinstance(chapter_pk, int):
        return Response({'detail': 'chapter_id must be an integer.'}, status=400)
    audio = listenable_chapter(audiobook, chapter_pk)
    if audio is None:
        return Response({'detail': 'chapter_id is not a chapter of this audiobook.'}, status=400)
    listened = _number(data.get('listened_s'), 0)
    if listened is None:
        return Response({'detail': 'listened_s must be a number.'}, status=400)
    listened = min(max(listened, 0), LISTEN_SECONDS_MAX)

    AudiobookDailyStat.bump(audiobook.pk, plays=1, listen_seconds=round(listened))
    return Response(status=204)


M4B_ACCEL_PREFIX = '/_m4b/'  # internal nginx location, see nginx.conf.template


def _counts_as_download(request):
    """A request counts as a download unless it asks for a range that does not start the file: a player
    seeking through the file is not a new download."""
    range_header = request.META.get('HTTP_RANGE', '').strip()
    return not range_header or range_header.startswith('bytes=0-')


def _content_disposition(name):
    """An attachment name in UTF-8 (RFC 5987), with an ASCII fallback for old clients."""
    fallback = name.encode('ascii', 'replace').decode('ascii').replace('?', '_')
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


def _serve_m4b(request, part, path):
    """Behind nginx (it sends X-Real-IP) the file is served by nginx through X-Accel-Redirect, so no worker is
    held while it downloads. Otherwise Django serves it."""
    name = audiobook_m4b.download_filename(part)
    if request.META.get('HTTP_X_REAL_IP'):
        response = HttpResponse(content_type='audio/mp4')
        relative = os.path.relpath(path, settings.LNCRAWL_OUTPUT_PATH)
        # /_m4b/ is nginx's internal alias of the output folder: the cache is not reachable by a direct URL
        response['X-Accel-Redirect'] = f"{M4B_ACCEL_PREFIX}{quote(relative)}"
        response['Content-Disposition'] = _content_disposition(name)
        return response
    return FileResponse(
        open(path, 'rb'), as_attachment=True, filename=name, content_type='audio/mp4',
    )


class _FormatQueryIgnoringNegotiation(DefaultContentNegotiation):
    """The download reads ``?format=`` as the file format. DRF would take it as a renderer suffix and answer 404."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class AudiobookDownloadView(APIView):
    content_negotiation_class = _FormatQueryIgnoringNegotiation

    def get(self, request, slug, index):
        """
        The .m4b of a listenable part, ``?format=opus`` (default) or ``aac``. Served from the cache when built,
        counted as a download when the request counts. Otherwise a build is started, or the one already running is
        reported: 202 with Retry-After until the file is ready. ``?check=1`` answers 200 ``{status: 'ready'}`` when
        the file is cached, without serving or counting it; a missing file is handled as above.
        """
        audiobook = playable_audiobook_or_404(slug, _language(request))
        part = get_object_or_404(audiobook.parts.filter(LISTENABLE_PART_Q), index=index)
        fmt = request.GET.get('format', 'opus')
        if fmt not in audiobook_m4b.FORMATS:
            return Response({'detail': 'format must be opus or aac.'}, status=400)

        cached = audiobook_m4b.cached_m4b(part, fmt)
        if cached is not None and request.GET.get('check') == '1':
            return Response({'status': 'ready'})
        if cached is not None:
            # Only a request starting the file is counted, so a player seeking through it is not a new download
            if _counts_as_download(request):
                AudiobookDailyStat.bump(audiobook.pk, downloads=1)
            return _serve_m4b(request, part, cached)

        job = audiobook_m4b.active_m4b_job(part, fmt)
        if job is None:
            user = request.user if request.user.is_authenticated else None
            job = audiobook_m4b.enqueue_m4b_job(part, fmt, user=user)
        progress = min(job.progress / job.total_items, 1.0) if job.total_items else None
        response = Response({'status': 'building', 'progress': progress}, status=202)
        response['Retry-After'] = str(BUILD_RETRY_SECONDS)
        return response


audiobook_download = AudiobookDownloadView.as_view()
