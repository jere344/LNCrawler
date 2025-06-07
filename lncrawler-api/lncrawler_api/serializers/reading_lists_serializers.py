from rest_framework import serializers

from ..models.users_models import ReadingList, ReadingListItem
from auth_app.serializers import OtherUserSerializer
from .novels_serializers import BasicNovelSerializer

class ReadingListItemSerializer(serializers.ModelSerializer):
    novel = BasicNovelSerializer(read_only=True)
    novel_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = ReadingListItem
        fields = ['id', 'novel', 'novel_id', 'note', 'position', 'added_at']
        read_only_fields = ['id', 'added_at']
    
    def create(self, validated_data):
        return ReadingListItem.objects.create(**validated_data)


class ReadingListSerializer(serializers.ModelSerializer):
    user = OtherUserSerializer(read_only=True)
    items_count = serializers.SerializerMethodField()
    first_item = ReadingListItemSerializer(read_only=True, source='items.first')
    items_names = serializers.SerializerMethodField()
    
    class Meta:
        model = ReadingList
        fields = ['id', 'title', 'description', 'user', 'items_count', 'created_at', 'updated_at', 'first_item', 'items_names']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def get_items_count(self, obj):
        return obj.items.count()
    
    def get_items_names(self, obj):
        return [item.novel.title for item in obj.items.all() if item.novel]


class DetailedReadingListSerializer(serializers.ModelSerializer):
    user = OtherUserSerializer(read_only=True)
    items = ReadingListItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = ReadingList
        fields = ['id', 'title', 'description', 'user', 'items', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']