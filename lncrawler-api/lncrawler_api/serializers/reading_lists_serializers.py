from rest_framework import serializers

from ..models.users_models import ReadingList, ReadingListItem, ReadingListCollaborator
from auth_app.serializers import OtherUserSerializer
from .novels_serializers import BasicNovelSerializer


def get_reading_list_role(reading_list, user):
    """Return owner/editor/reader for a user on a list, or None."""
    if not user or not user.is_authenticated:
        return None
    if reading_list.user_id == user.id:
        return 'owner'
    collaborator = reading_list.collaborators.filter(user=user).first()
    return collaborator.role if collaborator else None


class ReadingListItemSerializer(serializers.ModelSerializer):
    novel = BasicNovelSerializer(read_only=True)
    novel_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = ReadingListItem
        fields = ['id', 'novel', 'novel_id', 'note', 'position', 'added_at']
        read_only_fields = ['id', 'added_at']


class ReadingListCollaboratorSerializer(serializers.ModelSerializer):
    user = OtherUserSerializer(read_only=True)
    
    class Meta:
        model = ReadingListCollaborator
        fields = ['id', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class ReadingListSerializer(serializers.ModelSerializer):
    user = OtherUserSerializer(read_only=True)
    user_role = serializers.SerializerMethodField()
    collaborators = ReadingListCollaboratorSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    first_item = ReadingListItemSerializer(read_only=True, source='items.first')
    items_names = serializers.SerializerMethodField()
    
    class Meta:
        model = ReadingList
        fields = ['id', 'title', 'description', 'is_public', 'user', 'user_role',
                  'collaborators', 'items_count', 'created_at', 'updated_at',
                  'first_item', 'items_names']
        read_only_fields = ['id', 'user', 'user_role', 'collaborators', 'created_at', 'updated_at']
    
    def get_user_role(self, obj):
        request = self.context.get('request')
        return get_reading_list_role(obj, getattr(request, 'user', None))
    
    def get_items_count(self, obj):
        return obj.items.count()
    
    def get_items_names(self, obj):
        return [item.novel.title for item in obj.items.all() if item.novel]


class DetailedReadingListSerializer(serializers.ModelSerializer):
    user = OtherUserSerializer(read_only=True)
    user_role = serializers.SerializerMethodField()
    collaborators = ReadingListCollaboratorSerializer(many=True, read_only=True)
    items = ReadingListItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = ReadingList
        fields = ['id', 'title', 'description', 'is_public', 'user', 'user_role',
                  'collaborators', 'items', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'user_role', 'collaborators', 'created_at', 'updated_at']
    
    def get_user_role(self, obj):
        request = self.context.get('request')
        return get_reading_list_role(obj, getattr(request, 'user', None))
