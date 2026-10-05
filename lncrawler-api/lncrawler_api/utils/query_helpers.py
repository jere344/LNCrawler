from django.db.models import Count, OuterRef, Prefetch, Subquery, Sum

from ..models import (
    Chapter,
    NovelBookmark,
    ReadingHistory,
    Volume,
    WeeklySourceView,
)
from ..models.sources_models import NovelFromSource, SourceVote


def _latest_content_chapter():
    return Chapter.objects.filter(
        novel_from_source=OuterRef('pk'), has_content=True
    ).order_by('-chapter_id')


def _first_content_chapter():
    return Chapter.objects.filter(
        novel_from_source=OuterRef('pk'), has_content=True
    ).order_by('chapter_id')


def _related_count(model, **filters):
    return Subquery(
        model.objects.filter(novel_from_source=OuterRef('pk'), **filters)
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


def sources_queryset(detailed=False, ip=None, user=None):
    """Sources with everything the serializers read: external source and
    parent novel joined, authors/tags prefetched, and the latest available
    chapter annotated (avoids a per-source chapter query).

    ``detailed`` additionally annotates the first available chapter and
    prefetches volumes and (when an ``ip``/``user`` is given) the viewer's own
    vote/reading history, so detail views resolve the whole payload without a
    query per source. Lists leave these off to keep their SQL smaller."""
    latest = _latest_content_chapter()
    qs = (
        NovelFromSource.objects.select_related('external_source', 'novel')
        .prefetch_related('authors', 'editors', 'translators', 'tags', 'alternative_titles')
        .annotate(
            latest_chapter_id=Subquery(latest.values('chapter_id')[:1]),
            latest_chapter_title=Subquery(latest.values('title')[:1]),
            latest_chapter_url=Subquery(latest.values('url')[:1]),
            # Counted here so the serializer never runs per-source COUNT queries.
            annotated_chapters_count=_related_count(Chapter),
            annotated_volumes_count=_related_count(Volume),
        )
    )
    if not detailed:
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


def source_prefetch(prefix='', detailed=False, ip=None, user=None):
    """Prefetch a novel's sources (see `sources_queryset`)."""
    return Prefetch(
        prefix + 'sources',
        queryset=sources_queryset(detailed=detailed, ip=ip, user=user),
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


def novel_prefetch_objects(user=None, prefix='', detailed=False, ip=None):
    """The prefetch list for a novel queryset, optionally addressed through a
    relation (e.g. prefix='to_novel__' for NovelSimilarity rows)."""
    prefetches = [
        source_prefetch(prefix, detailed=detailed, ip=ip, user=user),
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
                queryset=ReadingHistory.objects.filter(user=user).select_related(
                    'source', 'novel', 'last_read_chapter'
                ),
                to_attr='user_histories',
            ),
        ]
    return prefetches


def apply_novel_prefetches(queryset, user=None, detailed=False, ip=None):
    """Attach the relations the novel serializers read. Pass the request user
    so per-user bookmark/history lookups are collapsed into one query each;
    ``detailed`` adds the first-chapter/volumes/vote prefetches detail views
    need (see ``sources_queryset``)."""
    return queryset.prefetch_related(
        *novel_prefetch_objects(user, detailed=detailed, ip=ip)
    )
