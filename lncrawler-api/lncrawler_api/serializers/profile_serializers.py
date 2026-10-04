from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework import serializers

from auth_app.serializers import OtherUserSerializer, absolute_media_url
from auth_app.models import PRIVACY_SECTIONS

from ..models.users_models import Friendship, ProfilePinnedNovel, ReadingHistory
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
        return {section: obj.visibility(section) for section in PRIVACY_SECTIONS}

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
        from auth_app.serializers import UserSerializer
        data = UserSerializer(obj, context=self.context).data
        return {
            'word_read': data['word_read'],
            'chapters_read_count': data['chapters_read_count'],
            'chapters_not_read_yet_count': data['chapters_not_read_yet_count'],
            'novels_count': obj.novel_bookmarks.count(),
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
