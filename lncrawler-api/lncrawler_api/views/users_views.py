from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, F, IntegerField, Max, OuterRef, Q, Subquery

import uuid

from ..models.users_models import LibraryFolder, NovelBookmark, ReadingHistory
from ..models.novels_models import Novel, NovelRating, NovelSimilarity
from ..models.sources_models import NovelFromSource, Chapter
from ..serializers.novels_serializers import NovelSerializer
from ..serializers.reading_history_serializers import ReadingHistorySerializer
from ..serializers.users_serializers import UserSerializer
from ..utils import resolve_novel_slug
from ..utils.pagination import parse_page_size, paginated_response
from ..utils.query_helpers import (
    adult_allowed,
    apply_novel_prefetches,
    exclude_adult,
)


def _folder_count_annotation(allow_adult):
    """Count a folder's bookmarks, hiding adult novels unless allowed.

    A novel is adult if ANY of its sources is, so this uses a subquery rather
    than a per-source-row filter (which would count mixed-source novels).
    """
    if allow_adult:
        return Count("bookmarks")
    adult_novel_ids = Novel.objects.filter(sources__is_adult=True).values("id")
    return Count(
        "bookmarks",
        filter=~Q(bookmarks__novel_id__in=adult_novel_ids),
        distinct=True,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_novel_bookmark(request, novel_slug):
    """
    Bookmark a novel for the authenticated user.
    """
    novel = resolve_novel_slug(novel_slug)
    try:
        bookmark, created = NovelBookmark.objects.get_or_create(user=request.user, novel=novel)
    except IntegrityError:
        bookmark = NovelBookmark.objects.get(user=request.user, novel=novel)
        created = False

    if created:
        last_position = (
            NovelBookmark.objects.filter(user=request.user)
            .exclude(pk=bookmark.pk)
            .aggregate(max_position=Max('position'))['max_position']
        )
        bookmark.position = (last_position + 1) if last_position is not None else 0
        bookmark.save(update_fields=['position'])
        return Response({"status": "bookmarked", "bookmark_id": bookmark.id}, status=status.HTTP_201_CREATED)
    else:
        return Response({"status": "already bookmarked", "bookmark_id": bookmark.id}, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_novel_bookmark(request, novel_slug):
    """
    Remove a novel bookmark for the authenticated user.
    """
    novel = resolve_novel_slug(novel_slug)
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
    List the authenticated user's library (bookmarks) with folders, custom
    order, notes and the user's own ratings.
    """
    return _library_response(
        request.user, request.user, request,
        show_notes=True, show_ratings=True, include_recommendations=True,
    )


def _folder_data(folder):
    return {
        "id": str(folder.id),
        "name": folder.name,
        "count": getattr(folder, "count", 0),
    }


def _library_response(owner, viewer, request, show_notes, show_ratings, include_recommendations=False):
    """
    Build the shared library payload for both the owner's library and the
    public profile mirror. `owner` owns the bookmarks; `viewer` is who is
    asking (may be anonymous).

    With sort=custom the whole set is returned unpaginated so drag & drop can
    reorder it; other sort modes paginate.
    """
    search = request.GET.get("search", "").strip()
    folder_param = request.GET.get("folder", "all")
    sort = request.GET.get("sort", "custom")
    page_number = request.GET.get("page", 1)
    page_size = parse_page_size(request, 24, 100)

    bookmarks = NovelBookmark.objects.filter(user=owner)
    allow_adult = adult_allowed(viewer)
    if not allow_adult:
        bookmarks = bookmarks.exclude(novel__sources__is_adult=True)

    if folder_param == "unfiled":
        bookmarks = bookmarks.filter(folder__isnull=True)
    elif folder_param and folder_param != "all":
        try:
            bookmarks = bookmarks.filter(folder_id=uuid.UUID(str(folder_param)))
        except (ValueError, TypeError):
            bookmarks = bookmarks.none()

    if search:
        bookmarks = bookmarks.filter(
            Q(novel__title__icontains=search)
            | Q(novel__sources__authors__name__icontains=search)
        ).distinct()

    owner_rating = Subquery(
        NovelRating.objects.filter(novel=OuterRef("novel_id"), user=owner).values("rating")[:1],
        output_field=IntegerField(),
    )
    bookmarks = bookmarks.select_related("folder").annotate(owner_rating=owner_rating)

    if sort == "title":
        bookmarks = bookmarks.order_by("novel__title")
    elif sort == "date_added":
        bookmarks = bookmarks.order_by("-created_at")
    elif sort == "rating" and show_ratings:
        bookmarks = bookmarks.order_by(F("owner_rating").desc(nulls_last=True), "novel__title")
    else:
        sort = "custom"
        bookmarks = bookmarks.order_by("position", "-created_at")

    folder_qs = LibraryFolder.objects.filter(user=owner)
    folder_qs = folder_qs.annotate(count=_folder_count_annotation(allow_adult))
    folders = [_folder_data(folder) for folder in folder_qs]

    # Resolve the viewer's own bookmark status up front so the serializer's
    # `is_bookmarked` never runs a query per row.
    viewer_bookmarked_ids = set()
    if getattr(viewer, "is_authenticated", False):
        viewer_bookmarked_ids = set(
            NovelBookmark.objects.filter(user=viewer).values_list("novel_id", flat=True)
        )

    if sort == "custom":
        page_items = list(bookmarks)
        count = len(page_items)
        total_pages, current_page = 1, 1
    else:
        paginator = Paginator(bookmarks, page_size)
        page_obj = paginator.get_page(page_number)
        page_items = list(page_obj)
        count, total_pages, current_page = paginator.count, paginator.num_pages, page_obj.number

    novels_by_id = {
        novel.id: novel
        for novel in apply_novel_prefetches(
            Novel.objects.filter(id__in=[bookmark.novel_id for bookmark in page_items]), viewer
        )
    }
    novels = []
    for bookmark in page_items:
        novel = novels_by_id[bookmark.novel_id]
        novel.library_bookmark = bookmark
        novel.user_bookmarks = [True] if novel.id in viewer_bookmarked_ids else []
        novels.append(novel)

    serializer = NovelSerializer(
        novels, many=True, profile='library',
        context={"request": request, "show_notes": show_notes, "show_ratings": show_ratings},
    )

    payload = {
        "count": count,
        "total_pages": total_pages,
        "current_page": current_page,
        "results": serializer.data,
        "folders": folders,
        "sort": sort,
    }
    if include_recommendations:
        recommendations = get_novel_recommendations(
            owner, Novel.objects.filter(bookmarked_by_users__user=owner), viewer
        )
        payload["recommendations"] = NovelSerializer(
            recommendations, many=True, context={"request": request}
        ).data
    return Response(payload)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def library_folders(request):
    """List or create the authenticated user's library folders."""
    if request.method == "POST":
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "Folder name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if LibraryFolder.objects.filter(user=request.user, name=name).exists():
            return Response(
                {"error": "A folder with this name already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        folder = LibraryFolder.objects.create(user=request.user, name=name)
        return Response(_folder_data(folder), status=status.HTTP_201_CREATED)

    folders = LibraryFolder.objects.filter(user=request.user).annotate(
        count=_folder_count_annotation(adult_allowed(request.user))
    )
    return Response([_folder_data(folder) for folder in folders])


@api_view(["PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def library_folder_detail(request, folder_id):
    """Rename or delete one of the authenticated user's library folders."""
    folder = get_object_or_404(LibraryFolder, id=folder_id, user=request.user)

    if request.method == "DELETE":
        folder.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    name = (request.data.get("name") or "").strip()
    if not name:
        return Response({"error": "Folder name is required."}, status=status.HTTP_400_BAD_REQUEST)
    if LibraryFolder.objects.filter(user=request.user, name=name).exclude(pk=folder.pk).exists():
        return Response(
            {"error": "A folder with this name already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    folder.name = name
    folder.save(update_fields=["name"])
    folder = LibraryFolder.objects.filter(pk=folder.pk).annotate(
        count=_folder_count_annotation(adult_allowed(request.user))
    ).get()
    return Response(_folder_data(folder))


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_library_item(request, bookmark_id):
    """Update the note and/or folder of one of the user's library items."""
    bookmark = get_object_or_404(NovelBookmark, id=bookmark_id, user=request.user)

    if "note" in request.data:
        note = request.data.get("note")
        bookmark.note = note if note else None
    if "folder" in request.data:
        folder_id = request.data.get("folder")
        if folder_id in (None, "", "null"):
            bookmark.folder = None
        else:
            bookmark.folder = get_object_or_404(LibraryFolder, id=folder_id, user=request.user)
    bookmark.save()

    return Response({
        "id": str(bookmark.id),
        "note": bookmark.note,
        "folder": str(bookmark.folder_id) if bookmark.folder_id else None,
        "position": bookmark.position,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reorder_library(request):
    """Persist a global custom order for the user's library items."""
    items = request.data
    if not isinstance(items, list):
        return Response(
            {"error": "Expected a list of {id, position}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    by_id = {str(bookmark.id): bookmark for bookmark in NovelBookmark.objects.filter(user=request.user)}
    updated = []
    for entry in items:
        bookmark = by_id.get(str(entry.get("id")))
        if not bookmark:
            continue
        try:
            bookmark.position = max(0, int(entry.get("position", 0)))
        except (TypeError, ValueError):
            continue
        updated.append(bookmark)

    if updated:
        NovelBookmark.objects.bulk_update(updated, ["position"])
    return Response({"status": "reordered", "count": len(updated)})

def get_novel_recommendations(user, bookmarked_novels, viewer=None, max_recommendations=12):
    """
    Generate novel recommendations based on user's bookmarked novels.
    Optimized version that reduces database queries and performs most calculations at DB level.
    """
    if not bookmarked_novels.exists():
        return []

    # ``viewer`` is who will see the recommendations (adult pref + bookmark
    # prefetch); defaults to the library owner for the self-view.
    viewer = viewer if viewer is not None else user
    allow_adult = adult_allowed(viewer)

    bookmarked_ids = list(bookmarked_novels.values_list('id', flat=True))
    
    # Get recommendations with counts using a single database query
    from django.db.models import Count, Max
    similar_qs = (NovelSimilarity.objects
        .filter(from_novel_id__in=bookmarked_ids)
        .exclude(to_novel_id__in=bookmarked_ids)  # Exclude already bookmarked novels
    )
    if not allow_adult:
        similar_qs = similar_qs.exclude(to_novel__sources__is_adult=True)
    similar_novels = (similar_qs
        .values('to_novel')
        .annotate(
            recommendation_count=Count('to_novel'),
            # Aggregate similarity so it lands in the SELECT, not the GROUP BY;
            # otherwise each distinct score yields a duplicate to_novel row.
            best_similarity=Max('similarity'),
        )
        .order_by('-recommendation_count', '-best_similarity')[:max_recommendations]
    )
    
    # Get IDs of similar novels
    recommended_ids = [item['to_novel'] for item in similar_novels]
    
    # If we need more recommendations, add popular novels
    if len(recommended_ids) < max_recommendations:
        needed = max_recommendations - len(recommended_ids)
        excluded_ids = bookmarked_ids + recommended_ids
        
        # Get popular novels IDs in a single query (summed over sources)
        from django.db.models import Sum
        popular_qs = Novel.objects.exclude(id__in=excluded_ids)
        if not allow_adult:
            popular_qs = popular_qs.exclude(sources__is_adult=True)
        popular_ids = (popular_qs
            .annotate(total_views=Sum('sources__total_views'))
            .order_by('-total_views')
            .values_list('id', flat=True)[:needed]
        )
        
        recommended_ids.extend(popular_ids)
    
    # Now fetch all novels in a single query, preserving order efficiently
    from django.db.models import Case, When, IntegerField
    preserved_order = Case(
        *[When(pk=pk, then=pos) for pos, pk in enumerate(recommended_ids)],
        output_field=IntegerField()
    )
    
    recommendations = apply_novel_prefetches(
        Novel.objects.filter(pk__in=recommended_ids).order_by(preserved_order), viewer
    )
    
    return recommendations

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_reading_history(request):
    """
    List all novels with reading history for the authenticated user.
    """
    # Get novels with reading history for the current user
    novels_with_history = apply_novel_prefetches(
        exclude_adult(
            Novel.objects.filter(reading_histories__user=request.user),
            request.user,
        ).order_by('-reading_histories__last_read_at'),
        request.user,
    )
    return paginated_response(
        request, novels_with_history, NovelSerializer, max_size=50
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
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(NovelFromSource, novel=novel, source_slug=source_slug)
    chapter = get_object_or_404(Chapter, novel_from_source=source, chapter_id=chapter_number)
    
    # Update or create reading history for this novel
    previous_chapter_id = (
        ReadingHistory.objects.filter(user=request.user, novel=novel)
        .values_list("last_read_chapter_id", flat=True)
        .first()
    )
    try:
        reading_history, created = ReadingHistory.objects.update_or_create(
            user=request.user,
            novel=novel,
            defaults={
                'source': source,
                'last_read_chapter': chapter
            }
        )
    except IntegrityError:
        reading_history = ReadingHistory.objects.get(user=request.user, novel=novel)
        created = False

    # Only count words when advancing to a different chapter, so revisiting a
    # chapter does not inflate the total. F() avoids lost updates under concurrency.
    if previous_chapter_id != chapter.id:
        body = chapter.body
        word_count = body.count(' ') if body else 0
        if word_count:
            get_user_model().objects.filter(pk=request.user.pk).update(
                word_read=F('word_read') + word_count
            )
    
    serializer = ReadingHistorySerializer(reading_history, profile='detail')
    
    if created:
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request):
    """
    Search users by username (case-insensitive), for adding list collaborators.
    """
    query = request.query_params.get("q", "").strip()
    if len(query) < 2:
        return Response([])

    users = (
        get_user_model().objects
        .filter(username__icontains=query, discoverable=True)
        .exclude(id=request.user.id)
        .order_by("username")[:20]
    )
    serializer = UserSerializer(users, many=True, context={"request": request}, profile='compact')
    return Response(serializer.data)
