from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Sum, Count
from lncrawler_api.models import NovelBookmark, ReadingHistory, Chapter

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(required=False, allow_null=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)
    word_read = serializers.IntegerField(read_only=True)
    chapters_read_count = serializers.SerializerMethodField()
    chapters_not_read_yet_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'profile_pic', 'date_joined', 'last_login', 
                 'word_read', 'chapters_read_count', 'chapters_not_read_yet_count')
        read_only_fields = ('id', 'date_joined', 'last_login', 'word_read', 
                           'chapters_read_count', 'chapters_not_read_yet_count')
    
    def get_chapters_read_count(self, obj):
        # Check if we've already calculated this
        if hasattr(self, '_chapters_read_count'):
            return self._chapters_read_count
            
        # Calculate and cache the result
        self._chapters_read_count = ReadingHistory.objects.filter(
            user=obj,
            novel__in=NovelBookmark.objects.filter(user=obj).values('novel'),
            last_read_chapter__isnull=False
        ).aggregate(
            total=Sum('last_read_chapter__chapter_id')
        ).get('total') or 0
        
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
        
        profile_pic_url = representation.get('profile_pic')

        if profile_pic_url and not profile_pic_url.startswith('http'):
            request = self.context.get('request')
            if request:
                representation['profile_pic'] = request.build_absolute_uri(profile_pic_url)
            else:
                formatted_url = profile_pic_url if profile_pic_url.startswith('/') else f'/{profile_pic_url}'
                representation['profile_pic'] = f"{settings.SITE_API_URL}{formatted_url}"

        # If profile_pic_url is None or already absolute (starts with 'http'), 
        # it remains as is from super(), which is correct.
            
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
