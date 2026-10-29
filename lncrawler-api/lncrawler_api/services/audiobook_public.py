"""What the public sees of the audiobooks: which ones a viewer may see, their totals over the listenable parts,
and the media URLs of their covers and chapters.

An audiobook is addressed by its novel's slug and a language. A part is listenable when it is done or stale and
passed QA or was approved (see ``AudiobookPart.is_listenable``).
"""
from datetime import timedelta

from django.db.models import BooleanField, Case, Count, Exists, F, FloatField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Audiobook, AudiobookChapter, AudiobookDailyStat, AudiobookPart, ListeningProgress
from ..models.sources_models import adult_novel_ids
from ..utils.media_utils import build_media_url
from ..utils.novel_resolution import resolve_novel_slug
from ..utils.query_helpers import adult_allowed
from . import audiobook_cover, audiobook_media

LISTENABLE_PART_Q = Q(status__in=['done', 'stale']) & (Q(qa_passed=True) | Q(approved=True))
POPULARITY_DAYS = 30  # trailing window of the plays and downloads counted for popularity


def adult_audiobook_q():
    """Q of the adult audiobooks: their source is adult, or their novel is (see ``adult_novel_ids``)."""
    return Q(source__is_adult=True) | Q(novel_id__in=adult_novel_ids())


def hides_adult_audiobooks(user):
    """Whether the viewer does not see adult audiobooks: only a logged-in viewer who chose ``show_r18`` 'no'.
    Guests and the viewers who allow adult content ('yes' or 'blur') see them; the frontend blurs the covers."""
    return user is not None and user.is_authenticated and not adult_allowed(user)


def visible_audiobooks(user=None, language=None, adult='viewer'):
    """Audiobooks the viewer may see: published, not retired, novel not DMCA'd, and at least one listenable part.
    ``adult`` is 'viewer' (the adult ones hidden only from logged-in viewers who chose 'no'), 'include', 'exclude'
    (no adult audiobook, for the SEO pages, sitemap and catalog feed) or 'only' (adult audiobooks alone).
    """
    audiobooks = (
        Audiobook.objects.filter(published=True, novel__is_dmca=False)
        .exclude(status='retired')
        .filter(Exists(AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=OuterRef('pk'))))
    )
    if adult == 'viewer':
        adult = 'exclude' if hides_adult_audiobooks(user) else 'include'
    if adult == 'exclude':
        audiobooks = audiobooks.exclude(adult_audiobook_q())
    elif adult == 'only':
        audiobooks = audiobooks.filter(adult_audiobook_q())
    if language:
        audiobooks = audiobooks.filter(language=language)
    return audiobooks.select_related('novel', 'source').prefetch_related('source__authors')


def _listenable_sum(field):
    """Sum of a part column over the listenable parts of the outer audiobook, as a correlated subquery."""
    return Subquery(
        AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=OuterRef('pk'))
        .order_by()
        .values('audiobook')
        .annotate(total=Sum(field))
        .values('total')[:1]
    )


def annotate_public_totals(queryset):
    """Annotate ``public_duration_s``, ``public_parts``, ``public_chapters`` and ``popularity``.

    The totals count listenable parts only. Each is its own subquery: joining the parts and the chapters in one
    aggregate would multiply the rows.
    """
    since = timezone.localdate() - timedelta(days=POPULARITY_DAYS - 1)
    popularity = Subquery(
        AudiobookDailyStat.objects.filter(audiobook=OuterRef('pk'), date__gte=since)
        .order_by()
        .values('audiobook')
        .annotate(total=Sum(F('plays') + F('downloads')))
        .values('total')[:1]
    )
    return queryset.annotate(
        public_duration_s=Coalesce(_listenable_sum('duration_s'), Value(0.0), output_field=FloatField()),
        public_parts=Coalesce(
            Subquery(
                AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=OuterRef('pk'))
                .order_by()
                .values('audiobook')
                .annotate(total=Count('id'))
                .values('total')[:1]
            ),
            Value(0),
        ),
        public_chapters=Coalesce(
            Subquery(
                AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=OuterRef('pk'))
                .order_by()
                .values('audiobook')
                .annotate(total=Count('chapters'))
                .values('total')[:1]
            ),
            Value(0),
        ),
        popularity=Coalesce(popularity, Value(0)),
        is_adult=Case(When(adult_audiobook_q(), then=Value(True)), default=Value(False), output_field=BooleanField()),
    )


def get_visible_audiobook_or_404(user, slug, language='en', adult='viewer'):
    """The visible audiobook of a novel in a language, with its public totals. 404 for an unknown novel, or an
    audiobook in that language the viewer may not see (``adult`` as in ``visible_audiobooks``). Follows novel
    merge aliases."""
    novel = resolve_novel_slug(slug)
    return get_object_or_404(
        annotate_public_totals(visible_audiobooks(user, language, adult)), novel=novel,
    )


def playable_audiobook_or_404(slug, language='en'):
    """The audiobook of a novel in a language that can be played, resumed or downloaded: published, not retired,
    with a listenable part. DMCA and adult only hide an audiobook from listings, so they do not apply here."""
    novel = resolve_novel_slug(slug)
    audiobooks = (
        Audiobook.objects.filter(published=True, language=language)
        .exclude(status='retired')
        .filter(Exists(AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=OuterRef('pk'))))
    )
    return get_object_or_404(audiobooks.select_related('novel', 'source'), novel=novel)


def progress_by_audiobook(user, audiobooks):
    """The viewer's ListeningProgress of each audiobook, in one query. Empty for anonymous viewers."""
    if user is None or not user.is_authenticated:
        return {}
    audiobook_ids = [audiobook.pk for audiobook in audiobooks]
    return {
        progress.audiobook_id: progress
        for progress in ListeningProgress.objects.filter(user=user, audiobook_id__in=audiobook_ids)
        .select_related('chapter')
    }


def audiobook_path(slug, language='en'):
    """Public path of an audiobook page, with ``?lang=`` when it is not English."""
    path = f"/audiobooks/{slug}/"
    return path if language == 'en' else f"{path}?lang={language}"


def narrator_credit(audiobook):
    """The narrator credit shown publicly: the stored credit when there is one, else the generated voices line."""
    credits = {'narrator': audiobook_media.audiobook_metadata(audiobook)['narrator'], **(audiobook.credits or {})}
    return credits['narrator']


def cover_urls(audiobook):
    """(600 px webp, 1400 px jpg) URLs of the cover, both None while no cover was built."""
    if not audiobook.cover_path:
        return None, None
    return (
        build_media_url(audiobook_cover.thumb_path(audiobook)),
        build_media_url(audiobook.cover_path),
    )


def chapter_audio_hidden(user, source):
    """Whether the audio of a chapter of ``source`` is hidden from the viewer: adult audio, for a logged-in viewer
    who chose 'no' (see ``hides_adult_audiobooks``). ``source`` is a NovelFromSource."""
    if not hides_adult_audiobooks(user):
        return False
    return source.is_adult or adult_novel_ids().filter(novel_id=source.novel_id).exists()


def chapter_audio_url(audio_chapter):
    """URL of the audio of a chapter inside a part. ``?g=`` carries the part generation, so a regenerated part
    busts the caches. ``audio_chapter`` is an AudiobookChapter with its part loaded."""
    return f"{build_media_url(audio_chapter.file_path)}?g={audio_chapter.part.generation}"


def chapter_has_audio_subquery():
    """Whether a chapter has public audio: an AudiobookChapter of it in a listenable part of a published, not
    retired audiobook. Correlated on the outer Chapter, for the chapter list."""
    return Exists(
        AudiobookChapter.objects.filter(
            chapter=OuterRef('pk'),
            part__in=AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook__published=True)
            .exclude(audiobook__status='retired'),
        )
    )


def listenable_chapter(audiobook, chapter_pk):
    """The AudiobookChapter of a chapter of a listenable part of this audiobook, or None."""
    return (
        AudiobookChapter.objects.select_related('part', 'chapter')
        .filter(
            part__audiobook=audiobook,
            part__in=AudiobookPart.objects.filter(LISTENABLE_PART_Q),
            chapter_id=chapter_pk,
        )
        .first()
    )
