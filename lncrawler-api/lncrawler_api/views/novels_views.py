from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import IntegrityError, transaction
from django.db.models import F, Avg, Q, Case, When, IntegerField, Count, Sum, Value, Max, Min
from django.db.models.functions import Coalesce
from ..models import (
    Novel,
    NovelRating,
    Tag,
    TagAlias,
    Author,
    FeaturedNovel,
    NovelFromSource,
    WeeklySourceView,
    ReadingHistory,
)
from ..languages import parse_languages
from ..models.reviews_models import Review
from ..utils import get_client_ip, resolve_novel_slug
from ..utils.query_helpers import (
    adult_allowed,
    apply_novel_prefetches,
    exclude_adult,
    novel_prefetch_objects,
    sources_queryset,
    sources_total_views_subquery,
    weekly_views_subquery,
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
    novels = apply_novel_prefetches(
        exclude_adult(Novel.objects.all(), request.user).order_by("title"), request.user
    )
    return paginated_response(request, novels, NovelSerializer, max_size=50)


@api_view(["GET"])
def novel_detail_by_slug(request, novel_slug):
    """
    Get details for a specific novel using its slug
    """
    novel = resolve_novel_slug(novel_slug)
    novel = apply_novel_prefetches(
        Novel.objects.filter(pk=novel.pk), request.user,
        detailed=True, ip=get_client_ip(request),
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


@api_view(["GET"])
def search_novels(request):
    """
    Search novels with various filters
    """
    # Get search parameters
    query = request.GET.get("query", "").strip()

    # Get filter parameters
    tags = request.GET.getlist("tag", [])
    exclude_tags = request.GET.getlist("exclude_tag", [])
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

    if adult == "hide":
        novels_query = novels_query.exclude(sources__is_adult=True)
    elif adult == "only":
        novels_query = novels_query.filter(sources__is_adult=True).distinct()

    # Apply search query if provided
    if query:
        # Each traversal is its own subquery so Postgres can use the per-column
        # pg_trgm indexes; a single multi-table OR cannot use them. Authors are
        # intentionally not searched here (use ?author= or the author
        # autocomplete instead).
        novels_query = novels_query.filter(
            Q(id__in=Novel.objects.filter(title__icontains=query).values('id'))
            | Q(id__in=NovelFromSource.objects.filter(synopsis__icontains=query).values('novel_id'))
            | Q(id__in=NovelFromSource.objects.filter(alternative_titles__name__icontains=query).values('novel_id'))
        ).annotate(
            # Relevance: exact title, exact alt-title, title prefix, title
            # substring, then anything else (e.g. synopsis match).
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
                default=Value(4),
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
            sources__authors__name__in=authors
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
            # Get novels with average rating >= min_rating
            novels_with_min_rating = Novel.objects.annotate(
                avg_rating=Avg("ratings__rating")
            ).filter(avg_rating__gte=min_rating_val)
            novels_query = novels_query.filter(id__in=novels_with_min_rating)

    # Apply sorting
    if sort_by == "rating":
        # Sort by rating requires annotation
        novels_query = novels_query.annotate(
            avg_rating=Coalesce(Avg("ratings__rating"), Value(0.0))
        )
        order_field = "-avg_rating" if sort_order == "desc" else "avg_rating"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "title":
        order_field = "-title" if sort_order == "desc" else "title"
        novels_query = novels_query.order_by(order_field)
    elif sort_by == "date_added":
        order_field = "-created_at" if sort_order == "desc" else "created_at"
        novels_query = novels_query.order_by(order_field)
    elif sort_by == "popularity":
        # Use total view count for popularity, summed over a deduplicated
        # subquery so tag/author filters joining sources don't inflate it.
        novels_query = novels_query.annotate(
            total_views=Coalesce(sources_total_views_subquery(), Value(0))
        )
        order_field = "-total_views" if sort_order == "desc" else "total_views"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "trending":
        # Use the rolling 7-day view count for trending (deduplicated subquery)
        novels_query = novels_query.annotate(
            week_views=Coalesce(weekly_views_subquery(), Value(0))
        )
        order_field = "-week_views" if sort_order == "desc" else "week_views"
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

    # Resolve everything the serializer needs up front, then paginate.
    novels_query = apply_novel_prefetches(novels_query, request.user)

    return paginated_response(
        request, novels_query, NovelSerializer,
        max_size=50,
        context={"languages": languages},
        extra={"filters": {
            "statuses": ["Ongoing", "Completed", "Unknown", "On Hiatus", "Cancelled"],
        }},
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

        suggestions = [
            {"name": author.name, "count": author.novel_count}
            for author in author_counts
        ]

    else:
        return Response(
            {"error": "Invalid search type"}, status=status.HTTP_400_BAD_REQUEST
        )

    return Response(suggestions)


@api_view(["GET"])
def random_featured_novel(request):
    """
    Get a random featured novel
    """
    import random

    featured_qs = FeaturedNovel.objects.select_related('novel').filter(
        novel__is_dmca=False
    )
    if not adult_allowed(request.user):
        featured_qs = featured_qs.exclude(novel__sources__is_adult=True)
    featured_qs = featured_qs.prefetch_related(
        *novel_prefetch_objects(
            user=request.user, prefix='novel__',
            ip=get_client_ip(request),
        )
    )
    featured_count = featured_qs.count()
    if featured_count == 0:
        return Response(
            {
                "novel": None,
                "description": None,
                "featured_since": None,
            }
        )

    random_index = random.randint(0, featured_count - 1)
    featured = featured_qs[random_index]
    
    # Get the novel and serialize it
    novel = featured.novel
    serializer = NovelSerializer(novel, context={"request": request}, profile='featured')
    
    data = {
        'novel': serializer.data,
        'description': featured.description,
        'featured_since': featured.created_at,
    }
    
    return Response(data)

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
    
    # Get featured novel (restricted to one available in the selected languages)
    featured_novel_data = None
    featured_qs = FeaturedNovel.objects.select_related('novel').filter(
        novel__is_dmca=False
    )
    if not adult_allowed(request.user):
        featured_qs = featured_qs.exclude(novel__sources__is_adult=True)
    featured_qs = featured_qs.prefetch_related(
        *novel_prefetch_objects(
            user=request.user, prefix='novel__',
            ip=get_client_ip(request),
        )
    )
    if languages:
        featured_qs = featured_qs.filter(novel__sources__language__in=languages).distinct()
    featured_count = featured_qs.count()
    if featured_count > 0:
        import random
        random_index = random.randint(0, featured_count - 1)
        featured = featured_qs[random_index]
        featured_novel_data = {
            'novel': NovelSerializer(featured.novel, context=serializer_context, profile='featured').data,
            'description': featured.description,
            'featured_since': featured.created_at,
        }
    
    # for the recently updated it's a list of NovelFromSource insead of Novel that we want
    # NULLs sort first on PostgreSQL by default; never-updated sources would top
    # the strip, so push them to the end.
    recently_updated_qs = sources_queryset().filter(novel__is_dmca=False)
    if not adult_allowed(request.user):
        # Novel-level: hide the whole novel if any of its sources is adult.
        recently_updated_qs = recently_updated_qs.exclude(novel__sources__is_adult=True)
    recently_updated_qs = recently_updated_qs.order_by(
        F('last_chapter_update').desc(nulls_last=True)
    )
    if languages:
        recently_updated_qs = recently_updated_qs.filter(language__in=languages)
    recently_updated = recently_updated_qs[:12]
    
    # Get recent reviews (restricted to novels in the selected languages)
    recent_reviews_qs = Review.objects.select_related('user', 'novel').filter(
        novel__is_dmca=False
    )
    if not adult_allowed(request.user):
        recent_reviews_qs = recent_reviews_qs.exclude(novel__sources__is_adult=True)
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
    
    # Serialize all the data
    response_data = {
        'top_novels': NovelSerializer(top_novels, many=True, context=serializer_context).data,
        'trending_novels': NovelSerializer(trending_novels, many=True, context=serializer_context).data,
        'top_rated_novels': NovelSerializer(top_rated_novels, many=True, context=serializer_context).data,
        'recently_updated': NovelSourceSerializer(recently_updated, many=True, context=serializer_context, profile='card').data,
        'featured_novel': featured_novel_data,
        'recent_reviews': ReviewSerializer(recent_reviews, many=True, context=serializer_context, profile='card').data,
        'recommended_novels': NovelSerializer(recommended_novels, many=True, context=serializer_context).data,
    }
    
    return Response(response_data)
