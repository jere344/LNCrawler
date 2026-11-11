from django.db.models import Avg, Count, Exists, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.expressions import RawSQL
from django.db.models.functions import JSONObject

from ..models import (
    Audiobook,
    AudiobookPart,
    Author,
    AuthorAlias,
    Chapter,
    Novel,
    NovelBookmark,
    NovelRating,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    Tag,
    WeeklySourceView,
)
from ..models.audiobook_models import LISTENABLE_PART_Q
from ..models.sources_models import NovelFromSource
from ..models.source_votes_models import SourceVote
from ..utils.author_names import normalize_author
from ..utils.search import matching_novel_ids, normalize_query

# Account setting values that let adult (R18) content through; 'blur' still
# shows it (the frontend blurs the covers), only 'no' hides it.
ADULT_ALLOWED_SETTINGS = ('yes', 'blur')


def adult_allowed(user):
    """Whether ``user`` may see adult novels. Anonymous visitors never can."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'show_r18', 'no') in ADULT_ALLOWED_SETTINGS


def public_novels(queryset):
    """Novels shown to everyone: not DMCA'd and not adult.

    Viewer-independent, so the SEO pages and sitemaps use it as is.
    """
    return queryset.filter(is_dmca=False, is_adult=False)


def public_sources(queryset):
    """Sources whose novel is public (see ``public_novels``)."""
    return queryset.filter(novel__is_dmca=False, novel__is_adult=False)


def exclude_adult(queryset, user=None, path=''):
    """Drop adult novels, unless the viewer may see them.

    ``Novel.is_adult`` is the stored rule (see refresh_novel_adult). ``path``
    reaches the novel from the queryset's model: ``'novel__'`` for sources,
    bookmarks and reviews, ``'to_novel__'`` for similarity rows.
    """
    if adult_allowed(user):
        return queryset
    return queryset.filter(**{f'{path}is_adult': False})


def most_viewed_novel_ids(user, limit, exclude_ids=(), novels=None):
    """Ids of the most viewed novels ``user`` may see (not DMCA'd, adult ones only when allowed), most viewed
    first (``rank_total_views``, then slug). ``novels`` narrows the candidates, ``exclude_ids`` drops ids."""
    candidates = Novel.objects.all() if novels is None else novels
    if exclude_ids:
        candidates = candidates.exclude(pk__in=exclude_ids)
    return list(
        exclude_adult(candidates.filter(is_dmca=False), user)
        .order_by('-rank_total_views', 'slug')
        .values_list('pk', flat=True)[:limit]
    )


def language_tier(source, languages=()):
    """0 when ``source`` is in ``languages`` (or no language is asked for), else 1."""
    return 0 if not languages or source.language in languages else 1


def source_rank_key(source, languages=()):
    """Rank a novel's sources the same everywhere: language tier, best vote score, then
    upvotes, then the most chapters with content, then title. Empty chapters
    never make a source look more complete than it reads."""
    return (
        language_tier(source, languages),
        -(source.upvotes - source.downvotes),
        -source.upvotes,
        -source.available_chapters_count,
        source.title or '',
    )


def rank_sources(sources, languages=()):
    """The best of ``sources`` by ``source_rank_key``, or None when there are none."""
    return min(sources, key=lambda source: source_rank_key(source, languages), default=None)


def _chapters_after_current():
    """Content chapters after a history row's current chapter, correlated on that row."""
    return Chapter.objects.filter(
        novel_from_source=OuterRef('source_id'),
        chapter_id__gt=OuterRef('current_chapter__chapter_id'),
        has_content=True,
    )


def unread_chapters_subquery():
    """Content chapters after a history row's current chapter, as a
    correlated subquery so listing histories costs one query, not one COUNT
    per row (see ``ReadingHistorySerializer.get_unread_chapters``)."""
    return Subquery(
        _chapters_after_current()
        .values('novel_from_source')
        .annotate(total=Count('*'))
        .values('total')[:1]
    )


# The DB columns behind ChapterSerializer's card fields (``has_audio`` is not one).
CHAPTER_CARD_COLUMNS = ('id', 'chapter_id', 'title', 'url', 'volume', 'volume_title', 'has_content')


def next_chapter_subquery():
    """The content chapter after a history row's current chapter, as one JSON object of the card columns.
    Correlated, so listing histories costs no per-row Chapter query (see
    ``ReadingHistorySerializer.get_resume``). The latest chapter is not here: it is the source's
    stored ``latest_available_chapter``."""
    chapters = _chapters_after_current().order_by('chapter_id')
    card = JSONObject(**{column: column for column in CHAPTER_CARD_COLUMNS})
    return Subquery(chapters.annotate(card=card).values('card')[:1])


def annotate_reading_history(queryset):
    """Annotate the history rows ``ReadingHistorySerializer`` reads, so a list of histories resolves its
    unread count and its resume chapter in one query each."""
    return queryset.annotate(
        annotated_unread_chapters=unread_chapters_subquery(),
        annotated_next_chapter=next_chapter_subquery(),
    )


def sources_total_views_subquery(languages=None):
    """Sum ``total_views`` over a novel's sources as a correlated subquery.

    Aggregating the ``sources`` relation directly duplicates each source row
    when the outer queryset already joins sources (tag/author/language
    filters), inflating the sum. Grouping over the source rows inside a
    subquery keeps the total correct regardless of the outer joins.
    """
    sources = NovelFromSource.objects.filter(novel=OuterRef('pk'))
    if languages:
        sources = sources.filter(language__in=languages)
    return Subquery(
        sources.values('novel')
        .annotate(total=Sum('total_views'))
        .values('total')[:1]
    )


def weekly_views_subquery(languages=None):
    """Sum the rolling-window daily views over a novel's sources.

    Same join-inflation guard as ``sources_total_views_subquery``; optionally
    restricted to the selected content languages.
    """
    views = WeeklySourceView.objects.filter(
        source__novel=OuterRef('pk'),
        granularity=WeeklySourceView.DAY,
        day__gte=WeeklySourceView.window_start(),
    )
    if languages:
        views = views.filter(source__language__in=languages)
    return Subquery(
        views.values('source__novel')
        .annotate(total=Sum('views'))
        .values('total')[:1]
    )


def avg_rating_subquery():
    """Mean star rating as a correlated subquery (NULL when unrated)."""
    return Subquery(
        NovelRating.objects.filter(novel=OuterRef('pk'))
        .values('novel')
        .annotate(avg=Avg('rating'))
        .values('avg')[:1]
    )


def rating_count_subquery():
    """Number of star ratings as a correlated subquery."""
    return Subquery(
        NovelRating.objects.filter(novel=OuterRef('pk'))
        .values('novel')
        .annotate(total=Count('*'))
        .values('total')[:1]
    )


def has_audiobook_subquery():
    """Whether the novel has a public audiobook: not retired, with a listenable part. Correlated, so
    the novel card reads it from its own row."""
    return Exists(
        Audiobook.objects.filter(novel=OuterRef('pk'))
        .exclude(status='retired')
        .filter(parts__in=AudiobookPart.objects.filter(LISTENABLE_PART_Q))
    )


# The NovelSourceSerializer profiles a source query can be shaped for.
SOURCE_PROFILES = ('card', 'library', 'preview', 'summary', 'detail')


def sources_queryset(profile='card', ip=None, user=None):
    """Sources with what the source serializer's ``profile`` reads (see
    ``NovelSourceSerializer.field_profiles``). Every profile joins the parent
    novel and the stored latest available chapter.

    ``card`` prefetches authors/tags, the list payload. ``detail`` adds the
    first available chapter, volumes, editors/translators and, when an ``ip``
    or ``user`` is given, the viewer's own vote and reading history, so detail
    views resolve the whole payload without a query per source. ``summary``
    prefetches no associations, defers the big text columns and, given ``ip``,
    the viewer's vote. ``library`` and ``preview`` prefetch no associations and
    skip the external source, which their payloads never read."""
    if profile not in SOURCE_PROFILES:
        raise ValueError(f"unknown source profile {profile!r}; expected one of {SOURCE_PROFILES}")
    detailed = profile == 'detail'
    associations = profile in ('card', 'detail')
    if not associations:
        prefetch = []
    else:
        # The tag payloads read only the name and is_adult; the embedding vector is never serialized, so it is
        # left out of the tag rows.
        tags = Prefetch('tags', queryset=Tag.objects.defer('embedding'))
        prefetch = (
            ['authors', 'editors', 'translators', tags, 'alternative_titles']
            if detailed
            else ['authors', tags]
        )
    related = ['novel', 'latest_available_chapter']
    if profile not in ('library', 'preview'):
        related.insert(0, 'external_source')
    qs = NovelFromSource.objects.select_related(*related).prefetch_related(*prefetch)
    if ip and profile in ('summary', 'detail'):
        # The summary and detail profiles report the viewer's own vote; prefetch it for the whole page so it
        # doesn't query once per source.
        qs = qs.prefetch_related(
            Prefetch(
                'votes',
                queryset=SourceVote.objects.filter(ip_address=ip),
                to_attr='user_votes',
            )
        )
    if not detailed:
        # Card/library payloads read only a handful of columns; defer the big
        # text/blob columns (the synopsis alone can be kilobytes per source) so
        # list pages don't transfer every source's full row.
        deferred = [
            'cover_url', 'cover_file', 'overview_picture_file', 'cover_phash',
            'novelupdates_url', 'original_publisher',
            'english_publisher', 'status', 'source_url',
            'synopsis',
        ]
        qs = qs.defer(*deferred)
        return qs

    qs = qs.select_related('first_available_chapter').prefetch_related('volumes')
    if user is not None and user.is_authenticated:
        # The reading position is per novel, whichever source it was saved from: prefetch the viewer's row
        # through the novel, so the source page shows it with any of the novel's sources.
        qs = qs.prefetch_related(
            Prefetch(
                'novel__reading_histories',
                queryset=reading_history_queryset(user, 'detail'),
                to_attr='user_novel_history',
            )
        )
    return qs


# The prefetch set of each novel payload, keyed by the NovelSerializer profile that reads it.
#   sources:   the NovelSourceSerializer profile of the nested sources (see sources_queryset)
#   counters:  the card aggregates (rating average and count, total and weekly views), annotated in SQL
#   audiobook: the has_audiobook flag, annotated in SQL, for the profiles whose fields include it
#   bookmarks: the viewer's own bookmark rows, when a user is given
#   history:   the ReadingHistorySerializer profile of the viewer's progress rows, when a user is given
NOVEL_PREFETCH_PROFILES = {
    # Cards on home, search and lists: authors/tags, counters, the viewer's bookmark and progress.
    'card': {'sources': 'card', 'counters': True, 'audiobook': True, 'bookmarks': True, 'history': 'detail'},
    # Library items: no authors/tags or counters. The view sets the bookmark state; progress is
    # passed only for the owner's private list.
    'library': {'sources': 'library', 'counters': False, 'audiobook': False, 'bookmarks': False, 'history': 'library'},
    # Reading-list thumbnails: the sources and the audiobook flag only.
    'preview': {'sources': 'preview', 'counters': False, 'audiobook': True, 'bookmarks': False, 'history': None},
    # Novel and source detail pages: nested source summaries, counters, bookmark and progress.
    'detail': {'sources': 'summary', 'counters': True, 'audiobook': False, 'bookmarks': True, 'history': 'detail'},
}


def reading_history_queryset(user, history_profile):
    """The viewer's history rows, shaped for ``ReadingHistorySerializer``'s ``history_profile``: 'detail'
    adds the novel. Both carry the source's name and latest chapter and the resume and unread counts."""
    histories = ReadingHistory.objects.filter(user=user).select_related(
        'source__latest_available_chapter', 'source__external_source', 'current_chapter',
    )
    if history_profile != 'library':
        histories = histories.select_related('novel')
    return annotate_reading_history(histories)


def novel_queryset(queryset=None, user=None, profile='card', ip=None, languages=None):
    """The novels ``NovelSerializer(profile=...)`` renders, with everything the profile reads resolved up front:
    the card counters and ``annotated_has_audiobook`` as SQL annotations, and the relations of
    ``NOVEL_PREFETCH_PROFILES[profile]`` prefetched. Pass the request user so bookmark and progress lookups are
    one query each, and ``languages`` (the same ones the serializer context carries) to scope the view counters.

    Each aggregate is its own correlated subquery, so joining the ratings and sources does not multiply rows.
    The ``card_*`` prefix keeps the serializer off the ordering-only ``avg_rating``/``total_views`` annotations,
    which mean something else.
    """
    flags = NOVEL_PREFETCH_PROFILES[profile]
    if queryset is None:
        queryset = Novel.objects.all()
    if flags['counters']:
        queryset = queryset.annotate(
            card_avg_rating=avg_rating_subquery(),
            card_rating_count=rating_count_subquery(),
            card_total_views=sources_total_views_subquery(languages),
            card_weekly_views=weekly_views_subquery(languages),
        )
    if flags['audiobook']:
        queryset = queryset.annotate(annotated_has_audiobook=has_audiobook_subquery())
    prefetches = [Prefetch('sources', queryset=sources_queryset(flags['sources'], ip=ip, user=user))]
    if user is not None and user.is_authenticated:
        if flags['bookmarks']:
            prefetches.append(Prefetch(
                'bookmarked_by_users',
                queryset=NovelBookmark.objects.filter(user=user),
                to_attr='user_bookmarks',
            ))
        if flags['history']:
            prefetches.append(Prefetch(
                'reading_histories',
                queryset=reading_history_queryset(user, flags['history']),
                to_attr='user_histories',
            ))
    return queryset.prefetch_related(*prefetches)


def reading_lists_queryset(user=None, full=True):
    """
    Reading lists with their relations prefetched so serializing a page does
    not issue per-list queries (owner, collaborators, items and their novels).

    ``full`` gives each item's novel the 'card' novel profile (sources, the card
    counters and, for a logged-in ``user``, their own bookmark and progress).
    List cards only render a title and a cover thumbnail, so they pass
    ``full=False`` to get the 'preview' profile (sources and the audiobook flag).

    Items are prefetched into ``visible_items`` with adult novels dropped when
    the viewer may not see them, so the serializer renders only visible items
    (counts, first_item, names) consistently.
    """
    items_qs = ReadingListItem.objects.all()
    items_qs = exclude_adult(items_qs, user, 'novel__')
    items_qs = items_qs.prefetch_related(
        Prefetch('novel', queryset=novel_queryset(user=user, profile='card' if full else 'preview'))
    )
    return ReadingList.objects.select_related('user').prefetch_related(
        'collaborators__user',
        Prefetch('items', queryset=items_qs, to_attr='visible_items'),
    )


def _canonical_tag_names(names):
    """Map requested tag names onto the canonical tag names they now resolve to.

    Old URLs can carry a merged-away or case/plural variant; the alias or key
    lookup finds the surviving tag. Unknown names are kept as typed.
    """
    canonical = []
    for name in names:
        tag = Tag.find(name) if name.strip() else None
        canonical.append(tag.name if tag is not None else name)
    return canonical


def _author_ids(names):
    """Ids of every author a requested name stands for.

    Matches the exact name, the normalized key, and merged-away aliases. Several
    authors can share one key before they are merged, so all of them count.
    Unknown names match nothing.
    """
    names = [name for name in names if normalize_author(name)]
    if not names:
        return set()
    keys = {normalize_author(name) for name in names}
    ids = set(
        Author.objects.filter(Q(name__in=names) | Q(normalized__in=keys)).values_list("pk", flat=True)
    )
    ids.update(
        AuthorAlias.objects.filter(normalized__in=keys, author__is_blocked=False)
        .values_list("author_id", flat=True)
    )
    return ids


def text_match_ids(query):
    """Ids of the novels a text query matches (title, alias or synopsis), with the title-only ids.

    Returns ``(normalized query, title_ids, all_ids)``. Authors are not searched.
    """
    nq = normalize_query(query) or query.upper()  # all-combining-marks query folds to ''
    title_ids, synopsis_ids = matching_novel_ids(nq, query)
    return nq, title_ids, list(set(title_ids) | set(synopsis_ids))


def filter_novel_ids(queryset, ids, path=''):
    """Keep the rows whose novel is one of ``ids``. ``path`` reaches the novel from the model."""
    return queryset.filter(**{f'{path}id__in': RawSQL("SELECT unnest(%s::uuid[])", [ids])})


def filter_tags(queryset, tags=(), exclude_tags=(), path=''):
    """Novels with any of ``tags`` and none of ``exclude_tags``. ``path`` reaches the novel from the model."""
    if tags:
        queryset = queryset.filter(**{f'{path}sources__tags__name__in': tags}).distinct()
    if exclude_tags:
        queryset = queryset.exclude(**{f'{path}sources__tags__name__in': exclude_tags}).distinct()
    return queryset


def filter_authors(queryset, authors, path=''):
    """Novels written by any of ``authors`` (names, see ``_author_ids``). ``path`` reaches the novel from the model."""
    if authors:
        queryset = queryset.filter(**{f'{path}sources__authors__in': _author_ids(authors)}).distinct()
    return queryset
