from rest_framework import serializers
from ..models import (
    Novel, Author, Genre, Tag,
    NovelViewCount, WeeklyNovelView,
    NovelBookmark
)
from django.db.models import Avg, F, ExpressionWrapper, IntegerField
from .sources_serializers import NovelSourceSerializer
from .users_serializers import DetailedReadingHistorySerializer
from ..utils import get_client_ip


class BasicNovelSerializer(serializers.ModelSerializer):
    """
    Serializes basic novel information for list views
    """
    avg_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    total_views = serializers.SerializerMethodField()
    weekly_views = serializers.SerializerMethodField()
    prefered_source = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    reading_history = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources_count',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'prefered_source', 'languages', 'is_bookmarked', 'comment_count',
            'reading_history'
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
    
    def get_languages(self, obj):
        """
        Returns a list of languages for the sources of the novel
        """
        languages = set()
        for source in obj.sources.all():
            if source.language:
                languages.add(source.language)
        return list(languages)

    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return NovelBookmark.objects.filter(novel=obj, user=request.user).exists()
        return None
    
    def get_reading_history(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            history = obj.reading_histories.filter(user=request.user).first()
            if history:
                return DetailedReadingHistorySerializer(history).data
        return None

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
    is_bookmarked = serializers.SerializerMethodField()
    reading_history = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources', 'created_at', 'updated_at',
            'avg_rating', 'rating_count', 'user_rating', 'total_views', 'weekly_views',
            'prefered_source', 'is_bookmarked', 'comment_count', 'reading_history'
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

    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return NovelBookmark.objects.filter(novel=obj, user=request.user).exists()
        return None

    def get_reading_history(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            history = obj.reading_histories.filter(user=request.user).first()
            if history:
                return DetailedReadingHistorySerializer(history).data


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
