from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import F, Avg, Q, Count, Value, Max, Min, Sum
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
)
from ..languages import parse_languages
from ..models.reviews_models import Review
from ..utils import get_client_ip, resolve_novel_slug
from ..utils.query_helpers import (
    apply_novel_prefetches,
    novel_prefetch_objects,
    sources_queryset,
)
from ..serializers import (
    BasicNovelSerializer,
    DetailedNovelSerializer,
    NovelSourceSerializer,

)
from ..serializers.reviews_serializers import ReviewListSerializer

@api_view(["GET"])
def list_novels(request):
    """
    List all novels with pagination
    """
    novels = apply_novel_prefetches(
        Novel.objects.all().order_by("title"), request.user
    )
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)

    paginator = Paginator(novels, page_size)
    page_obj = paginator.get_page(page_number)

    serializer = BasicNovelSerializer(page_obj, many=True, context={"request": request})

    return Response(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "results": serializer.data,
        }
    )


@api_view(["GET"])
def novel_detail_by_slug(request, novel_slug):
    """
    Get details for a specific novel using its slug
    """
    novel = resolve_novel_slug(novel_slug)
    novel = apply_novel_prefetches(
        Novel.objects.filter(pk=novel.pk), request.user
    ).get()
    serializer = DetailedNovelSerializer(novel, context={"request": request})
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
    client_ip = get_client_ip(request)

    if not client_ip:
        return Response(
            {"error": "Could not determine your IP address."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create or update the rating
    rating, created = NovelRating.objects.update_or_create(
        novel=novel, ip_address=client_ip, defaults={"rating": rating_value}
    )

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
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)

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

    # Start with all novels
    novels_query = Novel.objects.all()

    # Apply search query if provided
    if query:
        novels_query = novels_query.filter(
            Q(title__icontains=query)
            | Q(sources__synopsis__icontains=query)
            | Q(sources__authors__name__icontains=query)
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

    # Filter by minimum rating
    if min_rating and min_rating.isdigit():
        min_rating_val = float(min_rating)
        # Get novels with average rating >= min_rating
        novels_with_min_rating = Novel.objects.annotate(
            avg_rating=Avg("ratings__rating")
        ).filter(avg_rating__gte=min_rating_val)
        novels_query = novels_query.filter(id__in=novels_with_min_rating)

    # Rolling 7-day window start for trending
    window_start = WeeklySourceView.window_start()

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
        # Use total view count for popularity (summed over sources)
        novels_query = novels_query.annotate(
            total_views=Coalesce(Sum('sources__total_views'), Value(0))
        )
        order_field = "-total_views" if sort_order == "desc" else "total_views"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "trending":
        # Use the rolling 7-day view count for trending (summed over sources)
        novels_query = novels_query.annotate(
            week_views=Coalesce(
                Sum(
                    "sources__weekly_views__views",
                    filter=Q(
                        sources__weekly_views__granularity=WeeklySourceView.DAY,
                        sources__weekly_views__day__gte=window_start,
                    ),
                ),
                Value(0),
            )
        )
        order_field = "-week_views" if sort_order == "desc" else "week_views"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "last_updated":
        # Annotate with the most recent last_updated date among all sources
        if sort_order == "desc":
            novels_query = novels_query.annotate(
                last_update=Max('sources__last_chapter_update')
            )
            order_field = "-last_update"
            novels_query = novels_query.order_by(order_field, "title")
        else:
            novels_query = novels_query.annotate(
                last_update=Min('sources__last_chapter_update')
            )
            order_field = "last_update"
            novels_query = novels_query.order_by(order_field, "title")
    else:
        # Default sorting by title
        novels_query = novels_query.order_by("title")

    # Resolve everything the serializer needs up front, then paginate.
    novels_query = apply_novel_prefetches(novels_query, request.user)

    # Pagination
    paginator = Paginator(novels_query, page_size)
    page_obj = paginator.get_page(page_number)

    serializer = BasicNovelSerializer(
        page_obj, many=True, context={"request": request, "languages": languages}
    )

    return Response(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "results": serializer.data,
            "filters": {
                "statuses": [
                    "Ongoing",
                    "Completed",
                    "Unknown",
                    "On Hiatus",
                    "Cancelled",
                ]
            },
        }
    )


@api_view(["GET"])
def autocomplete_suggestion(request):
    """
    Get autocomplete suggestions for tags, or authors with novel counts
    """
    search_type = request.GET.get("type", "")
    query = request.GET.get("query", "").strip()
    limit = int(request.GET.get("limit", "10"))

    if len(query) < 1:
        return Response([])

    if search_type == "tag":
        # Canonical tags matching the query.
        tag_counts = (
            Tag.objects.filter(name__icontains=query)
            .annotate(novel_count=Count("novels", distinct=True))
            .order_by("-novel_count")
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
            .annotate(novel_count=Count("tag__novels", distinct=True))
            .order_by("-novel_count")
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
            .annotate(novel_count=Count("novels", distinct=True))
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

    featured_count = FeaturedNovel.objects.count()
    if featured_count == 0:
        return Response(
            {
                "novel": None,
                "description": None,
                "featured_since": None,
            }
        )

    random_index = random.randint(0, featured_count - 1)
    featured = FeaturedNovel.objects.select_related('novel').prefetch_related(
        *novel_prefetch_objects(user=request.user, prefix='novel__')
    )[random_index]
    
    # Get the novel and serialize it
    novel = featured.novel
    serializer = DetailedNovelSerializer(novel, context={"request": request})
    
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
    # Rolling 7-day window start for trending
    window_start = WeeklySourceView.window_start()

    # Selected content languages (empty list = no segregation)
    languages = parse_languages(request.GET.getlist("languages"))
    serializer_context = {"request": request, "languages": languages}

    # Anonymous responses are identical for everyone with the same language
    # filter, so serve them from the per-process cache for a short window.
    # Authenticated responses embed user state (bookmarks/reading history) and
    # are never cached.
    cache_key = None
    if not request.user.is_authenticated:
        cache_key = "home_page:%s" % (",".join(sorted(languages)) if languages else "all")
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

    # Base queryset, optionally restricted to novels with a source in the
    # selected languages.
    base_queryset = apply_novel_prefetches(Novel.objects.all(), request.user)
    if languages:
        base_queryset = base_queryset.filter(
            sources__language__in=languages
        ).distinct()

    # Restrict the source-based view aggregations to the selected languages so
    # the ranking reflects readership within those languages.
    views_filter = Q()
    if languages:
        views_filter = Q(sources__language__in=languages)

    # Top novels (most popular, summed over sources)
    top_novels = (
        base_queryset.annotate(
            total_views=Coalesce(Sum('sources__total_views'), Value(0))
        )
        .order_by('-total_views', 'title')[:12]
    )
    
    # Trending novels (rolling 7-day views, summed over sources)
    trending_novels = (
        base_queryset.annotate(
            week_views=Coalesce(
                Sum(
                    "sources__weekly_views__views",
                    filter=Q(
                        sources__weekly_views__granularity=WeeklySourceView.DAY,
                        sources__weekly_views__day__gte=window_start,
                    ) & views_filter,
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
    featured_qs = FeaturedNovel.objects.select_related('novel').prefetch_related(
        *novel_prefetch_objects(user=request.user, prefix='novel__')
    )
    if languages:
        featured_qs = featured_qs.filter(novel__sources__language__in=languages).distinct()
    featured_count = featured_qs.count()
    if featured_count > 0:
        import random
        random_index = random.randint(0, featured_count - 1)
        featured = featured_qs[random_index]
        featured_novel_data = {
            'novel': DetailedNovelSerializer(featured.novel, context=serializer_context).data,
            'description': featured.description,
            'featured_since': featured.created_at,
        }
    
    # for the recently updated it's a list of NovelFromSource insead of Novel that we want
    recently_updated_qs = sources_queryset().order_by('-last_chapter_update')
    if languages:
        recently_updated_qs = recently_updated_qs.filter(language__in=languages)
    recently_updated = recently_updated_qs[:12]
    
    # Get recent reviews (restricted to novels in the selected languages)
    recent_reviews_qs = Review.objects.select_related('user', 'novel').prefetch_related('reactions__user').order_by('-created_at')
    if languages:
        recent_reviews_qs = recent_reviews_qs.filter(novel__sources__language__in=languages).distinct()
    recent_reviews = recent_reviews_qs[:4]
    
    # Serialize all the data
    response_data = {
        'top_novels': BasicNovelSerializer(top_novels, many=True, context=serializer_context).data,
        'trending_novels': BasicNovelSerializer(trending_novels, many=True, context=serializer_context).data,
        'top_rated_novels': BasicNovelSerializer(top_rated_novels, many=True, context=serializer_context).data,
        'recently_updated': NovelSourceSerializer(recently_updated, many=True, context=serializer_context).data,
        'featured_novel': featured_novel_data,
        'recent_reviews': ReviewListSerializer(recent_reviews, many=True, context=serializer_context).data,
    }
    
    if cache_key is not None:
        cache.set(cache_key, response_data, timeout=settings.HOME_PAGE_CACHE_SECONDS)
    
    return Response(response_data)
