from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..models.novels_models import Novel
from ..models.users_models import ProfilePinnedNovel, ReadingList
from ..models.reviews_models import Review
from ..models.comments_models import Comment
from ..privacy import can_view
from functools import partial

from ..serializers.reviews_serializers import ReviewSerializer
from ..serializers.comments_serializers import CommentSerializer
from ..serializers.reading_lists_serializers import ReadingListSerializer
from ..serializers.users_serializers import UserSerializer
from ..utils.pagination import (
    paginated_response as _paginated_response, paginated_reviews_response,
)
from ..utils.responses import forbidden as _forbidden

User = get_user_model()

MAX_PINNED_NOVELS = 6


def _target(username):
    return get_object_or_404(User, username=username)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_public_profile(request, username):
    """Public profile header for a user (bio, banner, socials, pinned novels,
    plus stats/genres/recent reads when visibility allows)."""
    owner = _target(username)
    serializer = UserSerializer(owner, context={"request": request}, profile='public')
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_library(request, username):
    owner = _target(username)
    viewer = request.user
    if not can_view(viewer, owner, 'library'):
        return _forbidden("This user's library is private.")
    from .users_views import _library_response
    return _library_response(
        owner, viewer, request,
        show_notes=can_view(viewer, owner, 'library_notes'),
        show_ratings=can_view(viewer, owner, 'library_ratings'),
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def user_reviews(request, username):
    owner = _target(username)
    if not can_view(request.user, owner, 'reviews'):
        return _forbidden("This user's reviews are private.")
    reviews = (
        Review.objects
        .filter(user=owner)
        .select_related('novel', 'user')
        .prefetch_related('reactions__user')
    )
    return paginated_reviews_response(request, reviews, ReviewSerializer)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_comments(request, username):
    owner = _target(username)
    if not can_view(request.user, owner, 'comments'):
        return _forbidden("This user's comments are private.")
    comments = (
        Comment.objects
        .filter(user=owner)
        .select_related('user', 'novel', 'chapter__novel_from_source__novel')
        .prefetch_related('replies')
        .order_by('-created_at')
    )
    return _paginated_response(request, comments, partial(CommentSerializer, profile='profile'))


@api_view(["GET"])
@permission_classes([AllowAny])
def user_reading_lists(request, username):
    owner = _target(username)
    viewer = request.user
    is_owner = viewer.is_authenticated and viewer.id == owner.id
    if not is_owner and not can_view(viewer, owner, 'reading_lists'):
        return _forbidden("This user's reading lists are private.")
    query_set = (
        ReadingList.objects
        .filter(user=owner)
        .prefetch_related('items__novel', 'collaborators__user')
    )
    if not is_owner:
        query_set = query_set.filter(is_public=True)
    return _paginated_response(request, query_set.order_by('-updated_at'), ReadingListSerializer)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_friends(request, username):
    owner = _target(username)
    if not can_view(request.user, owner, 'friends'):
        return _forbidden("This user's friends are private.")
    from .friends_views import friend_user_queryset
    friends = friend_user_queryset(owner).order_by('username')
    return _paginated_response(
        request, friends, partial(UserSerializer, profile='compact')
    )


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def pinned_novel(request, novel_id):
    """Pin or unpin a novel on the authenticated user's own profile."""
    novel = get_object_or_404(Novel, id=novel_id)
    if request.method == "POST":
        pin, created = ProfilePinnedNovel.objects.get_or_create(user=request.user, novel=novel)
        if created and ProfilePinnedNovel.objects.filter(user=request.user).count() > MAX_PINNED_NOVELS:
            pin.delete()
            return Response(
                {"detail": f"You can pin at most {MAX_PINNED_NOVELS} novels."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"status": "pinned", "pin_id": pin.id},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
    ProfilePinnedNovel.objects.filter(user=request.user, novel=novel).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
