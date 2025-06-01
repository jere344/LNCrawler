from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
import os
from urllib.parse import quote

from ..models import Novel, SourceVote, NovelViewCount, WeeklyNovelView
from ..serializers import NovelSourceSerializer, ChapterSerializer, ChapterContentSerializer
from ..serializers.sources_serializers import GalleryImageSerializer
from django.db.models import F, Avg, Q, Count, Value, Max, Min
from django.db.models.functions import Coalesce
from ..utils import get_client_ip
from django.conf import settings


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

    # Get the updated vote counts
    source.refresh_from_db()

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
            "source_name": source.external_source.source_name,
            "source_slug": source.source_slug,
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": int(page_number),
            "chapters": serializer.data,
            "source_overview_image_url": (
                f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{source.overview_picture_path}"
                if source.overview_picture_path and os.path.exists(
                    os.path.join(settings.LNCRAWL_OUTPUT_PATH, source.overview_picture_path)
                )
                else None
            ),
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


@api_view(["GET"])
def source_image_gallery(request, novel_slug, source_slug):
    """
    Get all images from a specific source for gallery display
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)

    # Get chapters with images
    chapters_with_images = source.chapters.filter(images__isnull=False)
    print(f"Chapters with images: {chapters_with_images.count()}")

    # Check if there are any images available
    has_overview = source.overview_picture_path and os.path.exists(os.path.join(settings.LNCRAWL_OUTPUT_PATH, source.overview_picture_path))
    if not chapters_with_images.exists() and not has_overview:
        return Response({"detail": "No images found for this source"}, status=status.HTTP_404_NOT_FOUND)

    # Pagination parameters
    page_number = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 20))

    # Prepare image data
    image_data = []
    
    # Add the overview image if it exists
    if has_overview:
        overview_image_url = f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{source.overview_picture_path}"
        image_data.append({
            "chapter_id": 0,  # Special ID for overview
            "chapter_title": "Novel Overview",
            "image_url": quote(overview_image_url, safe=':/'),
            "image_name": "overview.png"
        })

    # Add chapter images
    for chapter in chapters_with_images:
        base_image_url = f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{source.source_path}/images/"
        for image_name in chapter.images:
            image_data.append({
                "chapter_id": chapter.chapter_id,
                "chapter_title": chapter.title,
                "image_url": quote(f"{base_image_url}{image_name}", safe=':/'),
                "image_name": image_name
            })

    # Paginate the results
    paginator = Paginator(image_data, page_size)
    page_obj = paginator.get_page(page_number)
    
    # Get all images for the current page
    current_page_images = list(page_obj)
    
    serializer = GalleryImageSerializer(current_page_images, many=True)

    return Response({
        "novel_id": str(novel.id),
        "novel_title": novel.title,
        "novel_slug": novel.slug,
        "source_id": str(source.id),
        "source_name": source.external_source.source_name,
        "source_slug": source.source_slug,
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": int(page_number),
        "images": serializer.data
    })