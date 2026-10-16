from rest_framework import serializers
from ..models.comments_models import Comment, CommentVote
from ..utils.ip_utils import get_client_ip
from .users_serializers import UserSerializer
from .mixins import ProfileFieldsMixin


def chapter_comment_context(request, chapter):
    """Serializer context for the chapter comment profile, derived from a chapter."""
    source = chapter.novel_from_source
    return {
        'request': request,
        'chapter_title': chapter.title,
        'chapter_id': chapter.chapter_id,
        'source_name': source.external_source.source_name,
        'source_slug': source.source_slug,
    }


class CommentSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """Serializes a comment through one of several profiles.

    ``novel`` is the default comment thread; ``chapter`` adds the target
    labels carried in the serializer context; ``profile`` adds the target a
    comment was posted on (for the profile comments tab).
    """
    replies = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True, profile='compact')
    vote_score = serializers.IntegerField(read_only=True)
    upvotes = serializers.IntegerField(read_only=True)
    downvotes = serializers.IntegerField(read_only=True)
    has_replies = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    edited = serializers.BooleanField(read_only=True)
    chapter_title = serializers.SerializerMethodField()
    chapter_id = serializers.SerializerMethodField()
    source_name = serializers.SerializerMethodField()
    source_slug = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_title = serializers.SerializerMethodField()
    target_slug = serializers.SerializerMethodField()
    target_novel_slug = serializers.SerializerMethodField()
    target_source_slug = serializers.SerializerMethodField()
    target_chapter_number = serializers.SerializerMethodField()

    default_profile = 'novel'
    _base_fields = [
        'id', 'author_name', 'message', 'contains_spoiler', 'created_at',
        'upvotes', 'downvotes', 'vote_score', 'user', 'replies', 'has_replies',
        'user_vote',
    ]
    field_profiles = {
        'novel': _base_fields + ['type', 'edited'],
        'chapter': _base_fields + [
            'type', 'chapter_title', 'chapter_id', 'source_name', 'source_slug', 'edited',
        ],
        'profile': _base_fields + [
            'target_type', 'target_title', 'target_slug',
            'target_novel_slug', 'target_source_slug', 'target_chapter_number',
        ],
    }

    class Meta:
        model = Comment
        read_only_fields = ['id', 'created_at', 'upvotes', 'downvotes', 'vote_score']

    def get_replies(self, obj):
        # The thread views pass the whole reply tree as a prebuilt
        # ``comment_children`` map so the recursion never queries. Elsewhere
        # (single comment, profile tab) fall back to the related manager, which
        # is a no-op when the caller prefetched ``replies``.
        children = self.context.get('comment_children')
        if children is not None:
            replies = children.get(obj.id, [])
        else:
            replies = obj.replies.all()
        return [
            CommentSerializer(reply, context=self.context, profile=self.profile).data
            for reply in replies
        ]

    def get_has_replies(self, obj):
        children = self.context.get('comment_children')
        if children is not None:
            return bool(children.get(obj.id))
        if 'replies' in getattr(obj, '_prefetched_objects_cache', {}):
            return len(obj.replies.all()) > 0
        return obj.replies.exists()

    def get_user_vote(self, obj):
        # Batch path: the thread views precompute {comment_id: vote_type} for
        # the viewer in one query and drop it in the context.
        if 'comment_user_votes' in self.context:
            return self.context['comment_user_votes'].get(obj.id)
        request = self.context.get('request')
        if request:
            ip_address = get_client_ip(request)
            vote = CommentVote.objects.filter(comment=obj, ip_address=ip_address).first()
            if vote:
                return vote.vote_type
        return None

    def get_type(self, obj):
        return self.profile

    def get_chapter_title(self, obj):
        return self.context.get('chapter_title')

    def get_chapter_id(self, obj):
        return self.context.get('chapter_id')

    def get_source_name(self, obj):
        return self.context.get('source_name')

    def get_source_slug(self, obj):
        return self.context.get('source_slug')

    def _target(self, obj):
        if obj.novel_id:
            return 'novel', obj.novel
        if obj.chapter_id:
            return 'chapter', obj.chapter
        return None, None

    def get_target_type(self, obj):
        return self._target(obj)[0]

    def get_target_title(self, obj):
        kind, target = self._target(obj)
        if target is None:
            return None
        if kind == 'chapter':
            return getattr(target, 'title', None) or f"Chapter {getattr(target, 'chapter_id', '')}"
        return getattr(target, 'title', None)

    def get_target_slug(self, obj):
        kind, target = self._target(obj)
        if target is None:
            return None
        if kind == 'novel':
            return target.slug
        return None

    def get_target_novel_slug(self, obj):
        kind, target = self._target(obj)
        if kind == 'novel':
            return target.slug
        if kind == 'chapter':
            return target.novel_from_source.novel.slug
        return None

    def get_target_source_slug(self, obj):
        kind, target = self._target(obj)
        if kind == 'chapter':
            return target.novel_from_source.source_slug
        return None

    def get_target_chapter_number(self, obj):
        kind, target = self._target(obj)
        if kind == 'chapter':
            return target.chapter_id
        return None


class CommentVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentVote
        fields = ['id', 'comment', 'vote_type', 'ip_address', 'created_at']
        read_only_fields = ['id', 'created_at', 'ip_address']
