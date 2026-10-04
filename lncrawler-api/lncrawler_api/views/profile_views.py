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
from ..serializers.reviews_serializers import ReviewListSerializer
from ..serializers.comments_serializers import CommentSerializer
from ..serializers.reading_lists_serializers import ReadingListSerializer
from ..serializers.profile_serializers import PublicUserSerializer
from auth_app.serializers import OtherUserSerializer
from ..utils.pagination import (
    paginated_response as _paginated_response, paginated_reviews_response,
)
from ..utils.responses import forbidden as _forbidden
from rest_framework import serializers as drf_serializers

User = get_user_model()

MAX_PINNED_NOVELS = 6


class ProfileCommentSerializer(CommentSerializer):
    """Comment plus the target it was posted on, for the profile comments tab."""
    target_type = drf_serializers.SerializerMethodField()
    target_title = drf_serializers.SerializerMethodField()
    target_slug = drf_serializers.SerializerMethodField()
    target_novel_slug = drf_serializers.SerializerMethodField()
    target_source_slug = drf_serializers.SerializerMethodField()
    target_chapter_number = drf_serializers.SerializerMethodField()

    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + [
            'target_type', 'target_title', 'target_slug',
            'target_novel_slug', 'target_source_slug', 'target_chapter_number',
        ]

    def _target(self, obj):
        if obj.novel_id:
            return 'novel', obj.novel
        if obj.chapter_id:
            return 'chapter', obj.chapter
        if obj.board_id:
            return 'board', obj.board
        return None, None

    def get_target_type(self, obj):
        return self._target(obj)[0]

    def get_target_title(self, obj):
        kind, target = self._target(obj)
        if target is None:
            return None
        if kind == 'chapter':
            return getattr(target, 'title', None) or f"Chapter {getattr(target, 'chapter_id', '')}"
        return getattr(target, 'title', None)

    def get_target_slug(self, obj):
        kind, target = self._target(obj)
        if target is None:
            return None
        if kind in ('novel', 'board'):
            return target.slug
        return None

    def get_target_novel_slug(self, obj):
        kind, target = self._target(obj)
        if kind == 'novel':
            return target.slug
        if kind == 'chapter':
            return target.novel_from_source.novel.slug
        return None

    def get_target_source_slug(self, obj):
        kind, target = self._target(obj)
        if kind == 'chapter':
            return target.novel_from_source.source_slug
        return None

    def get_target_chapter_number(self, obj):
        kind, target = self._target(obj)
        if kind == 'chapter':
            return target.chapter_id
        return None




def _target(username):
    return get_object_or_404(User, username=username)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_public_profile(request, username):
    """Public profile header for a user (bio, banner, socials, pinned novels,
    plus stats/genres/recent reads when visibility allows)."""
    owner = _target(username)
    serializer = PublicUserSerializer(owner, context={"request": request})
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
    return paginated_reviews_response(request, reviews, ReviewListSerializer)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_comments(request, username):
    owner = _target(username)
    if not can_view(request.user, owner, 'comments'):
        return _forbidden("This user's comments are private.")
    comments = (
        Comment.objects
        .filter(user=owner)
        .select_related('user', 'novel', 'chapter__novel_from_source__novel', 'board')
        .prefetch_related('replies')
        .order_by('-created_at')
    )
    return _paginated_response(request, comments, ProfileCommentSerializer)


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
    return _paginated_response(request, friends, OtherUserSerializer)


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
