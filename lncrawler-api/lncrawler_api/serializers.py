from rest_framework import serializers
from django.conf import settings
from .models.novels_models import (
    Novel, NovelFromSource, Chapter, Author, Genre, Tag,
    NovelViewCount, WeeklyNovelView
)
from django.db.models import Avg, F, ExpressionWrapper, IntegerField
from urllib.parse import quote


class BasicNovelSerializer(serializers.ModelSerializer):
    """
    Serializes basic novel information for list views
    """
    avg_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    total_views = serializers.SerializerMethodField()
    weekly_views = serializers.SerializerMethodField()
    prefered_source = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources_count', 'total_chapters',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'prefered_source'
        ]
    
    def get_prefered_source(self, obj):
        # Calculate vote score as upvotes - downvotes using annotate
        prefered_source = obj.sources.annotate(
            calc_score=ExpressionWrapper(F('upvotes') - F('downvotes'), output_field=IntegerField())
        ).order_by('-calc_score', '-upvotes', 'title').first()
        
        if prefered_source:
            return NovelSourceSerializer(prefered_source, context=self.context).data
        return None
    
    def get_avg_rating(self, obj):
        avg = obj.ratings.all().aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else None
    
    def get_rating_count(self, obj):
        return obj.ratings.count()
    
    def get_total_views(self, obj):
        view_count = NovelViewCount.objects.filter(novel=obj).first()
        return view_count.views if view_count else 0
    
    def get_weekly_views(self, obj):
        from datetime import datetime
        current_date = datetime.now()
        current_year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
        
        weekly_view = WeeklyNovelView.objects.filter(
            novel=obj,
            year_week=current_year_week
        ).first()
        return weekly_view.views if weekly_view else 0
    

class DetailedNovelSerializer(serializers.ModelSerializer):
    """
    Serializes detailed novel information including sources
    """
    sources = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    user_rating = serializers.SerializerMethodField()
    total_views = serializers.SerializerMethodField()
    weekly_views = serializers.SerializerMethodField()
    prefered_source = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources', 'created_at', 'updated_at',
            'avg_rating', 'rating_count', 'user_rating', 'total_views', 'weekly_views',
            'prefered_source'
        ]
    
    def get_sources(self, obj):
        return NovelSourceSerializer(
            obj.sources.all().order_by(('-upvotes')).reverse(),
            many=True,
            context=self.context
        ).data
    
    def get_prefered_source(self, obj):
        # Calculate vote score as upvotes - downvotes using annotate
        prefered_source = obj.sources.annotate(
            calc_score=ExpressionWrapper(F('upvotes') - F('downvotes'), output_field=IntegerField())
        ).order_by('-calc_score', '-upvotes', 'title').first()
        
        if prefered_source:
            return NovelSourceSerializer(prefered_source, context=self.context).data
        return None
    
    def get_avg_rating(self, obj):
        avg = obj.ratings.all().aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else None
    
    def get_rating_count(self, obj):
        return obj.ratings.count()
    
    def get_user_rating(self, obj):
        request = self.context.get('request')
        if not request:
            return None
            
        from .utils import get_client_ip
        client_ip = get_client_ip(request)
        if not client_ip:
            return None
            
        try:
            rating = obj.ratings.filter(ip_address=client_ip).first()
            return rating.rating if rating else None
        except:
            return None
    
    def get_total_views(self, obj):
        view_count = NovelViewCount.objects.filter(novel=obj).first()
        return view_count.views if view_count else 0
    
    def get_weekly_views(self, obj):
        from datetime import datetime
        current_date = datetime.now()
        current_year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
        
        weekly_view = WeeklyNovelView.objects.filter(
            novel=obj,
            year_week=current_year_week
        ).first()
        return weekly_view.views if weekly_view else 0


class NovelSourceSerializer(serializers.ModelSerializer):
    """
    Serializes novel source information
    """
    authors = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    vote_score = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    
    class Meta:
        model = NovelFromSource
        fields = [
            'id', 'title', 'source_url', 'source_name', 'source_slug', 'cover_path',
            'authors', 'genres', 'tags', 'language', 'status', 'synopsis',
            'chapters_count', 'volumes_count', 'last_chapter_update', 'upvotes', 'downvotes',
            'vote_score', 'user_vote', 'novel_id', 'novel_slug', 'novel_title', 'cover_url'
        ]

    def get_cover_url(self, obj):
        if obj.cover_path:
            return quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{obj.cover_path}", safe=':/')
            return 
        return None
    
    def get_authors(self, obj):
        return [author.name for author in obj.authors.all()]
    
    def get_genres(self, obj):
        return [genre.name for genre in obj.genres.all()]
    
    def get_tags(self, obj):
        return [tag.name for tag in obj.tags.all()]
    
    def get_user_vote(self, obj):
        request = self.context.get('request')
        if not request:
            return None
            
        from .utils import get_client_ip
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


class ChapterSerializer(serializers.ModelSerializer):
    """
    Serializes chapter information
    """
    class Meta:
        model = Chapter
        fields = ['id', 'chapter_id', 'title', 'url', 'volume', 'volume_title', 'has_content']   


class ChapterContentSerializer(serializers.ModelSerializer):
    """
    Serializes chapter content with navigation
    """
    body = serializers.SerializerMethodField()
    prev_chapter = serializers.SerializerMethodField()
    next_chapter = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    source_id = serializers.SerializerMethodField()
    source_name = serializers.SerializerMethodField() 
    source_slug = serializers.SerializerMethodField()
    
    class Meta:
        model = Chapter
        fields = [
            'id', 'chapter_id', 'title', 'novel_title', 'novel_id', 'novel_slug',
            'source_id', 'source_name', 'source_slug', 'body', 'prev_chapter', 'next_chapter'
        ]
    
    def get_body(self, obj):
        return obj.body
    
    def get_prev_chapter(self, obj):
        previous_chapter = obj.novel_from_source.chapters.filter(
            chapter_id__lt=obj.chapter_id
        ).order_by('-chapter_id').first()
        return previous_chapter.chapter_id if previous_chapter and previous_chapter.has_content else None
    
    def get_next_chapter(self, obj):
        next_chapter = obj.novel_from_source.chapters.filter(
            chapter_id__gt=obj.chapter_id
        ).order_by('chapter_id').first()
        return next_chapter.chapter_id if next_chapter and next_chapter.has_content else None
    
    def get_novel_title(self, obj):
        return obj.novel_from_source.novel.title
    
    def get_novel_id(self, obj):
        return str(obj.novel_from_source.novel.id)
    
    def get_novel_slug(self, obj):
        return obj.novel_from_source.novel.slug
    
    def get_source_id(self, obj):
        return str(obj.novel_from_source.id)
    
    def get_source_name(self, obj):
        return obj.novel_from_source.source_name
    
    def get_source_slug(self, obj):
        return obj.novel_from_source.source_slug


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['name']


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['name']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name']
