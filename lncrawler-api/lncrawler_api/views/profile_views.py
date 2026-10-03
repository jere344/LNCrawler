from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
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
from ..serializers.novels_serializers import BasicNovelSerializer
from ..serializers.reviews_serializers import ReviewListSerializer
from ..serializers.comments_serializers import CommentSerializer
from ..serializers.reading_lists_serializers import ReadingListSerializer
from ..serializers.profile_serializers import PublicUserSerializer
from auth_app.serializers import OtherUserSerializer
from .reading_lists_views import _paginated_response
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




def _forbidden(detail):
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


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
    if not can_view(request.user, owner, 'library'):
        return _forbidden("This user's library is private.")
    novels = (
        Novel.objects
        .filter(bookmarked_by_users__user=owner)
        .order_by('title')
    )
    return _paginated_response(request, novels, BasicNovelSerializer)


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
    page_number = request.GET.get('page', 1)
    page_size = min(int(request.GET.get('page_size', 20)), 50)
    paginator = Paginator(reviews, page_size)
    page_obj = paginator.get_page(page_number)
    serializer = ReviewListSerializer(page_obj, many=True, context={"request": request})
    return Response({
        'reviews': serializer.data,
        'pagination': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_reviews': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def user_comments(request, username):
    owner = _target(username)
    if not can_view(request.user, owner, 'comments'):
        return _forbidden("This user's comments are private.")
    comments = (
        Comment.objects
        .filter(user=owner)
        .select_related('user', 'novel', 'chapter', 'board')
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
    query_set = ReadingList.objects.filter(user=owner)
    if not is_owner:
        query_set = query_set.filter(is_public=True)
    return _paginated_response(request, query_set.order_by('-updated_at'), ReadingListSerializer)


@api_view(["GET"])
@permission_classes([AllowAny])
def user_friends(request, username):
    owner = _target(username)
    if not can_view(request.user, owner, 'friends'):
        return _forbidden("This user's friends are private.")
    from ..models.users_models import Friendship
    from django.db.models import Q
    friendships = (
        Friendship.objects
        .filter(status=Friendship.ACCEPTED)
        .filter(Q(requester=owner) | Q(addressee=owner))
        .select_related('requester', 'addressee')
    )
    friends = [
        friendship.addressee if friendship.requester_id == owner.id else friendship.requester
        for friendship in friendships
    ]
    serializer = OtherUserSerializer(friends, many=True, context={"request": request})
    return Response(serializer.data)


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
