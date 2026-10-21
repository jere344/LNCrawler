from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Avg, Q, Case, When, IntegerField, Count, Sum, Value, Max, Min
from django.db.models.functions import Coalesce, Upper
from ..models import (
    Novel,
    NovelRating,
    Tag,
    TagAlias,
    Author,
    AuthorAlias,
    NovelFromSource,
    WeeklySourceView,
    ReadingHistory,
)
from ..languages import parse_languages
from ..models.reviews_models import Review
from ..utils import get_client_ip, resolve_novel_slug
from ..utils.author_names import normalize_author
from ..utils.query_helpers import (
    adult_allowed,
    annotate_card_aggregates,
    apply_novel_prefetches,
    exclude_adult,
    sources_queryset,
)
from ..utils.pagination import paginated_response
from ..serializers import (
    NovelSerializer,
    NovelSourceSerializer,
)
from ..serializers.reviews_serializers import ReviewSerializer

@api_view(["GET"])
def list_novels(request):
    """
    List all novels with pagination
    """
    novels = annotate_card_aggregates(
        exclude_adult(Novel.objects.all(), request.user)
    )
    # Count a bare id queryset so the paginator doesn't recompute the four card
    # subqueries for every row just to get a total.
    count_queryset = novels.order_by().values("pk")
    novels = apply_novel_prefetches(
        novels, request.user, card_aggregates=True
    ).order_by("title")
    return paginated_response(
        request, novels, NovelSerializer, max_size=50, count_queryset=count_queryset
    )


@api_view(["GET"])
def novel_detail_by_slug(request, novel_slug):
    """
    Get details for a specific novel using its slug
    """
    novel = resolve_novel_slug(novel_slug)
    novel = apply_novel_prefetches(
        Novel.objects.filter(pk=novel.pk), request.user,
        summary=True, ip=get_client_ip(request),
    ).get()
    serializer = NovelSerializer(novel, context={"request": request}, profile='detail')
    return Response(serializer.data)




@api_view(["POST"])
def rate_novel(request, novel_slug):
    """
    Rate a novel from 1-5 stars
    """
    rating_value = request.data.get("rating")
    try:
        rating_value = int(rating_value)
        if rating_value < 1 or rating_value > 5:
            raise ValueError("Rating must be between 1 and 5")
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid rating. Must be an integer between 1 and 5."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    novel = resolve_novel_slug(novel_slug)

    # Logged-in users are keyed by user; anonymous visitors fall back to IP
    # (same pattern as comments/reactions).
    if request.user.is_authenticated:
        lookup = {"novel": novel, "user": request.user}
    else:
        client_ip = get_client_ip(request)
        if not client_ip:
            return Response(
                {"error": "Could not determine your IP address."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lookup = {"novel": novel, "user": None, "ip_address": client_ip}

    # A concurrent first-time rating for the same (novel, user/ip) can win the
    # insert race between our get and create; catch the unique-constraint
    # violation and fall back to updating the row the other request inserted.
    try:
        with transaction.atomic():
            rating, created = NovelRating.objects.update_or_create(
                defaults={"rating": rating_value}, **lookup
            )
    except IntegrityError:
        NovelRating.objects.filter(**lookup).update(rating=rating_value)

    # Get updated average rating
    avg_rating = novel.ratings.aggregate(avg_rating=Avg("rating"))["avg_rating"]
    rating_count = novel.ratings.count()

    return Response(
        {
            "avg_rating": round(avg_rating, 1) if avg_rating else None,
            "rating_count": rating_count,
            "user_rating": rating_value,
        }
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


@api_view(["GET"])
def search_novels(request):
    """
    Search novels with various filters
    """
    # Get search parameters
    query = request.GET.get("query", "").strip()

    # Get filter parameters
    tags = _canonical_tag_names(request.GET.getlist("tag", []))
    exclude_tags = _canonical_tag_names(request.GET.getlist("exclude_tag", []))
    authors = request.GET.getlist("author", [])
    status = request.GET.get("status", "")
    # Accept either the multi-value "languages" (repeated or comma-separated) or
    # the legacy single "language" parameter.
    languages = parse_languages(
        request.GET.getlist("languages") + request.GET.getlist("language")
    )
    min_rating = request.GET.get("min_rating", None)
    sort_by = request.GET.get("sort_by", "title")
    sort_order = request.GET.get("sort_order", "asc")
    # Adult filter: hide (default), show (mixed in), only (adult only). Defaults
    # to show when the account allows adult content, else hide.
    adult = request.GET.get("adult", "")
    if adult not in ("hide", "show", "only"):
        adult = "show" if adult_allowed(request.user) else "hide"

    # Start with all novels
    novels_query = Novel.objects.all()

    # "hide" is applied after the other filters, once the hidden count is known.
    if adult == "only":
        novels_query = novels_query.filter(sources__is_adult=True).distinct()

    # Apply search query if provided
    if query:
        # Each traversal is its own subquery so Postgres can use the per-column
        # pg_trgm indexes; a single multi-table OR cannot use them. Authors are
        # intentionally not searched here (use ?author= or the author
        # autocomplete instead).
        # Fuzzy title match (pg_trgm) tolerates near-miss spellings like
        # "bungo"/"bungou"; the GIN trgm index on UPPER(title) backs the lookup.
        fuzzy_titles = Novel.objects.annotate(
            _upper_title=Upper("title")
        ).filter(_upper_title__trigram_similar=query.upper()).values('id')
        novels_query = novels_query.filter(
            Q(id__in=Novel.objects.filter(title__icontains=query).values('id'))
            | Q(id__in=fuzzy_titles)
            | Q(id__in=NovelFromSource.objects.filter(synopsis__icontains=query).values('novel_id'))
            | Q(id__in=NovelFromSource.objects.filter(alternative_titles__name__icontains=query).values('novel_id'))
        ).annotate(
            # Relevance: exact title, exact alt-title, title prefix, title
            # substring, fuzzy title, then anything else (e.g. synopsis match).
            _relevance=Case(
                When(title__iexact=query, then=Value(0)),
                When(
                    Q(pk__in=NovelFromSource.objects.filter(
                        alternative_titles__name__iexact=query
                    ).values('novel_id')),
                    then=Value(1),
                ),
                When(title__istartswith=query, then=Value(2)),
                When(title__icontains=query, then=Value(3)),
                When(Q(pk__in=fuzzy_titles), then=Value(4)),
                default=Value(5),
                output_field=IntegerField(),
            )
        ).distinct()

    # Filter by tags
    if tags:
        novels_query = novels_query.filter(sources__tags__name__in=tags).distinct()

    # Exclude novels with certain tags
    if exclude_tags:
        novels_query = novels_query.exclude(sources__tags__name__in=exclude_tags).distinct()

    # Filter by authors
    if authors:
        novels_query = novels_query.filter(
            sources__authors__in=_author_ids(authors)
        ).distinct()

    # Filter by status
    if status:
        novels_query = novels_query.filter(sources__status=status).distinct()
        
    # Filter by language(s)
    if languages:
        novels_query = novels_query.filter(sources__language__in=languages).distinct()

    # Filter by minimum rating (decimals allowed: "4.5")
    if min_rating:
        try:
            min_rating_val = float(min_rating)
        except (TypeError, ValueError):
            min_rating_val = None
        if min_rating_val is not None:
            # Average rating >= min_rating, read from the scheduler-refreshed
            # projection. Unrated novels project to 0 and every real average is
            # >= 1, so the floor of 1 keeps them excluded as before.
            novels_query = novels_query.filter(rank_avg_rating__gte=max(min_rating_val, 1))

    # Apply sorting
    # The popularity, trending and rating sorts read scheduler-refreshed projections (up to ~5 min stale).
    if sort_by == "rating":
        order_field = "-rank_avg_rating" if sort_order == "desc" else "rank_avg_rating"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "title":
        order_field = "-title" if sort_order == "desc" else "title"
        novels_query = novels_query.order_by(order_field)
    elif sort_by == "date_added":
        order_field = "-created_at" if sort_order == "desc" else "created_at"
        novels_query = novels_query.order_by(order_field)
    elif sort_by == "popularity":
        # Total view count for popularity, from the rank_total_views projection
        order_field = "-rank_total_views" if sort_order == "desc" else "rank_total_views"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "trending":
        # Rolling 7-day view count for trending, from the rank_week_views projection
        order_field = "-rank_week_views" if sort_order == "desc" else "rank_week_views"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "last_updated":
        # Annotate with the most recent last_updated date among all sources.
        # Never-updated sources (NULL) sort last in both directions.
        if sort_order == "desc":
            novels_query = novels_query.annotate(
                last_update=Max('sources__last_chapter_update')
            )
            novels_query = novels_query.order_by(
                F("last_update").desc(nulls_last=True), "title"
            )
        else:
            novels_query = novels_query.annotate(
                last_update=Min('sources__last_chapter_update')
            )
            novels_query = novels_query.order_by(
                F("last_update").asc(nulls_last=True), "title"
            )
    else:
        # Default sorting by title
        novels_query = novels_query.order_by("title")

    # With a text query, exact/near title matches outrank the chosen sort; the
    # chosen sort still breaks ties within the same relevance tier.
    if query:
        novels_query = novels_query.order_by(
            "_relevance", *novels_query.query.order_by
        )

    # Count distinct ids without the display-only relevance annotation (which
    # re-runs the fuzzy-title subquery a second time); the full SELECT would
    # evaluate all of it for every match just to page 20 rows.
    count_queryset = novels_query.order_by().values("pk")

    # Hidden adult matches: the ones the filters found that "hide" drops. Counted
    # on the same filtered set, so the UI can say how many results were left out.
    hidden_adult = 0
    if adult == "hide":
        hidden_adult = count_queryset.filter(
            pk__in=Novel.objects.filter(sources__is_adult=True).values("pk")
        ).count()
        novels_query = novels_query.exclude(sources__is_adult=True)
        count_queryset = novels_query.order_by().values("pk")

    # Resolve everything the serializer needs up front, then paginate.
    novels_query = apply_novel_prefetches(novels_query, request.user)

    return paginated_response(
        request, novels_query, NovelSerializer,
        max_size=50,
        context={"languages": languages},
        count_queryset=count_queryset,
        extra={
            "hidden_adult": hidden_adult,
            "filters": {
                "statuses": ["Ongoing", "Completed", "Unknown", "On Hiatus", "Cancelled"],
            },
        },
    )


@api_view(["GET"])
def autocomplete_suggestion(request):
    """
    Get autocomplete suggestions for tags, or authors with novel counts
    """
    search_type = request.GET.get("type", "")
    query = request.GET.get("query", "").strip()
    try:
        limit = max(1, min(int(request.GET.get("limit", "10")), 50))
    except (TypeError, ValueError):
        limit = 10

    if len(query) < 1:
        return Response([])

    if search_type == "tag":
        # Canonical tags matching the query.
        tag_counts = (
            Tag.objects.filter(name__icontains=query)
            .annotate(novel_count=Count("novels__novel", distinct=True))
            .order_by("-novel_count")[:limit]
        )
        suggestions = {
            tag.name: {"name": tag.name, "count": tag.novel_count}
            for tag in tag_counts
        }

        # Merged-away names: surface their canonical tag so old searches still
        # find it. Display-only, the canonical name stays the selected value.
        alias_matches = (
            TagAlias.objects.filter(name__icontains=query)
            .select_related("tag")
            .annotate(novel_count=Count("tag__novels__novel", distinct=True))
            .order_by("-novel_count")[:limit]
        )
        for alias in alias_matches:
            entry = suggestions.get(alias.tag.name)
            if entry is None:
                suggestions[alias.tag.name] = {
                    "name": alias.tag.name,
                    "count": alias.novel_count,
                    "alias": alias.name,
                }
            else:
                entry.setdefault("alias", alias.name)

        suggestions = sorted(
            suggestions.values(), key=lambda s: (-s["count"], s["name"])
        )[:limit]

    elif search_type == "author":
        # Count novels for each author
        author_counts = (
            Author.objects.filter(name__icontains=query)
            .annotate(novel_count=Count("novels__novel", distinct=True))
            .order_by("-novel_count")[:limit]
        )
        suggestions = {
            author.pk: {"name": author.name, "count": author.novel_count}
            for author in author_counts
        }

        # Merged-away names: surface their author so old searches still find it.
        # Display-only, the canonical name stays the selected value.
        alias_matches = (
            AuthorAlias.objects.filter(name__icontains=query, author__is_blocked=False)
            .select_related("author")
            .annotate(novel_count=Count("author__novels__novel", distinct=True))
            .order_by("-novel_count")[:limit]
        )
        for alias in alias_matches:
            entry = suggestions.get(alias.author_id)
            if entry is None:
                suggestions[alias.author_id] = {
                    "name": alias.author.name,
                    "count": alias.novel_count,
                    "alias": alias.name,
                }
            else:
                entry.setdefault("alias", alias.name)

        suggestions = sorted(
            suggestions.values(), key=lambda s: (-s["count"], s["name"])
        )[:limit]

    else:
        return Response(
            {"error": "Invalid search type"}, status=status.HTTP_400_BAD_REQUEST
        )

    return Response(suggestions)


# How long the home page's ranking id lists are reused before being recomputed
HOME_RANKING_CACHE_SECONDS = 120


def _in_order(queryset, ids):
    """Evaluate ``queryset`` and return its objects in the order of ``ids``."""
    by_pk = {obj.pk: obj for obj in queryset}
    return [by_pk[pk] for pk in ids if pk in by_pk]


@api_view(["GET"])
def home_page(request):
    """
    Get all data needed for the home page in a single request.

    When the ``languages`` query parameter is present (and non-empty) every
    section is restricted to novels available in those content languages; the
    rankings merge the selected languages together. The frontend omits the
    parameter when the user disabled language segregation.
    """
    # Selected content languages (empty list = no segregation)
    languages = parse_languages(request.GET.getlist("languages"))
    serializer_context = {"request": request, "languages": languages}

    # Base queryset, optionally restricted to novels with a source in the
    # selected languages.
    base_queryset = apply_novel_prefetches(
        exclude_adult(Novel.objects.filter(is_dmca=False), request.user), request.user
    )
    if languages:
        # Match novels having a source in the selected languages without
        # joining sources: a join forces DISTINCT, so every ranking subquery
        # runs over the deduplicated set before LIMIT instead of a top-N scan.
        base_queryset = base_queryset.filter(
            pk__in=NovelFromSource.objects.filter(language__in=languages).values("novel")
        )

    # Rankings sum the already-stored per-source projections (total_views is
    # maintained by WeeklySourceView.increment_for_source) in a single
    # aggregate join, scoped to the selected languages. The base queryset
    # filters languages via pk__in (no source join), so this join adds no
    # duplicate rows and each novel's sources are summed in one pass instead
    # of one correlated subquery per novel.
    language_filter = Q(sources__language__in=languages) if languages else Q()
    week_filter = Q(
        sources__weekly_views__granularity=WeeklySourceView.DAY,
        sources__weekly_views__day__gte=WeeklySourceView.window_start(),
    )

    # Top novels (most popular), ranked by all-time views.
    top_novels = (
        base_queryset.annotate(
            total_views=Coalesce(
                Sum('sources__total_views', filter=language_filter), Value(0)
            )
        )
        .order_by('-total_views', 'title')[:12]
    )

    # Trending novels (rolling 7-day views).
    trending_novels = (
        base_queryset.annotate(
            week_views=Coalesce(
                Sum(
                    'sources__weekly_views__views',
                    filter=language_filter & week_filter,
                ),
                Value(0),
            )
        )
        .order_by('-week_views', 'title')[:12]
    )
    
    # Top rated novels
    top_rated_novels = (
        base_queryset.annotate(
            avg_rating=Coalesce(Avg("ratings__rating"), Value(0.0))
        )
        .order_by('-avg_rating', 'title')[:12]
    )
    
    # Recently added novels, one entry per novel (by creation time). Distinct
    # from recently_updated below, which lists per-source chapter updates.
    recently_added = base_queryset.order_by('-created_at')[:12]
    
    # for the recently updated it's a list of NovelFromSource insead of Novel that we want
    # NULLs sort first on PostgreSQL by default; never-updated sources would top
    # the strip, so push them to the end.
    recently_updated_qs = sources_queryset().filter(novel__is_dmca=False)
    # Novel-level: hide the whole novel if any of its sources is adult.
    recently_updated_qs = exclude_adult(recently_updated_qs, request.user, 'novel__')
    recently_updated_qs = recently_updated_qs.order_by(
        F('last_chapter_update').desc(nulls_last=True)
    )
    if languages:
        recently_updated_qs = recently_updated_qs.filter(language__in=languages)
    recently_updated = recently_updated_qs[:12]

    # The ranking id lists are the expensive part and are shared by every viewer
    # with the same language set and adult setting, so only those are cached.
    # The cards are re-fetched per request so per-viewer fields (bookmarks,
    # reading history) stay current.
    rank_key = f"home:rank:v1:{','.join(sorted(languages))}:{int(adult_allowed(request.user))}"
    rankings = cache.get(rank_key)
    if rankings is None:
        rankings = {
            'top_novels': list(top_novels.prefetch_related(None).values_list('pk', flat=True)),
            'trending_novels': list(trending_novels.prefetch_related(None).values_list('pk', flat=True)),
            'top_rated_novels': list(top_rated_novels.prefetch_related(None).values_list('pk', flat=True)),
            'recently_added': list(recently_added.prefetch_related(None).values_list('pk', flat=True)),
            'recently_updated': list(recently_updated.prefetch_related(None).values_list('pk', flat=True)),
        }
        cache.set(rank_key, rankings, HOME_RANKING_CACHE_SECONDS)

    def novels_in_order(ids):
        # DMCA and adult filters are re-applied so a takedown or a newly adult
        # novel drops off immediately instead of lingering for the cache TTL.
        return _in_order(
            apply_novel_prefetches(
                exclude_adult(Novel.objects.filter(pk__in=ids, is_dmca=False), request.user),
                request.user,
            ),
            ids,
        )

    top_novels = novels_in_order(rankings['top_novels'])
    trending_novels = novels_in_order(rankings['trending_novels'])
    top_rated_novels = novels_in_order(rankings['top_rated_novels'])
    recently_added = novels_in_order(rankings['recently_added'])
    recently_updated_fresh = sources_queryset().filter(
        pk__in=rankings['recently_updated'], novel__is_dmca=False
    )
    recently_updated_fresh = exclude_adult(recently_updated_fresh, request.user, 'novel__')
    recently_updated = _in_order(recently_updated_fresh, rankings['recently_updated'])

    # Get recent reviews (restricted to novels in the selected languages)
    recent_reviews_qs = Review.objects.select_related('user', 'novel').filter(
        novel__is_dmca=False
    )
    recent_reviews_qs = exclude_adult(recent_reviews_qs, request.user, 'novel__')
    recent_reviews_qs = recent_reviews_qs.order_by('-created_at')
    if languages:
        recent_reviews_qs = recent_reviews_qs.filter(
            novel__in=NovelFromSource.objects.filter(language__in=languages).values("novel")
        )
    recent_reviews = recent_reviews_qs[:4]
    
    # "Recommended for you" (authenticated users with reading history only):
    # seed from the last five novels read, aggregate their similarities, and
    # exclude every novel the user already read. Anonymous visitors skip this
    # entirely, so the public home path is untouched.
    recommended_novels = []
    if request.user.is_authenticated:
        from .users_views import get_novel_recommendations

        # One ordered fetch serves both the similarity seeds (last five) and
        # the exclusion set (every novel already read).
        read_ids = list(
            ReadingHistory.objects.filter(user=request.user)
            .order_by('-last_read_at')
            .values_list('novel_id', flat=True)
        )
        if read_ids:
            recommended_novels = get_novel_recommendations(
                request.user, read_ids[:5], viewer=request.user,
                exclude_ids=read_ids, languages=languages,
            )
    
    # "Novels you added" (authenticated users only): novels whose download job
    # was first started by this user. Deliberately built without the language
    # *and adult* filters so a user always sees everything they contributed,
    # even R18 novels; the frontend keeps the cover blurred unless the account
    # allows adult content. Anonymous visitors get an empty list.
    novels_you_added = []
    if request.user.is_authenticated:
        novels_you_added = apply_novel_prefetches(
            Novel.objects.filter(is_dmca=False, added_by=request.user),
            request.user,
        ).order_by('-created_at')[:12]

    # Serialize all the data
    response_data = {
        'top_novels': NovelSerializer(top_novels, many=True, context=serializer_context).data,
        'trending_novels': NovelSerializer(trending_novels, many=True, context=serializer_context).data,
        'top_rated_novels': NovelSerializer(top_rated_novels, many=True, context=serializer_context).data,
        'recently_added': NovelSerializer(recently_added, many=True, context=serializer_context).data,
        'recently_updated': NovelSourceSerializer(recently_updated, many=True, context=serializer_context, profile='card').data,
        'recent_reviews': ReviewSerializer(recent_reviews, many=True, context=serializer_context, profile='card').data,
        'recommended_novels': NovelSerializer(recommended_novels, many=True, context=serializer_context).data,
        'novels_you_added': NovelSerializer(novels_you_added, many=True, context=serializer_context).data,
    }
    
    return Response(response_data)
