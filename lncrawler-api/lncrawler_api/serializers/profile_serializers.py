from django.contrib.auth import get_user_model
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Sum
from rest_framework import serializers

from auth_app.serializers import OtherUserSerializer, absolute_media_url
from auth_app.models import PRIVACY_SECTIONS

from ..models.users_models import Friendship, NovelBookmark, ProfilePinnedNovel, ReadingHistory
from ..models.chapter_models import Chapter
from ..models.novels_models import Tag
from ..privacy import are_friends, can_view
from .novels_serializers import BasicNovelSerializer

User = get_user_model()

RECENT_READS_LIMIT = 6


class PublicUserSerializer(serializers.ModelSerializer):
    """
    Public-facing profile header. Section payloads (stats, genres, recent reads)
    are only included when the owner's privacy settings allow the requesting
    viewer; otherwise the field is null. Pinned novels are always shown.
    """
    profile_pic = serializers.ImageField(read_only=True)
    banner = serializers.ImageField(read_only=True)
    friendship_status = serializers.SerializerMethodField()
    friend_count = serializers.SerializerMethodField()
    visibility = serializers.SerializerMethodField()
    pinned_novels = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    currently_reading = serializers.SerializerMethodField()
    top_genres = serializers.SerializerMethodField()
    recent_reads = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'profile_pic', 'banner', 'bio', 'date_joined',
            'social_links', 'friendship_status', 'friend_count', 'visibility',
            'pinned_novels', 'stats', 'currently_reading', 'top_genres', 'recent_reads',
        ]

    def _viewer(self):
        return getattr(self.context.get('request'), 'user', None)

    def get_friendship_status(self, obj):
        viewer = self._viewer()
        if viewer is not None and getattr(viewer, 'is_authenticated', False) and viewer.id == obj.id:
            return 'self'
        if are_friends(viewer, obj):
            return 'friends'
        if viewer is None or not getattr(viewer, 'is_authenticated', False):
            return 'none'
        if Friendship.objects.filter(requester=viewer, addressee=obj, status=Friendship.PENDING).exists():
            return 'request_sent'
        if Friendship.objects.filter(requester=obj, addressee=viewer, status=Friendship.PENDING).exists():
            return 'request_received'
        return 'none'

    def get_friend_count(self, obj):
        if not can_view(self._viewer(), obj, 'friends'):
            return None
        return Friendship.objects.filter(status=Friendship.ACCEPTED).filter(
            Q(requester=obj) | Q(addressee=obj)
        ).count()

    def get_visibility(self, obj):
        viewer = self._viewer()
        return {
            section: 'public' if can_view(viewer, obj, section) else 'private'
            for section in PRIVACY_SECTIONS
        }

    def get_pinned_novels(self, obj):
        pins = (
            ProfilePinnedNovel.objects
            .filter(user=obj)
            .select_related('novel')
            .order_by('position', 'created_at')
        )
        return BasicNovelSerializer(
            [pin.novel for pin in pins], many=True, context=self.context
        ).data

    def get_stats(self, obj):
        if not can_view(self._viewer(), obj, 'stats'):
            return None
        bookmarked = NovelBookmark.objects.filter(user=obj).values('novel')
        chapters_read = (
            ReadingHistory.objects
            .filter(user=obj, novel__in=bookmarked, last_read_chapter__isnull=False)
            .annotate(last_chapter_id=F('last_read_chapter__chapter_id'))
            .annotate(read_count=Subquery(
                Chapter.objects
                .filter(
                    novel_from_source=OuterRef('source_id'),
                    has_content=True,
                    chapter_id__lte=OuterRef('last_chapter_id'),
                )
                .order_by()
                .values('novel_from_source')
                .annotate(c=Count('*'))
                .values('c')[:1],
                output_field=IntegerField(),
            ))
            .aggregate(total=Sum('read_count'))['total']
        ) or 0
        total_chapters = Chapter.objects.filter(
            novel_from_source__novel__in=bookmarked, has_content=True
        ).count()
        return {
            'word_read': obj.word_read,
            'chapters_read_count': chapters_read,
            'chapters_not_read_yet_count': max(0, total_chapters - chapters_read),
            'novels_count': NovelBookmark.objects.filter(user=obj).count(),
        }

    def _recent_history(self, obj):
        return (
            ReadingHistory.objects
            .filter(user=obj)
            .select_related('novel', 'source', 'last_read_chapter')
            .order_by('-last_read_at')[:RECENT_READS_LIMIT]
        )

    def get_currently_reading(self, obj):
        if not can_view(self._viewer(), obj, 'reading_history'):
            return None
        history = self._recent_history(obj).first()
        if not history:
            return None
        return {
            'novel': BasicNovelSerializer(history.novel, context=self.context).data,
            'last_read_at': history.last_read_at,
            'last_read_chapter': history.last_read_chapter.chapter_id if history.last_read_chapter else None,
            'source_slug': history.source.source_slug if history.source else None,
        }

    def get_top_genres(self, obj):
        if not can_view(self._viewer(), obj, 'stats'):
            return None
        rows = (
            Tag.objects
            .filter(novels__novel__bookmarked_by_users__user=obj)
            .values('name')
            .annotate(count=Count('novels__novel', distinct=True))
            .order_by('-count', 'name')[:5]
        )
        return [{'name': row['name'], 'count': row['count']} for row in rows]

    def get_recent_reads(self, obj):
        if not can_view(self._viewer(), obj, 'reading_history'):
            return None
        histories = self._recent_history(obj)
        return [
            {
                'novel': BasicNovelSerializer(history.novel, context=self.context).data,
                'last_read_at': history.last_read_at,
                'last_read_chapter': history.last_read_chapter.chapter_id if history.last_read_chapter else None,
            }
            for history in histories
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ('profile_pic', 'banner'):
            representation[field] = absolute_media_url(representation.get(field), self.context)
        return representation


class FriendshipSerializer(serializers.ModelSerializer):
    requester = OtherUserSerializer(read_only=True)
    addressee = OtherUserSerializer(read_only=True)

    class Meta:
        model = Friendship
        fields = ['id', 'requester', 'addressee', 'status', 'created_at']
        read_only_fields = fields
