from rest_framework import serializers
from ..models import (
    Novel,
    NovelBookmark
)
from django.core.cache import cache
from django.db.models import Prefetch, Q
from .mixins import ProfileFieldsMixin
from .sources_serializers import NovelSourceSerializer
from .reading_history_serializers import ReadingHistorySerializer
from ..utils import get_client_ip
from ..utils.query_helpers import (
    adult_allowed,
    exclude_adult,
    most_viewed_novel_ids,
    novel_queryset,
    rank_sources,
    reading_lists_queryset,
)


class NovelAggregatesMixin:
    """Computes the read-only counters shared by the novel profiles. They are
    read from the ``card_*`` annotations that ``novel_queryset`` puts on every
    queryset a novel payload is built from, so a novel rendered without them
    fails loudly instead of paying a query per row."""

    @property
    def source_profile(self):
        # Which NovelSourceSerializer profile the suggested/reading source uses.
        # detail = the source page is separate; nested sources only need the
        # lightweight summary; preview = thumbnail; library = the library card's
        # few columns; anything else = card.
        if self.profile == 'detail':
            return 'summary'
        if self.profile == 'preview':
            return 'preview'
        if self.profile == 'library':
            return 'library'
        return 'card'

    def _context_sources(self, obj):
        # Restrict to the languages the request was filtered by (when any) so
        # language badges and the suggested source agree with the filter; fall
        # back to all sources if none match. Memoized because the list serializer
        # instance is reused for every novel and reads this from suggested_source/languages.
        # (The view counters come from the card_* annotations, scoped to the same languages
        # but without the fall-back: callers only pass languages for lists already
        # filtered to novels with a matching source.)
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

    def _source_serializer(self, profile):
        # Per-object state is keyed by obj.pk, so one serializer serves every novel.
        return self._child(NovelSourceSerializer, profile=profile)

    def _history_serializer(self):
        return self._child(
            ReadingHistorySerializer,
            profile='library' if self.profile == 'library' else 'detail',
        )

    def get_suggested_source(self, obj):
        # The source a viewer opens: the best one in the languages the request was filtered by. When the
        # filter leaves no source of the novel, the canonical source (see services/novel_naming.py).
        # Sources come from the prefetch, so this costs no query per novel.
        sources = list(obj.sources.all())
        languages = self.context.get('languages') or []
        localized = [s for s in sources if s.language in languages] if languages else sources
        if localized:
            suggested = rank_sources(localized, languages)
        else:
            suggested = next((s for s in sources if s.pk == obj.canonical_source_id), None)
            if suggested is None:
                suggested = rank_sources(sources)
        if suggested is None:
            return None
        return self._source_serializer(self.source_profile).to_representation(suggested)

    def get_avg_rating(self, obj):
        # The average arrives as a SQL numeric, whose round() is half-even on the
        # decimal (2.45 -> 2.4); the float round matches the Python average it replaced.
        avg = obj.card_avg_rating
        return round(float(avg), 1) if avg is not None else None

    def get_rating_count(self, obj):
        return obj.card_rating_count or 0

    def get_total_views(self, obj):
        return obj.card_total_views or 0

    def get_weekly_views(self, obj):
        return obj.card_weekly_views or 0

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
        # Library items never query progress themselves: without the prefetch there is none to show.
        if self.profile == 'library':
            return None
        cache = getattr(self, '_history_cache', None)
        if cache is None:
            cache = self._history_cache = {}
        if obj.pk not in cache:
            request = self.context.get('request')
            history = None
            if request and request.user.is_authenticated:
                from ..utils.query_helpers import annotate_reading_history
                history = annotate_reading_history(
                    obj.reading_histories
                    .select_related('source__latest_available_chapter', 'source__external_source', 'current_chapter')
                    .filter(user=request.user)
                ).first()
            cache[obj.pk] = history
        return cache[obj.pk]

    def get_reading_history(self, obj):
        history = self._get_reading_history(obj)
        if not history or not history.current_chapter:
            return None
        return self._history_serializer().to_representation(history)

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
            return self._source_serializer(self.source_profile).to_representation(source)
        return None


class NovelSerializer(NovelAggregatesMixin, ProfileFieldsMixin, serializers.ModelSerializer):
    """Serializes a novel through one of three profiles.

    ``card`` is the lightweight card (default), ``detail`` adds the nested
    sources / viewer rating / similar novels / reading lists, and ``library``
    is the bookmark row a library item shows: the bookmark's folder, note and
    rating plus the progress the viewer may see. Only the fields a profile
    emits are built, so detail-only work never runs for card rows.
    """

    sources = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    user_rating = serializers.SerializerMethodField()
    total_views = serializers.SerializerMethodField()
    weekly_views = serializers.SerializerMethodField()
    suggested_source = serializers.SerializerMethodField()
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
    audiobooks = serializers.SerializerMethodField()
    has_audiobook = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'slug',
            'avg_rating', 'rating_count', 'total_views', 'weekly_views',
            'suggested_source', 'languages', 'is_adult', 'is_bookmarked', 'comment_count',
            'reading_history', 'reading_source', 'is_dmca', 'created_at', 'has_audiobook',
        ],
        'detail': [
            'id', 'slug', 'sources',
            'avg_rating', 'rating_count', 'user_rating', 'total_views', 'weekly_views',
            'suggested_source', 'is_adult', 'is_bookmarked', 'comment_count', 'reading_history',
            'reading_source', 'similar_novels', 'reading_lists', 'is_dmca', 'audiobooks',
        ],
        'library': [
            'id', 'slug', 'is_adult', 'is_dmca', 'is_bookmarked',
            'bookmark_id', 'note', 'folder', 'folder_name', 'user_rating',
            'suggested_source', 'reading_source', 'reading_history',
        ],
        # Cover thumbnail for reading-list cards (first_item): only what the
        # card renders, so a list page doesn't serialize a full card per list.
        'preview': ['id', 'suggested_source', 'is_adult', 'has_audiobook'],
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
        return obj.is_adult

    def get_audiobooks(self, obj):
        """The public audiobooks of the novel: language and total duration, for the detail page."""
        from ..services.audiobook_public import annotate_public_totals, visible_audiobooks

        user = getattr(self.context.get('request'), 'user', None)
        audiobooks = annotate_public_totals(visible_audiobooks(user).filter(novel=obj)).order_by('language')
        return [
            {'language': audiobook.language, 'duration_s': audiobook.public_duration_s}
            for audiobook in audiobooks
        ]

    def get_has_audiobook(self, obj):
        # Set by novel_queryset for the profiles that render it.
        return bool(obj.annotated_has_audiobook)

    def get_sources(self, obj):
        return NovelSourceSerializer(
            obj.sources.all(), many=True, context=self.context, profile='summary'
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
        # Up to 12 similar novels. Evaluated as a list so len() is the row count: a sliced queryset's
        # count() is capped at the slice.
        # Pass the requesting user so bookmark/history lookups are prefetched
        # instead of firing a query per similar novel.
        user = getattr(self.context.get('request'), 'user', None)
        languages = self.context.get('languages')
        similar_qs = obj.similar_to.filter(
            to_novel__is_dmca=False, similarity__gt=0,
        )
        similar_qs = exclude_adult(similar_qs, user, 'to_novel__')
        similar_novels = list(
            similar_qs
            .prefetch_related(Prefetch(
                'to_novel',
                queryset=novel_queryset(user=user, languages=languages),
            ))
            .order_by('-similarity')[:12]
        )

        # If we don't have enough similar novels, top up with most viewed novels
        if len(similar_novels) < 12:
            existing_ids = [item.to_novel_id for item in similar_novels]
            needed_count = 12 - len(existing_ids)

            # Most-viewed novel ids, cached briefly: ordering every novel on each
            # detail page scales with the catalogue size. Reads the indexed
            # rank_total_views projection (refreshed by the scheduler).
            most_viewed_key = f"similar:most_viewed:v3:{int(adult_allowed(user))}"
            most_viewed_ids = cache.get(most_viewed_key)
            if most_viewed_ids is None:
                most_viewed_ids = most_viewed_novel_ids(user, 40)
                cache.set(most_viewed_key, most_viewed_ids, 600)

            # Pick the most viewed novels not already in our list, keeping the cached order
            excluded_ids = set(existing_ids) | {obj.id}
            picked_ids = [
                pk for pk in most_viewed_ids if pk not in excluded_ids
            ][:needed_count]
            fetched = {
                novel.pk: novel
                for novel in novel_queryset(
                    exclude_adult(Novel.objects.filter(pk__in=picked_ids), user),
                    user, languages=languages,
                )
            }
            most_viewed = [fetched[pk] for pk in picked_ids if pk in fetched]

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

        # Only expose public lists, plus private ones the caller owns or helps on.
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        visibility = Q(is_public=True)
        if user is not None and user.is_authenticated:
            visibility |= Q(user=user) | Q(collaborators__user=user)

        reading_lists = obj.in_reading_lists.values_list('reading_list', flat=True)
        # Reuse the reading-lists queryset so each list's items (and their
        # nested novels) are prefetched instead of firing per-list/per-item.
        # The card only renders the preview profile of each item, so full=False.
        lists = (
            reading_lists_queryset(user, full=False)
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
