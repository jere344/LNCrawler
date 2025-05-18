from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(required=False, allow_null=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'profile_pic', 'date_joined', 'last_login')
        read_only_fields = ('id', 'date_joined', 'last_login')
    
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
