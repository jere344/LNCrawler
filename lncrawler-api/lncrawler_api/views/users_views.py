from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Count, Q
from collections import Counter

from ..models.users_models import NovelBookmark, ReadingHistory
from ..models.novels_models import Novel, NovelSimilarity
from ..models.sources_models import NovelFromSource, Chapter
from ..serializers.novels_serializers import BasicNovelSerializer
from ..serializers.users_serializers import DetailedReadingHistorySerializer
from ..models.novels_models import NovelViewCount
from django.db.models import Case, When, IntegerField

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
    Also provides personalized novel recommendations based on bookmarks.
    """
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)

    # Filter novels that are bookmarked by the current user
    bookmarked_novels = Novel.objects.filter(bookmarked_by_users__user=request.user).order_by('title')
    
    # Get recommendations based on bookmarked novels
    recommendations = get_novel_recommendations(request.user, bookmarked_novels, max_recommendations=12)
    recommendation_serializer = BasicNovelSerializer(recommendations, many=True, context={"request": request})
    
    paginator = Paginator(bookmarked_novels, page_size)
    page_obj = paginator.get_page(page_number)

    serializer = BasicNovelSerializer(page_obj, many=True, context={"request": request})

    return Response(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": int(page_number),
            "results": serializer.data,
            "recommendations": recommendation_serializer.data,
        }
    )

def get_novel_recommendations(user, bookmarked_novels, max_recommendations=12):
    """
    Generate novel recommendations based on user's bookmarked novels.
    Optimized version that reduces database queries and performs most calculations at DB level.
    """
    if not bookmarked_novels.exists():
        return []

    bookmarked_ids = list(bookmarked_novels.values_list('id', flat=True))
    
    # Get recommendations with counts using a single database query
    from django.db.models import Count
    similar_novels = (NovelSimilarity.objects
        .filter(from_novel_id__in=bookmarked_ids)
        .exclude(to_novel_id__in=bookmarked_ids)  # Exclude already bookmarked novels
        .values('to_novel')
        .annotate(recommendation_count=Count('to_novel'))
        .order_by('-recommendation_count', '-similarity')[:max_recommendations]
    )
    
    # Get IDs of similar novels
    recommended_ids = [item['to_novel'] for item in similar_novels]
    
    # If we need more recommendations, add popular novels
    if len(recommended_ids) < max_recommendations:
        needed = max_recommendations - len(recommended_ids)
        excluded_ids = bookmarked_ids + recommended_ids
        
        # Get popular novels IDs in a single query
        popular_ids = (NovelViewCount.objects
            .exclude(novel_id__in=excluded_ids)
            .order_by('-views')
            .values_list('novel_id', flat=True)[:needed]
        )
        
        recommended_ids.extend(popular_ids)
    
    # Now fetch all novels in a single query, preserving order efficiently
    from django.db.models import Case, When, IntegerField
    preserved_order = Case(
        *[When(pk=pk, then=pos) for pos, pk in enumerate(recommended_ids)],
        output_field=IntegerField()
    )
    
    recommendations = Novel.objects.filter(pk__in=recommended_ids).order_by(preserved_order)
    
    return recommendations

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

    # we also update the user word_read count
    request.user.word_read += chapter.word_count
    request.user.save(update_fields=['word_read'])
    
    serializer = DetailedReadingHistorySerializer(reading_history)
    
    if created:
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        return Response(serializer.data, status=status.HTTP_200_OK)
