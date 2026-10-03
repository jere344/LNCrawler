from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from lncrawler_api.models import NovelBookmark, ReadingHistory, Chapter
from lncrawler_api.languages import normalize_language, is_supported_language, parse_languages
from .models import PRIVACY_SECTIONS, PRIVACY_CHOICES

User = get_user_model()

# Allowlisted social profile keys. Kept small so we never render arbitrary
# user-controlled keys on the public profile.
SOCIAL_LINK_KEYS = ('mal', 'anilist', 'novelupdates', 'discord', 'x', 'website')


def absolute_media_url(url, context=None):
    """Turn a stored MEDIA path into an absolute URL for API responses."""
    if not url or url.startswith('http'):
        return url
    request = (context or {}).get('request')
    if request:
        return request.build_absolute_uri(url)
    formatted_url = url if url.startswith('/') else f'/{url}'
    return f"{settings.SITE_API_URL}{formatted_url}"


class UserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(required=False, allow_null=True)
    banner = serializers.ImageField(required=False, allow_null=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)
    word_read = serializers.IntegerField(read_only=True)
    chapters_read_count = serializers.SerializerMethodField()
    chapters_not_read_yet_count = serializers.SerializerMethodField()
    pinned_novels = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'profile_pic', 'banner', 'bio',
                 'social_links', 'privacy_settings', 'date_joined', 'last_login', 
                 'word_read', 'chapters_read_count', 'chapters_not_read_yet_count',
                 'preferred_ui_language', 'preferred_languages', 'language_filter_enabled',
                 'pinned_novels')
        read_only_fields = ('id', 'date_joined', 'last_login', 'word_read', 
                           'chapters_read_count', 'chapters_not_read_yet_count')

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
        from lncrawler_api.serializers import BasicNovelSerializer
        from lncrawler_api.models import ProfilePinnedNovel
        pinned = ProfilePinnedNovel.objects.filter(user=obj).select_related('novel').order_by('position', 'created_at')
        return BasicNovelSerializer([p.novel for p in pinned], many=True, context=self.context).data

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
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ('profile_pic', 'banner'):
            if field in representation:
                representation[field] = absolute_media_url(representation.get(field), self.context)
        return representation

class OtherUserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'profile_pic')

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
        profile_pic_url = representation.get('profile_pic')

        if profile_pic_url and not profile_pic_url.startswith('http'):
            request = self.context.get('request')
            if request:
                representation['profile_pic'] = request.build_absolute_uri(profile_pic_url)
            else:
                formatted_url = profile_pic_url if profile_pic_url.startswith('/') else f'/{profile_pic_url}'
                representation['profile_pic'] = f"{settings.SITE_API_URL}{formatted_url}"

        return representation

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'password2', 'email', 'profile_pic')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "New password fields didn't match."})
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email address.")
        return value

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField(required=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs
