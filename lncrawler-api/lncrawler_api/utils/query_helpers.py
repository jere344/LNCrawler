from django.db.models import Avg, Count, Exists, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.expressions import RawSQL
from django.db.models.functions import JSONObject

from ..models import (
    Audiobook,
    AudiobookPart,
    Author,
    AuthorAlias,
    Chapter,
    NovelBookmark,
    NovelRating,
    ReadingHistory,
    Tag,
    WeeklySourceView,
)
from ..models.sources_models import NovelFromSource, adult_novel_ids
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
    return queryset.filter(is_dmca=False).exclude(pk__in=adult_novel_ids())


def public_sources(queryset):
    """Sources whose novel is public (see ``public_novels``)."""
    return queryset.filter(novel__is_dmca=False).exclude(novel_id__in=adult_novel_ids())


def exclude_adult(queryset, user=None, path=''):
    """Drop adult novels, unless the viewer may see them.

    A novel is adult when more than half of its sources are. ``path``
    reaches the novel from the queryset's model: ``'novel__'`` for sources,
    bookmarks and reviews, ``'to_novel__'`` for similarity rows.
    """
    if adult_allowed(user):
        return queryset
    return queryset.exclude(**{f'{path}pk__in': adult_novel_ids()})


def preferred_source_key(source):
    """Rank a novel's sources the same everywhere: best vote score, then
    upvotes, then the most chapters with content, then title. Empty chapters
    never make a source look more complete than it reads."""
    return (
        -(source.upvotes - source.downvotes),
        -source.upvotes,
        -source.available_chapters_count,
        source.title or '',
    )


def unread_chapters_subquery():
    """Content chapters after a history row's last-read chapter, as a
    correlated subquery so listing histories costs one query, not one COUNT
    per row (see ``ReadingHistorySerializer.get_unread_chapters``)."""
    return Subquery(
        Chapter.objects.filter(
            novel_from_source=OuterRef('source_id'),
            chapter_id__gt=OuterRef('last_read_chapter__chapter_id'),
            has_content=True,
        )
        .values('novel_from_source')
        .annotate(total=Count('*'))
        .values('total')[:1]
    )


# The DB columns behind ChapterSerializer's card fields (``has_audio`` is not one).
CHAPTER_CARD_COLUMNS = ('id', 'chapter_id', 'title', 'url', 'volume', 'volume_title', 'has_content')


def next_chapter_subquery():
    """The content chapter after a history row's last-read chapter, as one JSON object of the card columns.
    Correlated, so listing histories costs no per-row Chapter query (see
    ``ReadingHistorySerializer.get_next_chapter``). The latest chapter is not here: it is the source's
    stored ``latest_available_chapter``."""
    chapters = Chapter.objects.filter(
        novel_from_source=OuterRef('source_id'),
        chapter_id__gt=OuterRef('last_read_chapter__chapter_id'),
        has_content=True,
    ).order_by('chapter_id')
    card = JSONObject(**{column: column for column in CHAPTER_CARD_COLUMNS})
    return Subquery(chapters.annotate(card=card).values('card')[:1])


def annotate_reading_history(queryset, next_chapter=True):
    """Annotate the history rows ``ReadingHistorySerializer`` reads, so a list of histories resolves its
    unread count (and, unless ``next_chapter=False``, its next chapter) in one query each."""
    annotations = {'annotated_unread_chapters': unread_chapters_subquery()}
    if next_chapter:
        annotations['annotated_next_chapter'] = next_chapter_subquery()
    return queryset.annotate(**annotations)


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
    """Whether the novel has a public audiobook: published, not retired, with a listenable part. Correlated, so
    the novel card reads it from its own row."""
    # Imported here: services.audiobook_public imports this module.
    from ..services.audiobook_public import LISTENABLE_PART_Q

    return Exists(
        Audiobook.objects.filter(novel=OuterRef('pk'), published=True)
        .exclude(status='retired')
        .filter(parts__in=AudiobookPart.objects.filter(LISTENABLE_PART_Q))
    )


def annotate_card_aggregates(queryset, languages=None):
    """Annotate the four counters a novel card renders (avg/count rating and
    total/weekly views) as correlated subqueries, and ``annotated_has_audiobook``
    (see ``has_audiobook_subquery``).

    A direct ``Avg('ratings')`` + ``Sum('sources')`` in one queryset would join
    both relations and multiply the rows, so each aggregate lives in its own
    subquery. Use together with ``apply_novel_prefetches(card_aggregates=True)``
    to drop the matching prefetches; the serializer then reads the annotations
    instead of recomputing them from prefetched rows.

    The names are deliberately ``card_*``-prefixed: ordering-only annotations
    elsewhere reuse plain ``avg_rating``/``total_views`` with different
    semantics (coalesced to 0, and not language-scoped), so the serializer must
    not pick those up.
    """
    return queryset.annotate(
        card_avg_rating=avg_rating_subquery(),
        card_rating_count=rating_count_subquery(),
        card_total_views=sources_total_views_subquery(languages),
        card_weekly_views=weekly_views_subquery(languages),
        annotated_has_audiobook=has_audiobook_subquery(),
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
        prefetch = (
            ['authors', 'editors', 'translators', 'tags', 'alternative_titles']
            if detailed
            else ['authors', 'tags']
        )
    related = ['novel', 'latest_available_chapter']
    if profile not in ('library', 'preview'):
        related.insert(0, 'external_source')
    qs = (
        NovelFromSource.objects.select_related(*related)
        .prefetch_related(*prefetch)
        .annotate(
            # Novel-level adult flag: a novel is adult if more than half of its
            # sources are, so source cards blur when the *novel* is adult.
            # Correlated, so it reads only this novel's sources (novel_id index).
            novel_is_adult=Exists(adult_novel_ids().filter(novel_id=OuterRef('novel_id'))),
        )
    )
    if not detailed:
        # Card/library payloads read only a handful of columns; defer the big
        # text/blob columns (the synopsis alone can be kilobytes per source) so
        # list pages don't transfer every source's full row.
        deferred = [
            'cover_url', 'cover_path', 'overview_picture_path', 'cover_phash',
            'meta_file_path', 'novelupdates_url', 'original_publisher',
            'english_publisher', 'status', 'source_path', 'source_url',
            'synopsis',
        ]
        qs = qs.defer(*deferred)
        if profile == 'summary' and ip:
            # The summary profile reports the viewer's own vote; prefetch it for
            # the whole page so it doesn't query once per source.
            qs = qs.prefetch_related(
                Prefetch(
                    'votes',
                    queryset=SourceVote.objects.filter(ip_address=ip),
                    to_attr='user_votes',
                )
            )
        return qs

    qs = qs.select_related('first_available_chapter').prefetch_related('volumes')
    if ip:
        qs = qs.prefetch_related(
            Prefetch(
                'votes',
                queryset=SourceVote.objects.filter(ip_address=ip),
                to_attr='user_votes',
            )
        )
    if user is not None and user.is_authenticated:
        qs = qs.prefetch_related(
            Prefetch(
                'read_by_users',
                queryset=ReadingHistory.objects.filter(user=user),
                to_attr='user_read_history',
            )
        )
    return qs


def source_prefetch(prefix='', profile='card', ip=None, user=None):
    """Prefetch a novel's sources (see `sources_queryset`)."""
    return Prefetch(
        prefix + 'sources',
        queryset=sources_queryset(profile, ip=ip, user=user),
    )


def weekly_views_prefetch(prefix=''):
    """Only the daily buckets inside the current window are ever summed."""
    return Prefetch(
        prefix + 'sources__weekly_views',
        queryset=WeeklySourceView.objects.filter(
            granularity=WeeklySourceView.DAY,
            day__gte=WeeklySourceView.window_start(),
        ),
    )


# The prefetch set of each novel payload, keyed by the NovelSerializer profile that reads it.
#   sources:   the NovelSourceSerializer profile of the nested sources (see sources_queryset)
#   counters:  rating and weekly-view prefetches (the card aggregates)
#   bookmarks: the viewer's own bookmark rows, when a user is given
#   history:   the ReadingHistorySerializer profile of the viewer's progress rows, when a user is given
NOVEL_PREFETCH_PROFILES = {
    # Cards on home, search and lists: authors/tags, counters, the viewer's bookmark and progress.
    'card': {'sources': 'card', 'counters': True, 'bookmarks': True, 'history': 'detail'},
    # Library items: no authors/tags or counters. The view sets the bookmark state; progress is
    # passed only for the owner's private list.
    'library': {'sources': 'library', 'counters': False, 'bookmarks': False, 'history': 'library'},
    # Reading-list thumbnails: the sources only.
    'preview': {'sources': 'preview', 'counters': False, 'bookmarks': False, 'history': None},
    # Novel and source detail pages: nested source summaries, counters, bookmark and progress.
    'detail': {'sources': 'summary', 'counters': True, 'bookmarks': True, 'history': 'detail'},
}


def novel_prefetch_objects(user=None, prefix='', profile='card', ip=None, card_aggregates=False):
    """The prefetch list for a novel queryset, optionally addressed through a
    relation (e.g. prefix='to_novel__' for NovelSimilarity rows). ``profile``
    picks the set from ``NOVEL_PREFETCH_PROFILES``.

    ``card_aggregates`` drops the ratings/weekly-views prefetches because the
    queryset already carries the matching annotations
    (``annotate_card_aggregates``); only set it when that is true, otherwise the
    serializer falls back to a query per novel.
    """
    flags = NOVEL_PREFETCH_PROFILES[profile]
    prefetches = [source_prefetch(prefix, profile=flags['sources'], ip=ip, user=user)]
    if flags['counters'] and not card_aggregates:
        prefetches += [
            prefix + 'ratings',
            weekly_views_prefetch(prefix),
        ]
    if user is not None and user.is_authenticated:
        if flags['bookmarks']:
            prefetches.append(Prefetch(
                prefix + 'bookmarked_by_users',
                queryset=NovelBookmark.objects.filter(user=user),
                to_attr='user_bookmarks',
            ))
        if flags['history']:
            prefetches.append(Prefetch(
                prefix + 'reading_histories',
                queryset=reading_history_queryset(user, flags['history']),
                to_attr='user_histories',
            ))
    return prefetches


def reading_history_queryset(user, history_profile):
    """The viewer's history rows, shaped for ``ReadingHistorySerializer``'s ``history_profile``: 'detail'
    adds the novel and the next chapter, 'library' reads neither."""
    histories = ReadingHistory.objects.filter(user=user).select_related(
        'source__latest_available_chapter', 'last_read_chapter',
    )
    if history_profile == 'library':
        return annotate_reading_history(histories, next_chapter=False)
    return annotate_reading_history(histories.select_related('novel'))


def apply_novel_prefetches(queryset, user=None, profile='card', ip=None, card_aggregates=False):
    """Attach the relations the novel serializers read for ``profile`` (see
    ``NOVEL_PREFETCH_PROFILES``). Pass the request user so per-user bookmark and
    progress lookups are collapsed into one query each; ``card_aggregates`` is
    passed through to ``novel_prefetch_objects``."""
    return queryset.prefetch_related(
        *novel_prefetch_objects(
            user, profile=profile, ip=ip, card_aggregates=card_aggregates,
        )
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
