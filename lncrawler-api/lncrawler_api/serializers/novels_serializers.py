from rest_framework import serializers
from ..models import (
    Novel, Author, Tag,
    WeeklySourceView,
    NovelBookmark
)
from django.db.models import Avg, Sum, Value
from django.db.models.functions import Coalesce
from .mixins import ProfileFieldsMixin
from .sources_serializers import NovelSourceSerializer
from .reading_history_serializers import ReadingHistorySerializer
from ..utils import get_client_ip


class NovelAggregatesMixin:
    """Computes the read-only counters shared by the novel profiles. When the
    queryset was built with `apply_novel_prefetches` everything is served from
    the prefetch cache (zero extra queries); otherwise it falls back to the
    original per-object queries."""

    @property
    def source_profile(self):
        # Which NovelSourceSerializer profile the preferred/reading source uses.
        # detail = full source payload; featured = card + synopsis (home card);
        # anything else (card/library) = card.
        if self.profile == 'detail':
            return 'detail'
        if self.profile == 'featured':
            return 'featured'
        if self.profile == 'preview':
            return 'preview'
        return 'card'

    def _prefetched(self, obj, name):
        return name in getattr(obj, '_prefetched_objects_cache', {})

    def _context_sources(self, obj):
        # Restrict to the languages the request was filtered by (when any) so
        # counters, language badges and the preferred source agree with the
        # filter; fall back to all sources if none match. Memoized because the
        # list serializer instance is reused for every novel and reads this
        # from total_views/weekly_views/prefered_source/languages.
        cache = getattr(self, '_context_sources_cache', None)
        if cache is None:
            cache = self._context_sources_cache = {}
        if obj.pk not in cache:
            sources = list(obj.sources.all())
            languages = self.context.get('languages') or []
            if languages:
                localized = [s for s in sources if s.language in languages]
                if localized:
                    sources = localized
            cache[obj.pk] = sources
        return cache[obj.pk]

    def get_prefered_source(self, obj):
        sources = self._context_sources(obj)

        if not sources:
            return None

        # Highest vote score, then most upvotes, then title.
        prefered = min(
            sources,
            key=lambda s: (-(s.upvotes - s.downvotes), -s.upvotes, s.title or ''),
        )
        return NovelSourceSerializer(
            prefered, context=self.context, profile=self.source_profile
        ).data

    def get_avg_rating(self, obj):
        # Querysets built with annotate_card_aggregates carry the average.
        if 'card_avg_rating' in obj.__dict__:
            avg = obj.card_avg_rating
            return round(avg, 1) if avg is not None else None
        if self._prefetched(obj, 'ratings'):
            ratings = [rating.rating for rating in obj.ratings.all()]
            return round(sum(ratings) / len(ratings), 1) if ratings else None
        avg = obj.ratings.all().aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else None

    def get_rating_count(self, obj):
        if 'card_rating_count' in obj.__dict__:
            return obj.card_rating_count or 0
        if self._prefetched(obj, 'ratings'):
            return len(obj.ratings.all())
        return obj.ratings.count()

    def get_total_views(self, obj):
        if 'card_total_views' in obj.__dict__:
            return obj.card_total_views or 0
        return sum(source.total_views for source in self._context_sources(obj))

    def get_weekly_views(self, obj):
        if 'card_weekly_views' in obj.__dict__:
            return obj.card_weekly_views or 0
        sources = self._context_sources(obj)
        if self._prefetched(obj, 'sources') and all(
            self._prefetched(source, 'weekly_views') for source in sources
        ):
            return sum(
                view.views for source in sources for view in source.weekly_views.all()
            )
        total = WeeklySourceView.objects.filter(
            source_id__in=[source.pk for source in sources],
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
        if not history or not history.last_read_chapter:
            return None
        return ReadingHistorySerializer(history, profile='detail').data

    def _source_by_pk(self, obj, pk):
        # The reader's source is already in the prefetched ``sources`` list
        # (with authors/tags warm), unlike ``history.source`` whose M2M would
        # fire two queries per novel.
        for source in obj.sources.all():
            if source.pk == pk:
                return source
        return None

    def get_reading_source(self, obj):
        history = self._get_reading_history(obj)
        if history and history.source:
            source = self._source_by_pk(obj, history.source_id) or history.source
            return NovelSourceSerializer(
                source, context=self.context, profile=self.source_profile
            ).data
        return None


class NovelSerializer(NovelAggregatesMixin, ProfileFieldsMixin, serializers.ModelSerializer):
    """Serializes a novel through one of four profiles.

    ``card`` is the lightweight card (default), ``detail`` adds the nested
    sources / viewer rating / similar novels / reading lists, ``library`` is
    the card payload plus the bookmark owner's folder, note, position and
    rating, and ``featured`` is ``card`` with the preferred source's synopsis
    for the home card. Only the fields a profile emits are built, so
    detail-only work never runs for card rows.
    """

    sources = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    user_rating = serializers.SerializerMethodField()
    total_views = serializers.SerializerMethodField()
    weekly_views = serializers.SerializerMethodField()
    prefered_source = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    is_adult = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    reading_history = serializers.SerializerMethodField()
    reading_source = serializers.SerializerMethodField()
    similar_novels = serializers.SerializerMethodField()
    reading_lists = serializers.SerializerMethodField()
    bookmark_id = serializers.SerializerMethodField()
    note = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    folder_name = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'title', 'slug',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'prefered_source', 'languages', 'is_adult', 'is_bookmarked', 'comment_count',
            'reading_history', 'reading_source', 'is_dmca',
        ],
        # The home featured card: the card payload with its preferred source
        # carrying the synopsis. Deliberately omits sources / similar_novels /
        # reading_lists / user_rating, which the card never renders and whose
        # serialization is where home used to spend most of its queries.
        'featured': [
            'id', 'title', 'slug',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'prefered_source', 'languages', 'is_adult', 'is_bookmarked', 'comment_count',
            'reading_history', 'reading_source', 'is_dmca',
        ],
        'detail': [
            'id', 'title', 'slug', 'sources', 'created_at', 'updated_at',
            'avg_rating', 'rating_count', 'user_rating', 'total_views', 'weekly_views',
            'prefered_source', 'is_adult', 'is_bookmarked', 'comment_count', 'reading_history',
            'reading_source', 'similar_novels', 'reading_lists', 'is_dmca',
        ],
        'library': [
            'id', 'title', 'slug',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'prefered_source', 'languages', 'is_adult', 'is_bookmarked', 'comment_count',
            'reading_history', 'reading_source', 'is_dmca',
            'bookmark_id', 'note', 'folder', 'folder_name', 'position', 'user_rating',
        ],
        # Cover thumbnail for reading-list cards (first_item): only what the
        # card renders, so a list page doesn't serialize a full card per list.
        'preview': ['id', 'title', 'prefered_source', 'is_adult'],
    }

    class Meta:
        model = Novel

    def get_languages(self, obj):
        """Returns a list of languages for the sources of the novel."""
        languages = {
            source.language
            for source in self._context_sources(obj)
            if source.language
        }
        return list(languages)

    def get_is_adult(self, obj):
        # Novel-level flag: adult if any of its sources is adult. Reads the
        # prefetched sources, so no extra query.
        return any(source.is_adult for source in obj.sources.all())

    def get_sources(self, obj):
        return NovelSourceSerializer(
            obj.sources.all(), many=True, context=self.context, profile='detail'
        ).data

    def get_user_rating(self, obj):
        # Library = the bookmark owner's star rating (already attached by the
        # view; no query). Detail = the requesting viewer's own rating.
        if self.profile == 'library':
            if not self.context.get('show_ratings', True):
                return None
            bookmark = self._bookmark(obj)
            return getattr(bookmark, 'owner_rating', None) if bookmark else None

        request = self.context.get('request')
        if not request:
            return None

        if request.user.is_authenticated:
            rating = obj.ratings.filter(user=request.user).first()
        else:
            client_ip = get_client_ip(request)
            if not client_ip:
                return None
            rating = obj.ratings.filter(user__isnull=True, ip_address=client_ip).first()
        return rating.rating if rating else None

    def get_similar_novels(self, obj):
        from ..utils.query_helpers import (
            adult_allowed, apply_novel_prefetches, exclude_adult,
            novel_prefetch_objects, sources_total_views_subquery
        )

        # Get the top 12 similar novels (list() so len() is accurate; a sliced
        # queryset's .count() caps at the slice and made the fallback always fire).
        # Pass the requesting user so bookmark/history lookups are prefetched
        # instead of firing a query per similar novel.
        user = getattr(self.context.get('request'), 'user', None)
        similar_qs = obj.similar_to.select_related('to_novel')
        if not adult_allowed(user):
            similar_qs = similar_qs.exclude(to_novel__sources__is_adult=True)
        similar_novels = list(
            similar_qs
            .prefetch_related(*novel_prefetch_objects(user, prefix='to_novel__'))
            .order_by('-similarity')[:12]
        )

        # If we don't have enough similar novels, top up with most viewed novels
        if len(similar_novels) < 12:
            existing_ids = [item.to_novel_id for item in similar_novels]
            needed_count = 12 - len(existing_ids)

            # Get the most viewed novels not already in our list. Coalesce so
            # source-less novels (NULL sum) sort last instead of first on
            # Postgres DESC, and a dedup subquery so the sum isn't inflated.
            most_viewed = apply_novel_prefetches(
                exclude_adult(
                    Novel.objects.exclude(id=obj.id).exclude(id__in=existing_ids),
                    user,
                )
                .annotate(total_views=Coalesce(sources_total_views_subquery(), Value(0)))
                .order_by('-total_views'),
                user,
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
                novel_data = NovelSerializer(item.to_novel, context=self.context).data
                novel_data['similarity'] = item.similarity
            else:
                # Dictionary from most viewed novels
                novel_data = NovelSerializer(item['to_novel'], context=self.context).data
                novel_data['similarity'] = item['similarity']

            result.append(novel_data)

        return result

    def get_reading_lists(self, obj):
        from .reading_lists_serializers import ReadingListSerializer
        from ..views.reading_lists_views import _reading_lists_query_set
        from django.db.models import Q

        # Only expose public lists, plus private ones the caller owns or helps on.
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        visibility = Q(is_public=True)
        if user is not None and user.is_authenticated:
            visibility |= Q(user=user) | Q(collaborators__user=user)

        reading_lists = obj.in_reading_lists.values_list('reading_list', flat=True)
        # Reuse the reading-lists view queryset so each list's items (and their
        # nested novels) are prefetched instead of firing per-list/per-item.
        lists = (
            _reading_lists_query_set(user)
            .filter(id__in=reading_lists)
            .filter(visibility)
            .distinct()
        )

        return ReadingListSerializer(lists, many=True, context=self.context).data

    def _bookmark(self, obj):
        # Set by the library view; absent everywhere else.
        return getattr(obj, 'library_bookmark', None)

    def get_bookmark_id(self, obj):
        bookmark = self._bookmark(obj)
        return str(bookmark.id) if bookmark else None

    def get_note(self, obj):
        if not self.context.get('show_notes', True):
            return None
        bookmark = self._bookmark(obj)
        return bookmark.note if bookmark else None

    def get_folder(self, obj):
        bookmark = self._bookmark(obj)
        return str(bookmark.folder_id) if bookmark and bookmark.folder_id else None

    def get_folder_name(self, obj):
        bookmark = self._bookmark(obj)
        return bookmark.folder.name if bookmark and bookmark.folder_id else None

    def get_position(self, obj):
        bookmark = self._bookmark(obj)
        return bookmark.position if bookmark else 0


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['name']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name']
