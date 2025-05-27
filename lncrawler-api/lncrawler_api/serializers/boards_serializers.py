from rest_framework import serializers
from ..models.boards_models import Board
from .comments_serializers import CommentSerializer

class BoardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Board
        fields = ['id', 'name', 'slug', 'description', 'created_at', 'comment_count', 'is_active']
        read_only_fields = ['id', 'slug', 'created_at', 'comment_count']

class BoardCommentSerializer(CommentSerializer):
    type = serializers.CharField(default='board', read_only=True)
    board_name = serializers.CharField(read_only=True)
    board_slug = serializers.CharField(read_only=True)
    
    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + ['type', 'board_name', 'board_slug', 'edited']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['board_name'] = self.context.get('board_name')
        data['board_slug'] = self.context.get('board_slug')
        return data
