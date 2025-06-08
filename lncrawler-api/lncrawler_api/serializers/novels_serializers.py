from rest_framework import serializers
from ..models import (
    Novel, Author, Tag,
    NovelViewCount, WeeklyNovelView,
    NovelBookmark
)
from django.db.models import Avg, F, ExpressionWrapper, IntegerField, Subquery, OuterRef
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
    similar_novels = serializers.SerializerMethodField()
    reading_lists = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources', 'created_at', 'updated_at',
            'avg_rating', 'rating_count', 'user_rating', 'total_views', 'weekly_views',
            'prefered_source', 'is_bookmarked', 'comment_count', 'reading_history',
            'similar_novels', 'reading_lists'
        ]
    
    def get_sources(self, obj):
        return NovelSourceSerializer(
            obj.sources.all(),
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
        return None
        
    def get_similar_novels(self, obj):
        # Get the top 12 similar novels
        similar_novels = obj.similar_to.select_related('to_novel').order_by('-similarity')[:10]
        
        # If we don't have enough similar novels, get most viewed novels
        if similar_novels.count() < 12:
            # Get IDs of novels we already have
            existing_ids = list(similar_novels.values_list('to_novel_id', flat=True))
            needed_count = 12 - len(existing_ids)
            
            # Get the most viewed novels not already in our list
            most_viewed = NovelViewCount.objects.exclude(
                novel_id=obj.id
            ).exclude(
                novel_id__in=existing_ids
            ).order_by('-views')[:needed_count]
            
            # Combine the results
            result = list(similar_novels)
            for view_count in most_viewed:
                result.append({
                    'to_novel': view_count.novel,
                    'similarity': 0.0
                })
            similar_novels = result
        
        # Serialize the novels
        result = []
        for item in similar_novels:
            if hasattr(item, 'to_novel'):
                # Regular NovelSimilarity object
                novel_data = BasicNovelSerializer(item.to_novel, context=self.context).data
                novel_data['similarity'] = item.similarity
            else:
                # Dictionary from most viewed novels
                novel_data = BasicNovelSerializer(item['to_novel'], context=self.context).data
                novel_data['similarity'] = item['similarity']
            
            result.append(novel_data)
        
        return result
    
    def get_reading_lists(self, obj):
        from .reading_lists_serializers import ReadingListSerializer
        
        # Get all reading lists that contain this novel
        reading_lists = obj.in_reading_lists.values_list('reading_list', flat=True)
        from ..models.users_models import ReadingList
        lists = ReadingList.objects.filter(id__in=reading_lists)
        
        return ReadingListSerializer(lists, many=True, context=self.context).data


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['name']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name']
