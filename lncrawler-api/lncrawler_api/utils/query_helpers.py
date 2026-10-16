from django.db.models import Avg, Count, Exists, OuterRef, Prefetch, Subquery, Sum

from ..models import (
    Chapter,
    NovelBookmark,
    NovelRating,
    ReadingHistory,
    WeeklySourceView,
)
from ..models.sources_models import NovelFromSource, SourceVote

# Account setting values that let adult (R18) content through; 'blur' still
# shows it (the frontend blurs the covers), only 'no' hides it.
ADULT_ALLOWED_SETTINGS = ('yes', 'blur')


def adult_allowed(user):
    """Whether ``user`` may see adult novels. Anonymous visitors never can."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'show_r18', 'no') in ADULT_ALLOWED_SETTINGS


def exclude_adult(queryset, user=None):
    """Drop novels that have any adult source, unless the viewer may see them.

    A novel is treated as adult when *any* of its sources is adult.
    """
    if adult_allowed(user):
        return queryset
    return queryset.exclude(sources__is_adult=True)


def _latest_content_chapter():
    return Chapter.objects.filter(
        novel_from_source=OuterRef('pk'), has_content=True
    ).order_by('-chapter_id')


def _first_content_chapter():
    return Chapter.objects.filter(
        novel_from_source=OuterRef('pk'), has_content=True
    ).order_by('chapter_id')


def available_chapters_count(source):
    """Chapters with content for a source, preferring the queryset annotation
    (``annotated_available_chapters_count``) over a per-source COUNT. The
    annotation is NULL (not absent) when a source has no chapters, so detect
    it via ``__dict__`` like the serializer does."""
    if 'annotated_available_chapters_count' in source.__dict__:
        return source.annotated_available_chapters_count or 0
    return source.chapters.filter(has_content=True).count()


def preferred_source_key(source):
    """Rank a novel's sources the same everywhere: best vote score, then
    upvotes, then the most chapters with content, then title. Empty chapters
    never make a source look more complete than it reads."""
    return (
        -(source.upvotes - source.downvotes),
        -source.upvotes,
        -available_chapters_count(source),
        source.title or '',
    )


def _related_count(model, **filters):
    return Subquery(
        model.objects.filter(novel_from_source=OuterRef('pk'), **filters)
        .values('novel_from_source')
        .annotate(total=Count('*'))
        .values('total')[:1]
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


def annotate_card_aggregates(queryset, languages=None):
    """Annotate the four counters a novel card renders (avg/count rating and
    total/weekly views) as correlated subqueries.

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
    )


def sources_queryset(
    detailed=False, ip=None, user=None, associations=True, summary=False
):
    """Sources with everything the serializers read: external source and
    parent novel joined, authors/tags prefetched, and the latest available
    chapter annotated (avoids a per-source chapter query).

    ``detailed`` additionally annotates the first available chapter and
    prefetches volumes and (when an ``ip``/``user`` is given) the viewer's own
    vote/reading history, so detail views resolve the whole payload without a
    query per source. Lists only need authors/tags (the card serializer drops
    the rest), so they leave these off to keep their SQL smaller.

    ``summary`` is the middle ground the source page's "other sources" list and
    the novel detail's nested sources use: scalar columns plus the viewer's own
    vote, but no authors/tags/volumes/first-chapter and the big text columns
    deferred. ``associations=False`` drops the authors/tags prefetches too, for
    profiles that only read scalar source columns (e.g. the reading-list preview
    thumbnail)."""
    latest = _latest_content_chapter()
    if summary:
        associations = False
    if not associations:
        prefetch = []
    else:
        prefetch = (
            ['authors', 'editors', 'translators', 'tags', 'alternative_titles']
            if detailed
            else ['authors', 'tags']
        )
    qs = (
        NovelFromSource.objects.select_related('external_source', 'novel')
        .prefetch_related(*prefetch)
        .annotate(
            latest_chapter_id=Subquery(latest.values('chapter_id')[:1]),
            latest_chapter_title=Subquery(latest.values('title')[:1]),
            latest_chapter_url=Subquery(latest.values('url')[:1]),
            # Counted here so the serializer never runs per-source COUNT queries.
            annotated_chapters_count=_related_count(Chapter),
            annotated_available_chapters_count=_related_count(Chapter, has_content=True),
            # Novel-level adult flag: a novel is adult if any of its sources is,
            # so source cards blur when the *novel* is adult, not just this row.
            novel_is_adult=Exists(
                NovelFromSource.objects.filter(
                    novel=OuterRef('novel_id'), is_adult=True
                )
            ),
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
        if summary and ip:
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

    first = _first_content_chapter()
    qs = qs.annotate(
        first_chapter_id=Subquery(first.values('chapter_id')[:1]),
        first_chapter_title=Subquery(first.values('title')[:1]),
        first_chapter_url=Subquery(first.values('url')[:1]),
    ).prefetch_related('volumes')
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


def source_prefetch(
    prefix='', detailed=False, ip=None, user=None, associations=True,
    summary=False,
):
    """Prefetch a novel's sources (see `sources_queryset`)."""
    return Prefetch(
        prefix + 'sources',
        queryset=sources_queryset(
            detailed=detailed, ip=ip, user=user,
            associations=associations, summary=summary,
        ),
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


def novel_prefetch_objects(
    user=None, prefix='', detailed=False, ip=None,
    card_aggregates=False, associations=True, summary=False,
):
    """The prefetch list for a novel queryset, optionally addressed through a
    relation (e.g. prefix='to_novel__' for NovelSimilarity rows).

    ``card_aggregates`` drops the ratings/weekly-views prefetches because the
    queryset already carries the matching annotations
    (``annotate_card_aggregates``); only set it when that is true, otherwise the
    serializer falls back to a query per novel.
    """
    prefetches = [
        source_prefetch(
            prefix, detailed=detailed, ip=ip, user=user,
            associations=associations, summary=summary,
        ),
    ]
    if not card_aggregates:
        prefetches += [
            prefix + 'ratings',
            weekly_views_prefetch(prefix),
        ]
    if user is not None and user.is_authenticated:
        prefetches += [
            Prefetch(
                prefix + 'bookmarked_by_users',
                queryset=NovelBookmark.objects.filter(user=user),
                to_attr='user_bookmarks',
            ),
            Prefetch(
                prefix + 'reading_histories',
                queryset=ReadingHistory.objects.filter(user=user)
                .select_related('source', 'novel', 'last_read_chapter')
                .annotate(annotated_unread_chapters=unread_chapters_subquery()),
                to_attr='user_histories',
            ),
        ]
    return prefetches


def apply_novel_prefetches(
    queryset, user=None, detailed=False, ip=None, card_aggregates=False,
    summary=False,
):
    """Attach the relations the novel serializers read. Pass the request user
    so per-user bookmark/history lookups are collapsed into one query each;
    ``detailed`` adds the first-chapter/volumes/vote prefetches detail views
    need, while ``summary`` loads the lighter nested-source payload (see
    ``sources_queryset``). ``card_aggregates`` is passed through to
    ``novel_prefetch_objects``."""
    return queryset.prefetch_related(
        *novel_prefetch_objects(
            user, detailed=detailed, ip=ip,
            card_aggregates=card_aggregates, summary=summary,
        )
    )
