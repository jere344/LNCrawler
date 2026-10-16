from rest_framework import serializers
from ..models.chat_models import ChatMessage
from .users_serializers import UserSerializer

PARENT_PREVIEW_LENGTH = 200


class ChatMessageSerializer(serializers.ModelSerializer):
    """Serializes a chat message, with a short preview of the message it replies to."""
    user = UserSerializer(read_only=True, profile='compact')
    parent = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'author_name', 'message', 'contains_spoiler', 'created_at', 'edited', 'user', 'parent']
        read_only_fields = ['id', 'created_at', 'edited']

    def get_parent(self, obj):
        parent = obj.parent
        if not parent:
            return None
        return {
            'id': str(parent.id),
            'author_name': parent.author_name,
            'message': parent.message[:PARENT_PREVIEW_LENGTH],
        }
