from rest_framework import serializers
from ..models import (
    Novel, Author, Tag,
    WeeklySourceView,
    NovelBookmark
)
from django.db.models import Avg, Sum
from .sources_serializers import NovelSourceSerializer
from .users_serializers import DetailedReadingHistorySerializer
from ..utils import get_client_ip


class NovelAggregatesMixin:
    """Computes the read-only counters shared by the list and detail
    serializers. When the queryset was built with `apply_novel_prefetches`
    everything is served from the prefetch cache (zero extra queries);
    otherwise it falls back to the original per-object queries."""

    # Detail views opt into the heavier nested source payload (synopsis etc.).
    source_detail_context = False

    def _prefetched(self, obj, name):
        return name in getattr(obj, '_prefetched_objects_cache', {})

    def get_prefered_source(self, obj):
        # Restrict to the languages the request was filtered by (when any), so
        # a language-filtered list links to a source in that language; fall
        # back to all sources if none match.
        sources = list(obj.sources.all())
        languages = self.context.get('languages') or []
        if languages:
            localized = [s for s in sources if s.language in languages]
            if localized:
                sources = localized

        if not sources:
            return None

        # Highest vote score, then most upvotes, then title.
        prefered = min(
            sources,
            key=lambda s: (-(s.upvotes - s.downvotes), -s.upvotes, s.title or ''),
        )
        context = self.context
        if self.source_detail_context:
            context = {**context, 'include_synopsis': True}
        return NovelSourceSerializer(prefered, context=context).data

    def get_avg_rating(self, obj):
        if self._prefetched(obj, 'ratings'):
            ratings = [rating.rating for rating in obj.ratings.all()]
            return round(sum(ratings) / len(ratings), 1) if ratings else None
        avg = obj.ratings.all().aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else None

    def get_rating_count(self, obj):
        if self._prefetched(obj, 'ratings'):
            return len(obj.ratings.all())
        return obj.ratings.count()

    def get_total_views(self, obj):
        if self._prefetched(obj, 'sources'):
            return sum(source.total_views for source in obj.sources.all())
        return obj.sources.aggregate(total=Sum('total_views'))['total'] or 0

    def get_weekly_views(self, obj):
        sources = obj.sources.all()
        if self._prefetched(obj, 'sources') and all(
            self._prefetched(source, 'weekly_views') for source in sources
        ):
            return sum(
                view.views for source in sources for view in source.weekly_views.all()
            )
        total = WeeklySourceView.objects.filter(
            source__novel=obj,
            granularity=WeeklySourceView.DAY,
            day__gte=WeeklySourceView.window_start(),
        ).aggregate(total=Sum('views'))['total']
        return total or 0

    def get_is_bookmarked(self, obj):
        if hasattr(obj, 'user_bookmarks'):
            return bool(obj.user_bookmarks)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return NovelBookmark.objects.filter(novel=obj, user=request.user).exists()
        return None

    def _get_reading_history(self, obj):
        if hasattr(obj, 'user_histories'):
            return obj.user_histories[0] if obj.user_histories else None
        cache = getattr(self, '_history_cache', None)
        if cache is None:
            cache = self._history_cache = {}
        if obj.pk not in cache:
            request = self.context.get('request')
            history = None
            if request and request.user.is_authenticated:
                history = obj.reading_histories.select_related('source').filter(user=request.user).first()
            cache[obj.pk] = history
        return cache[obj.pk]

    def get_reading_history(self, obj):
        history = self._get_reading_history(obj)
        return DetailedReadingHistorySerializer(history).data if history else None

    def get_reading_source(self, obj):
        history = self._get_reading_history(obj)
        if history and history.source:
            context = self.context
            if self.source_detail_context:
                context = {**context, 'include_synopsis': True}
            return NovelSourceSerializer(history.source, context=context).data
        return None


class BasicNovelSerializer(NovelAggregatesMixin, serializers.ModelSerializer):
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
    reading_source = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources_count',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'prefered_source', 'languages', 'is_bookmarked', 'comment_count',
            'reading_history', 'reading_source'
        ]

    def get_languages(self, obj):
        """
        Returns a list of languages for the sources of the novel
        """
        languages = set()
        for source in obj.sources.all():
            if source.language:
                languages.add(source.language)
        return list(languages)


class DetailedNovelSerializer(NovelAggregatesMixin, serializers.ModelSerializer):
    """
    Serializes detailed novel information including sources
    """
    source_detail_context = True

    sources = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    user_rating = serializers.SerializerMethodField()
    total_views = serializers.SerializerMethodField()
    weekly_views = serializers.SerializerMethodField()
    prefered_source = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    reading_history = serializers.SerializerMethodField()
    reading_source = serializers.SerializerMethodField()
    similar_novels = serializers.SerializerMethodField()
    reading_lists = serializers.SerializerMethodField()
    
    class Meta:
        model = Novel
        fields = [
            'id', 'title', 'slug', 'sources', 'created_at', 'updated_at',
            'avg_rating', 'rating_count', 'user_rating', 'total_views', 'weekly_views',
            'prefered_source', 'is_bookmarked', 'comment_count', 'reading_history',
            'reading_source', 'similar_novels', 'reading_lists'
        ]
    
    def get_sources(self, obj):
        return NovelSourceSerializer(
            obj.sources.all(),
            many=True,
            context={**self.context, 'include_synopsis': True}
        ).data

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

    def get_similar_novels(self, obj):
        from ..utils.query_helpers import apply_novel_prefetches, novel_prefetch_objects

        # Get the top 12 similar novels (list() so len() is accurate; a sliced
        # queryset's .count() caps at the slice and made the fallback always fire)
        similar_novels = list(
            obj.similar_to.select_related('to_novel')
            .prefetch_related(*novel_prefetch_objects(prefix='to_novel__'))
            .order_by('-similarity')[:12]
        )

        # If we don't have enough similar novels, top up with most viewed novels
        if len(similar_novels) < 12:
            existing_ids = [item.to_novel_id for item in similar_novels]
            needed_count = 12 - len(existing_ids)

            # Get the most viewed novels not already in our list
            most_viewed = apply_novel_prefetches(
                Novel.objects.exclude(id=obj.id)
                .exclude(id__in=existing_ids)
                .annotate(total_views=Sum('sources__total_views'))
                .order_by('-total_views'),
                getattr(self.context.get('request'), 'user', None),
            )[:needed_count]

            # Combine the results
            for novel in most_viewed:
                similar_novels.append({
                    'to_novel': novel,
                    'similarity': 0.0
                })
        
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
        from ..models.users_models import ReadingList
        from django.db.models import Q

        # Only expose public lists, plus private ones the caller owns or helps on.
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        visibility = Q(is_public=True)
        if user is not None and user.is_authenticated:
            visibility |= Q(user=user) | Q(collaborators__user=user)

        reading_lists = obj.in_reading_lists.values_list('reading_list', flat=True)
        lists = ReadingList.objects.filter(id__in=reading_lists).filter(visibility).distinct()

        return ReadingListSerializer(lists, many=True, context=self.context).data


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['name']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name']
