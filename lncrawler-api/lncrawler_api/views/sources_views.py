from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
import os

from ..models import Novel, SourceVote, WeeklySourceView, resolve_output_path
from ..serializers import NovelSourceSerializer, ChapterSerializer
from ..serializers.sources_serializers import GalleryImageSerializer
from django.db.models import F, Avg, Q, Count, Value, Max, Min, Sum, Func, IntegerField
from django.db.models.functions import Coalesce
from django.http import FileResponse
from ..utils import build_media_url, get_client_ip, resolve_novel_slug
from ..utils.query_helpers import sources_queryset
from ..utils.pagination import parse_page_size
from ..services.epub_service import get_or_build_epub


MAX_EPUB_CHAPTERS = 500


class ArrayLength(Func):
    """Postgres array length (Django has no built-in array Length)."""
    function = 'CARDINALITY'
    arity = 1
    output_field = IntegerField()


@api_view(["GET"])
def source_detail(request, novel_slug, source_slug):
    """
    Get details for a specific novel source
    """
    novel = resolve_novel_slug(novel_slug)
    # Resolve every field the serializer reads (chapters, volumes, viewer vote
    # and reading history) in the initial queryset instead of one fallback
    # query per field.
    source = get_object_or_404(
        sources_queryset(detailed=True, ip=get_client_ip(request), user=request.user)
        .filter(novel=novel),
        source_slug=source_slug,
    )

    serializer = NovelSourceSerializer(source, context={"request": request}, profile='detail')
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

    novel = resolve_novel_slug(novel_slug)
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
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)

    chapters = source.chapters.all().order_by("chapter_id")

    search = request.GET.get("search", "").strip()
    if search:
        chapters = chapters.filter(
            Q(title__icontains=search) | Q(chapter_id__icontains=search)
        )

    # Pagination parameters
    page_number = request.GET.get("page", 1)
    page_size = parse_page_size(request, 100, 500)  # Higher default for chapters

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
            "is_dmca": novel.is_dmca,
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "chapters": serializer.data,
            "source_overview_image_url": (
                build_media_url(source.overview_picture_path)
                if source.overview_picture_path and os.path.exists(
                    resolve_output_path(source.overview_picture_path) or ""
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
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)

    if novel.is_dmca:
        return Response(
            {"error": "This work is unavailable due to a DMCA takedown request."},
            status=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
        )

    if not chapter.has_content:
        return Response(
            {"error": "Chapter content not available"}, status=status.HTTP_404_NOT_FOUND
        )

    # Increment views for the source (also updates its all-time projection)
    WeeklySourceView.increment_for_source(source)

    serializer = ChapterSerializer(chapter, profile='content')
    return Response(serializer.data)


@api_view(["GET"])
def source_image_gallery(request, novel_slug, source_slug):
    """
    Get all images from a specific source for gallery display
    """
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)

    # Get chapters with images
    chapters_with_images = (
        source.chapters.exclude(images=[])
        .order_by("chapter_id")
        .values_list("chapter_id", "title", "images")
    )

    # Check if there are any images available
    has_overview = source.overview_picture_path and os.path.exists(resolve_output_path(source.overview_picture_path) or "")
    total_images = chapters_with_images.aggregate(total=Sum(ArrayLength("images")))["total"] or 0
    if has_overview:
        total_images += 1
    if total_images == 0:
        return Response({"detail": "No images found for this source"}, status=status.HTTP_404_NOT_FOUND)

    # Pagination parameters
    page_size = parse_page_size(request, 20, 100)

    # Paginate over the image count only; rows are streamed below, so a source
    # with tens of thousands of images never lands in memory all at once.
    paginator = Paginator(range(total_images), page_size)
    page_obj = paginator.get_page(int(request.GET.get("page", 1)))
    start = (page_obj.number - 1) * page_size
    end = start + page_size

    # Prepare image data for the requested page
    image_data = []
    index = 0

    # Add the overview image if it exists
    if has_overview:
        if start <= index < end:
            image_data.append({
                "chapter_id": 0,  # Special ID for overview
                "chapter_title": "Novel Overview",
                "image_url": build_media_url(source.overview_picture_path),
                "image_name": "overview.png"
            })
        index += 1

    # Add chapter images, expanding only the slice for this page.
    image_dir = resolve_output_path(source.source_path, "images") or ""
    for chapter_id, chapter_title, images in chapters_with_images.iterator(chunk_size=500):
        for image_name in images:
            if index >= end:
                break
            # Skip files removed from disk so the gallery never links to a 404.
            # ponytail: total_images stays DB-derived, so a page can show gaps;
            # scan the directory if an exact count ever matters.
            if index >= start and os.path.exists(os.path.join(image_dir, image_name)):
                image_data.append({
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "image_url": build_media_url(f"{source.source_path}/images/{image_name}"),
                    "image_name": image_name
                })
            index += 1
        if index >= end:
            break

    serializer = GalleryImageSerializer(image_data, many=True)

    return Response({
        "novel_id": str(novel.id),
        "novel_title": novel.title,
        "novel_slug": novel.slug,
        "source_id": str(source.id),
        "source_name": source.external_source.source_name,
        "source_slug": source.source_slug,
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "images": serializer.data
    })


@api_view(["GET"])
def download_source_epub(request, novel_slug, source_slug):
    """
    Download the source as an EPUB. Pass ?volume=N for a single volume,
    omit it for the full novel. The book is generated on first request and
    cached inside the source folder.
    """
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)

    if novel.is_dmca:
        return Response(
            {"error": "This work is unavailable due to a DMCA takedown request."},
            status=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
        )

    raw_volume = request.GET.get("volume")
    if raw_volume in (None, ""):
        volume = None
    else:
        try:
            volume = int(raw_volume)
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid volume."}, status=status.HTTP_400_BAD_REQUEST
            )
        if not source.volumes.filter(volume_id=volume).exists():
            return Response(
                {"error": "Volume not found for this source."},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Cap the inline build so an unauthenticated request can't make the server
    # assemble a book with an unbounded number of chapters in one go.
    chapter_count = source.chapters.filter(has_content=True)
    if volume is not None:
        chapter_count = chapter_count.filter(volume=volume)
    chapter_count = chapter_count.count()
    if chapter_count > MAX_EPUB_CHAPTERS:
        return Response(
            {
                "error": (
                    f"This selection has {chapter_count} chapters (limit "
                    f"{MAX_EPUB_CHAPTERS}). Download it by volume instead."
                )
            },
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    try:
        path, filename = get_or_build_epub(source, volume)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

    response = FileResponse(
        open(path, "rb"), content_type="application/epub+zip", as_attachment=True
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response