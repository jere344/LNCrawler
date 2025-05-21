from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from ..models.users_models import NovelBookmark, ReadingHistory
from ..models.novels_models import Novel
from ..models.sources_models import NovelFromSource, Chapter
from ..serializers.novels_serializers import BasicNovelSerializer
from ..serializers.users_serializers import DetailedReadingHistorySerializer

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_novel_bookmark(request, novel_slug):
    """
    Bookmark a novel for the authenticated user.
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    bookmark, created = NovelBookmark.objects.get_or_create(user=request.user, novel=novel)

    if created:
        return Response({"status": "bookmarked", "bookmark_id": bookmark.id}, status=status.HTTP_201_CREATED)
    else:
        return Response({"status": "already bookmarked", "bookmark_id": bookmark.id}, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_novel_bookmark(request, novel_slug):
    """
    Remove a novel bookmark for the authenticated user.
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    try:
        bookmark = NovelBookmark.objects.get(user=request.user, novel=novel)
        bookmark.delete()
        return Response({"status": "bookmark removed"}, status=status.HTTP_204_NO_CONTENT)
    except NovelBookmark.DoesNotExist:
        return Response({"error": "Bookmark not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_bookmarked_novels(request):
    """
    List all novels bookmarked by the authenticated user.
    """
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)

    # Filter novels that are bookmarked by the current user
    bookmarked_novels = Novel.objects.filter(bookmarked_by_users__user=request.user).order_by('title')
    
    paginator = Paginator(bookmarked_novels, page_size)
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
@permission_classes([IsAuthenticated])
def list_reading_history(request):
    """
    List all novels with reading history for the authenticated user.
    """
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)

    # Get novels with reading history for the current user
    novels_with_history = Novel.objects.filter(reading_histories__user=request.user).order_by('-reading_histories__last_read_at')
    
    paginator = Paginator(novels_with_history, page_size)
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

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_reading_history(request, history_id):
    """
    Delete a reading history entry for the authenticated user.
    """
    try:
        history = ReadingHistory.objects.get(id=history_id, user=request.user)
        history.delete()
        return Response({"status": "history entry removed"}, status=status.HTTP_204_NO_CONTENT)
    except ReadingHistory.DoesNotExist:
        return Response({"error": "Reading history entry not found"}, status=status.HTTP_404_NOT_FOUND)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_chapter_as_read(request, novel_slug, source_slug, chapter_number):
    """
    Mark a chapter as read for the authenticated user.
    Updates or creates a reading history entry.
    """
    # Get the novel, source, and chapter
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(NovelFromSource, novel=novel, source_slug=source_slug)
    chapter = get_object_or_404(Chapter, novel_from_source=source, chapter_id=chapter_number)
    
    # Update or create reading history for this novel
    reading_history, created = ReadingHistory.objects.update_or_create(
        user=request.user,
        novel=novel,
        defaults={
            'source': source,
            'last_read_chapter': chapter
        }
    )
    
    serializer = DetailedReadingHistorySerializer(reading_history)
    
    if created:
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        return Response(serializer.data, status=status.HTTP_200_OK)
