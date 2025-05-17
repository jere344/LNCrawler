from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import F, Avg, Q, Count, Value, Max, Min
from django.db.models.functions import Coalesce
from ..models.novels_models import (
    Novel,
    SourceVote,
    NovelRating,
    Genre,
    Tag,
    Author,
    NovelViewCount,
    WeeklyNovelView,
    FeaturedNovel,
)
from ..utils import get_client_ip
from datetime import datetime
from ..serializers import (
    BasicNovelSerializer,
    DetailedNovelSerializer,
    NovelSourceSerializer,
    ChapterSerializer,
    ChapterContentSerializer,
)


@api_view(["GET"])
def list_novels(request):
    """
    List all novels with pagination
    """
    novels = Novel.objects.all().order_by("title")
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)

    paginator = Paginator(novels, page_size)
    page_obj = paginator.get_page(page_number)

    serializer = BasicNovelSerializer(page_obj, many=True, context={"request": request})

    return Response(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": int(page_number),
            "results": serializer.data,
        }
    )


@api_view(["GET"])
def novel_detail_by_slug(request, novel_slug):
    """
    Get details for a specific novel using its slug
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    serializer = DetailedNovelSerializer(novel, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
def source_detail(request, novel_slug, source_slug):
    """
    Get details for a specific novel source
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)

    serializer = NovelSourceSerializer(source, context={"request": request})
    # Add novel info to the response
    data = serializer.data
    data.update(
        {
            "novel_id": str(novel.id),
            "novel_slug": novel.slug,
            "novel_title": novel.title,
        }
    )

    return Response(data)


@api_view(["POST"])
def vote_source(request, novel_slug, source_slug):
    """
    Upvote or downvote a specific novel source
    """
    vote_type = request.data.get("vote_type")
    if vote_type not in ["up", "down"]:
        return Response(
            {"error": 'Invalid vote type. Use "up" or "down".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    client_ip = get_client_ip(request)

    if not client_ip:
        return Response(
            {"error": "Could not determine your IP address."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create or update the vote
    vote, created = SourceVote.objects.update_or_create(
        source=source, ip_address=client_ip, defaults={"vote_type": vote_type}
    )

    # Return updated vote counts
    return Response(
        {
            "upvotes": source.upvotes,
            "downvotes": source.downvotes,
            "vote_score": source.vote_score,
            "user_vote": vote_type,
        }
    )


@api_view(["GET"])
def novel_chapters_by_source(request, novel_slug, source_slug):
    """
    Get all chapters for a specific novel source using slugs with pagination
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)

    chapters = source.chapters.all().order_by("chapter_id")

    # Pagination parameters
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 100)  # Higher default for chapters

    paginator = Paginator(chapters, page_size)
    page_obj = paginator.get_page(page_number)

    serializer = ChapterSerializer(page_obj, many=True)

    return Response(
        {
            "novel_id": str(novel.id),
            "novel_title": novel.title,
            "novel_slug": novel.slug,
            "source_id": str(source.id),
            "source_name": source.source_name,
            "source_slug": source.source_slug,
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": int(page_number),
            "chapters": serializer.data,
        }
    )


@api_view(["GET"])
def chapter_content_by_number(request, novel_slug, source_slug, chapter_number):
    """
    Get content for a specific chapter by its number
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)

    if not chapter.has_content:
        return Response(
            {"error": "Chapter content not available"}, status=status.HTTP_404_NOT_FOUND
        )

    # Increment view count for the novel
    view_count, created = NovelViewCount.objects.get_or_create(novel=novel)
    view_count.increment()

    # Increment weekly view count
    WeeklyNovelView.increment_for_novel(novel)

    serializer = ChapterContentSerializer(chapter)
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

    novel = get_object_or_404(Novel, slug=novel_slug)
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
    genres = request.GET.getlist("genre", [])
    tags = request.GET.getlist("tag", [])
    authors = request.GET.getlist("author", [])
    status = request.GET.get("status", "")
    language = request.GET.get("language", "")
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

    # Filter by genres
    if genres:
        novels_query = novels_query.filter(sources__genres__name__in=genres).distinct()

    # Filter by tags
    if tags:
        novels_query = novels_query.filter(sources__tags__name__in=tags).distinct()

    # Filter by authors
    if authors:
        novels_query = novels_query.filter(
            sources__authors__name__in=authors
        ).distinct()

    # Filter by status
    if status:
        novels_query = novels_query.filter(sources__status=status).distinct()
        
    # Filter by language
    if language:
        novels_query = novels_query.filter(sources__language=language).distinct()

    # Filter by minimum rating
    if min_rating and min_rating.isdigit():
        min_rating_val = float(min_rating)
        # Get novels with average rating >= min_rating
        novels_with_min_rating = Novel.objects.annotate(
            avg_rating=Avg("ratings__rating")
        ).filter(avg_rating__gte=min_rating_val)
        novels_query = novels_query.filter(id__in=novels_with_min_rating)

    # Get current ISO year and week for trending
    current_date = datetime.now()
    current_year_week = (
        f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
    )

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
        # Use total view count for popularity
        novels_query = novels_query.annotate(
            total_views=Coalesce(F('view_count__views'), Value(0))
        )
        order_field = "-total_views" if sort_order == "desc" else "total_views"
        novels_query = novels_query.order_by(order_field, "title")
    elif sort_by == "trending":
        # Use weekly view count for trending
        novels_query = novels_query.annotate(
            week_views=Coalesce(
                Avg(
                    "weekly_views__views",
                    filter=Q(weekly_views__year_week=current_year_week),
                ),
                Value(0.0),
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

    # Pagination
    paginator = Paginator(novels_query, page_size)
    page_obj = paginator.get_page(page_number)

    serializer = BasicNovelSerializer(page_obj, many=True, context={"request": request})

    return Response(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": int(page_number),
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
    Get autocomplete suggestions for genres, tags, or authors with novel counts
    """
    search_type = request.GET.get("type", "")
    query = request.GET.get("query", "").strip()
    limit = int(request.GET.get("limit", "10"))

    if len(query) < 3:
        return Response([])

    if search_type == "genre":
        # Count novels for each genre
        genre_counts = (
            Genre.objects.filter(name__icontains=query)
            .annotate(novel_count=Count("novels", distinct=True))
            .order_by("-novel_count")[:limit]
        )

        suggestions = [
            {"name": genre.name, "count": genre.novel_count} for genre in genre_counts
        ]

    elif search_type == "tag":
        # Count novels for each tag
        tag_counts = (
            Tag.objects.filter(name__icontains=query)
            .annotate(novel_count=Count("novenovelslfromsource", distinct=True))
            .order_by("-novel_count")[:limit]
        )

        suggestions = [
            {"name": tag.name, "count": tag.novel_count} for tag in tag_counts
        ]

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
    featured = FeaturedNovel.objects.all()[random_index]
    
    # Get the novel and serialize it
    novel = featured.novel
    serializer = DetailedNovelSerializer(novel, context={"request": request})
    
    data = {
        'novel': serializer.data,
        'description': featured.description,
        'featured_since': featured.created_at,
    }
    
    return Response(data)
