from rest_framework import serializers

from ..models.users_models import Friendship
from .users_serializers import UserSerializer


class FriendshipSerializer(serializers.ModelSerializer):
    requester = UserSerializer(read_only=True, profile='compact')
    addressee = UserSerializer(read_only=True, profile='compact')

    class Meta:
        model = Friendship
        fields = ['id', 'requester', 'addressee', 'status', 'created_at']
        read_only_fields = fields
