from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import PasswordResetToken

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


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'password2', 'email', 'profile_pic')

    def validate(self, attrs):
        # Give the similarity validator a user-like object so it can compare
        # the password against the chosen username/email.
        user = User(username=attrs.get('username', ''), email=attrs.get('email', ''))
        validate_password(attrs['password'], user=user)
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
    new_password = serializers.CharField(required=True, write_only=True)
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        # Pass the requesting user so the similarity validator can compare
        # against username/email.
        validate_password(attrs['new_password'], user=self.context['request'].user)
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

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        # Resolve the token's user so the similarity validator has context.
        reset_token = (
            PasswordResetToken.objects
            .filter(token=PasswordResetToken.hash_token(attrs['token']))
            .first()
        )
        validate_password(
            attrs['new_password'],
            user=reset_token.user if reset_token else None,
        )
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs
