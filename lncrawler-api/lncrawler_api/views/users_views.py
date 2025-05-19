from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from ..models.users_models import NovelBookmark
from ..models.novels_models import Novel
from ..serializers.novels_serializers import BasicNovelSerializer # Reusing for listing bookmarked novels

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
