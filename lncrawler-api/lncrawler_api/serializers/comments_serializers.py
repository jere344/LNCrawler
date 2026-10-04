from rest_framework import serializers
from ..models.comments_models import Comment, CommentVote
from ..utils.ip_utils import get_client_ip
from auth_app.serializers import OtherUserSerializer


def chapter_comment_context(request, chapter):
    """Serializer context for ChapterCommentSerializer, derived from a chapter."""
    source = chapter.novel_from_source
    return {
        'request': request,
        'chapter_title': chapter.title,
        'chapter_id': chapter.chapter_id,
        'source_name': source.external_source.source_name,
        'source_slug': source.source_slug,
    }


class RecursiveCommentSerializer(serializers.Serializer):
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(instance, context=self.context)
        return serializer.data


class CommentSerializer(serializers.ModelSerializer):
    replies = RecursiveCommentSerializer(many=True, read_only=True)
    user = OtherUserSerializer(read_only=True)
    vote_score = serializers.IntegerField(read_only=True)
    upvotes = serializers.IntegerField(read_only=True)
    downvotes = serializers.IntegerField(read_only=True)
    has_replies = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    
    class Meta:
        model = Comment
        fields = [
            'id', 'author_name', 'message', 'contains_spoiler', 'created_at',
            'upvotes', 'downvotes', 'vote_score', 'user', 'replies', 'has_replies', 'user_vote'
        ]
        read_only_fields = ['id', 'created_at', 'upvotes', 'downvotes', 'vote_score']
    
    def get_has_replies(self, obj):
        return obj.replies.exists()

    def get_user_vote(self, obj):
        request = self.context.get('request')
        if request:
            ip_address = get_client_ip(request)
            vote = CommentVote.objects.filter(comment=obj, ip_address=ip_address).first()
            if vote:
                return vote.vote_type
        return None


class NovelCommentSerializer(CommentSerializer):
    type = serializers.CharField(default='novel', read_only=True)
    
    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + ['type', 'edited']


class ChapterCommentSerializer(CommentSerializer):
    #uses context data to add extra fields
    type = serializers.CharField(default='chapter', read_only=True)
    chapter_title = serializers.CharField(read_only=True)
    chapter_id = serializers.CharField(read_only=True)
    source_name = serializers.CharField(read_only=True)
    source_slug = serializers.CharField(read_only=True)

    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + ['type', 'chapter_title', 'chapter_id', 'source_name', 'source_slug', 'edited']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['chapter_title'] = self.context.get('chapter_title')
        data['chapter_id'] = self.context.get('chapter_id')
        data['source_name'] = self.context.get('source_name')
        data['source_slug'] = self.context.get('source_slug')
        return data

    


class CommentVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentVote
        fields = ['id', 'comment', 'vote_type', 'ip_address', 'created_at']
        read_only_fields = ['id', 'created_at', 'ip_address']
