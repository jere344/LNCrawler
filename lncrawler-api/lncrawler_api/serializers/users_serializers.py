from django.contrib.auth import get_user_model
from django.db.models import Count, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum
from rest_framework import serializers

from auth_app.serializers import SOCIAL_LINK_KEYS, absolute_media_url
from auth_app.models import PRIVACY_CHOICES, PRIVACY_SECTIONS

from ..languages import is_supported_language, normalize_language, parse_languages
from ..models.users_models import Friendship, NovelBookmark, ProfilePinnedNovel, ReadingHistory
from ..models.chapter_models import Chapter
from ..models.novels_models import Novel, Tag
from ..privacy import are_friends, can_view
from ..utils.query_helpers import novel_prefetch_objects
from .mixins import ProfileFieldsMixin

User = get_user_model()

RECENT_READS_LIMIT = 6


class UserSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """
    Serializes a user through one of three profiles.

    ``me`` is the owner's editable payload (default); ``compact`` is the tiny
    identity other payloads nest; ``public`` is the public profile header,
    whose section payloads (stats, genres, recent reads) are only included when
    the owner's privacy settings allow the requesting viewer.
    """
    profile_pic = serializers.ImageField(required=False, allow_null=True)
    banner = serializers.ImageField(required=False, allow_null=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)
    word_read = serializers.IntegerField(read_only=True)
    chapters_read_count = serializers.SerializerMethodField()
    chapters_not_read_yet_count = serializers.SerializerMethodField()
    pinned_novels = serializers.SerializerMethodField()
    friendship_status = serializers.SerializerMethodField()
    friend_count = serializers.SerializerMethodField()
    visibility = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    currently_reading = serializers.SerializerMethodField()
    top_genres = serializers.SerializerMethodField()
    recent_reads = serializers.SerializerMethodField()

    default_profile = 'me'
    field_profiles = {
        'me': [
            'id', 'username', 'email', 'profile_pic', 'banner', 'bio',
            'social_links', 'privacy_settings', 'date_joined', 'last_login',
            'word_read', 'chapters_read_count', 'chapters_not_read_yet_count',
            'preferred_ui_language', 'preferred_languages', 'language_filter_enabled',
            'discoverable', 'show_r18', 'pinned_novels',
        ],
        'compact': ['id', 'username', 'profile_pic'],
        'public': [
            'id', 'username', 'profile_pic', 'banner', 'bio', 'date_joined',
            'social_links', 'friendship_status', 'friend_count', 'visibility',
            'pinned_novels', 'stats', 'currently_reading', 'top_genres', 'recent_reads',
        ],
    }

    class Meta:
        model = User
        read_only_fields = (
            'id', 'date_joined', 'last_login', 'word_read',
            'chapters_read_count', 'chapters_not_read_yet_count',
        )

    def validate_social_links(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Provide an object of social links.")
        cleaned = {}
        for key, handle in value.items():
            if key not in SOCIAL_LINK_KEYS:
                raise serializers.ValidationError(f"Unknown social link '{key}'.")
            if handle in (None, ''):
                continue
            if not isinstance(handle, str) or len(handle) > 100:
                raise serializers.ValidationError(f"Invalid value for '{key}'.")
            cleaned[key] = handle
        return cleaned

    def validate_privacy_settings(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Provide an object of privacy settings.")
        cleaned = {}
        for section, visibility in value.items():
            if section not in PRIVACY_SECTIONS:
                raise serializers.ValidationError(f"Unknown privacy section '{section}'.")
            if visibility not in PRIVACY_CHOICES:
                raise serializers.ValidationError(
                    f"Visibility for '{section}' must be one of {PRIVACY_CHOICES}."
                )
            cleaned[section] = visibility
        return cleaned

    def validate_show_r18(self, value):
        if value not in ('yes', 'no', 'blur'):
            raise serializers.ValidationError("Must be one of 'yes', 'no', 'blur'.")
        return value

    def validate_preferred_ui_language(self, value):
        if value in (None, ''):
            return ''
        code = normalize_language(value)
        if not is_supported_language(code):
            raise serializers.ValidationError("Unsupported language code.")
        return code

    def validate_preferred_languages(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, (list, tuple, str)):
            raise serializers.ValidationError(
                "Provide a language code or a list of language codes."
            )
        codes = parse_languages(value)
        # An empty list clears the preference; a non-empty input that yields no
        # supported codes is rejected.
        if not codes and value:
            raise serializers.ValidationError(
                "Provide at least one supported language code."
            )
        return codes

    def get_pinned_novels(self, obj):
        from .novels_serializers import NovelSerializer
        from ..utils.query_helpers import adult_allowed
        pinned = ProfilePinnedNovel.objects.filter(user=obj)
        if not adult_allowed(self._viewer()):
            pinned = pinned.exclude(novel__sources__is_adult=True)
        pinned = (
            pinned
            .prefetch_related(
                Prefetch(
                    'novel',
                    queryset=Novel.objects.prefetch_related(
                        *novel_prefetch_objects(self._viewer())
                    ),
                )
            )
            .order_by('position', 'created_at')
        )
        return NovelSerializer(
            [pin.novel for pin in pinned], many=True, context=self.context
        ).data

    def get_chapters_read_count(self, obj):
        # Check if we've already calculated this
        if hasattr(self, '_chapters_read_count'):
            return self._chapters_read_count

        histories = ReadingHistory.objects.filter(
            user=obj,
            novel__in=NovelBookmark.objects.filter(user=obj).values('novel'),
            last_read_chapter__isnull=False
        ).select_related('source', 'last_read_chapter')

        total = 0
        for history in histories:
            total += Chapter.objects.filter(
                novel_from_source=history.source,
                has_content=True,
                chapter_id__lte=history.last_read_chapter.chapter_id
            ).count()

        self._chapters_read_count = total
        return self._chapters_read_count

    def get_chapters_not_read_yet_count(self, obj):
        # Get the total chapters count for bookmarked novels
        bookmarked_novels = NovelBookmark.objects.filter(user=obj).values('novel')
        total_chapters = Chapter.objects.filter(
            novel_from_source__novel__in=bookmarked_novels,
            has_content=True
        ).count()

        # Subtract the chapters already read
        chapters_read = self.get_chapters_read_count(obj)
        return max(0, total_chapters - chapters_read)

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
        cache_attr = f'_recent_history_cache_{obj.pk}'
        cache = getattr(self, cache_attr, None)
        if cache is None:
            from ..utils.query_helpers import adult_allowed
            history_qs = ReadingHistory.objects.filter(user=obj)
            if not adult_allowed(self._viewer()):
                history_qs = history_qs.exclude(novel__sources__is_adult=True)
            cache = list(
                history_qs
                .select_related('source', 'last_read_chapter')
                .prefetch_related(
                    Prefetch(
                        'novel',
                        queryset=Novel.objects.prefetch_related(
                            *novel_prefetch_objects(self._viewer())
                        ),
                    )
                )
                .order_by('-last_read_at')[:RECENT_READS_LIMIT]
            )
            setattr(self, cache_attr, cache)
        return cache

    def get_currently_reading(self, obj):
        if not can_view(self._viewer(), obj, 'reading_history'):
            return None
        histories = self._recent_history(obj)
        history = histories[0] if histories else None
        if not history:
            return None
        return {
            'novel': self._recent_novel(history.novel),
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
                'novel': self._recent_novel(history.novel),
                'last_read_at': history.last_read_at,
                'last_read_chapter': history.last_read_chapter.chapter_id if history.last_read_chapter else None,
            }
            for history in histories
        ]

    def _recent_novel(self, novel):
        from .novels_serializers import NovelSerializer
        return NovelSerializer(novel, context=self.context).data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ('profile_pic', 'banner'):
            if field in representation:
                representation[field] = absolute_media_url(
                    representation.get(field), self.context
                )
        return representation
