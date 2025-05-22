from rest_framework import serializers
from django.conf import settings
from ..models import NovelFromSource
from urllib.parse import quote
from ..utils import get_client_ip
from .users_serializers import ReadingHistorySerializer
from .chapter_serializers import ChapterSerializer


class NovelSourceSerializer(serializers.ModelSerializer):
    """
    Serializes novel source information
    """
    authors = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    vote_score = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    latest_available_chapter = serializers.SerializerMethodField()
    reading_history = serializers.SerializerMethodField()
    
    class Meta:
        model = NovelFromSource
        fields = [
            'id', 'title', 'source_url', 'source_name', 'source_slug', 'cover_path',
            'authors', 'tags', 'language', 'status', 'synopsis',
            'chapters_count', 'volumes_count', 'last_chapter_update', 'upvotes', 'downvotes',
            'vote_score', 'user_vote', 'novel_id', 'novel_slug', 'novel_title', 'cover_url',
            'latest_available_chapter', 'reading_history'
        ]

    def get_cover_url(self, obj):
        if obj.cover_path:
            return quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{obj.cover_path}", safe=':/')
        return None
    
    def get_authors(self, obj):
        return [author.name for author in obj.authors.all()]
    
    def get_tags(self, obj):
        return [tag.name for tag in obj.tags.all()]
    
    def get_user_vote(self, obj):
        request = self.context.get('request')
        if not request:
            return None
            
        client_ip = get_client_ip(request)
        if not client_ip:
            return None
            
        try:
            vote = obj.votes.filter(ip_address=client_ip).first()
            return vote.vote_type if vote else None
        except:
            return None

    def get_novel_id(self, obj):
        return str(obj.novel.id) if obj.novel else None

    def get_novel_slug(self, obj):
        return obj.novel.slug if obj.novel else None

    def get_novel_title(self, obj):
        return obj.novel.title if obj.novel else None

    def get_vote_score(self, obj):
        return obj.upvotes - obj.downvotes
    
    def get_latest_available_chapter(self, obj):
        """Return the latest available chapter with content"""
        latest_chapter = obj.chapters.filter(has_content=True).order_by('-chapter_id').first()
        if latest_chapter:
            return ChapterSerializer(latest_chapter).data
        return None
    
    def get_reading_history(self, obj):
        """
        Return the reading history for the current user
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            history = obj.read_by_users.filter(user=request.user).first()
            if history:
                return ReadingHistorySerializer(history).data
        return None

