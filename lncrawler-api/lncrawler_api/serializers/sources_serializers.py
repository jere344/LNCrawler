from rest_framework import serializers
from ..models import NovelFromSource
from ..utils import build_media_url, get_client_ip
from ..utils.crawler_registry import has_crawler
from ..utils.query_helpers import reading_history_queryset
from .mixins import ProfileFieldsMixin
from .reading_history_serializers import ReadingHistorySerializer
from .chapter_serializers import ChapterSerializer

class NovelSourceSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """Serializes a novel source through one of four profiles.

    ``card`` is the trimmed payload novel cards read (default), which lets
    ``sources_queryset('card')`` skip the matching prefetches and
    annotations; ``library`` is the few columns a library item shows (and the
    source page's preview of it); ``summary`` is the lighter per-source payload
    the source page's "other sources" list and the novel detail's nested sources
    read; ``detail`` is everything the current source's page needs.
    """

    authors = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    editors = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    translators = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    tags = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    alternative_titles = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    user_vote = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    vote_score = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    cover_min_url = serializers.SerializerMethodField()
    overview_url = serializers.SerializerMethodField()
    latest_available_chapter = serializers.SerializerMethodField()
    first_available_chapter = serializers.SerializerMethodField()
    reading_history = serializers.SerializerMethodField()
    volumes = serializers.SerializerMethodField()
    source_name = serializers.CharField(source='external_source.source_name', read_only=True)
    edition = serializers.SerializerMethodField()
    synopsis = serializers.SerializerMethodField()
    has_crawler = serializers.SerializerMethodField()
    is_adult = serializers.SerializerMethodField()
    adult_tags = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'title', 'source_slug', 'novel_slug', 'novel_id', 'cover_min_url',
            'authors', 'tags', 'chapters_count', 'available_chapters_count',
            'last_chapter_update', 'latest_available_chapter', 'is_adult', 'edition',
        ],
        # Cover thumbnail for reading-list cards: only the blurred/first-item
        # cover the list card needs.
        'preview': ['id', 'title', 'cover_min_url'],
        # Library cards and their source page preview: no authors/tags/counters.
        # is_adult drives the cover blur before the source page's own fetch lands.
        'library': [
            'title', 'source_slug', 'novel_slug', 'novel_id', 'cover_min_url',
            'available_chapters_count', 'latest_available_chapter', 'is_adult',
        ],
        'detail': [
            'id', 'title', 'source_url', 'source_name', 'source_slug', 'edition',
            'authors', 'tags', 'language', 'synopsis', 'has_crawler',
            'chapters_count', 'available_chapters_count', 'volumes',
            'last_chapter_update',
            'upvotes', 'downvotes', 'vote_score', 'user_vote', 'novel_id', 'novel_slug',
            'novel_title', 'cover_url', 'latest_available_chapter',
            'first_available_chapter', 'reading_history', 'overview_url',
            'novelupdates_url', 'status', 'editors', 'translators', 'alternative_titles',
            'original_publisher', 'english_publisher', 'is_adult', 'adult_tags',
        ],
        # Everything the source page's "other sources" list renders, plus the
        # novel detail's nested source overview. Covers the scalars and the
        # viewer's own vote, but not the heavy per-source detail (synopsis,
        # volumes, editors, reading history).
        'summary': [
            'id', 'title', 'source_slug', 'novel_slug', 'source_name', 'edition', 'cover_min_url',
            'language', 'chapters_count', 'available_chapters_count',
            'latest_available_chapter',
            'last_chapter_update', 'vote_score', 'user_vote',
        ],
    }

    class Meta:
        model = NovelFromSource

    def get_edition(self, obj: NovelFromSource):
        # Free-form edition label as stored; null when unknown.
        return obj.edition or None

    def get_synopsis(self, obj: NovelFromSource):
        # Synopsis is a large text field; only load it for detail views so list
        # endpoints don't pull every source's synopsis.
        return obj.synopsis if self.profile == 'detail' else None

    def get_has_crawler(self, obj: NovelFromSource):
        # Only detail views show the update button; skip the registry import in
        # list contexts (which don't render it).
        return has_crawler(obj.source_url or '') if self.profile == 'detail' else None

    def get_is_adult(self, obj: NovelFromSource):
        # The source payload drives cover blurring, so it reports its novel's flag
        # (Novel.is_adult). The novel is select_related by sources_queryset.
        return obj.novel.is_adult

    def get_cover_url(self, obj: NovelFromSource):
        return build_media_url(obj.cover_path)

    def get_cover_min_url(self, obj: NovelFromSource):
        return build_media_url(obj.cover_min_path)

    def get_overview_url(self, obj: NovelFromSource):
        return build_media_url(obj.overview_picture_path)

    def get_adult_tags(self, obj: NovelFromSource):
        # This source's R18 tags, so the source page can say why it is adult.
        # Filtered in Python to reuse the tags prefetch.
        return [tag.name for tag in obj.tags.all() if tag.is_adult]

    def get_user_vote(self, obj: NovelFromSource):
        # Only detail and summary views show the current user's vote; skipping
        # the lookup in list contexts removes one query per source.
        if self.profile not in ('detail', 'summary'):
            return None
        # Detailed querysets prefetch the viewer's votes for the whole page.
        if hasattr(obj, 'user_votes'):
            return obj.user_votes[0].vote_type if obj.user_votes else None
        request = self.context.get('request')
        if not request:
            return None

        client_ip = get_client_ip(request)
        if not client_ip:
            return None

        try:
            vote = obj.votes.filter(ip_address=client_ip).first()
            return vote.vote_type if vote else None
        except Exception:
            return None

    def get_novel_id(self, obj: NovelFromSource):
        return str(obj.novel.id) if obj.novel else None

    def get_novel_slug(self, obj: NovelFromSource):
        return obj.novel.slug if obj.novel else None

    def get_novel_title(self, obj: NovelFromSource):
        return obj.novel.title if obj.novel else None

    def get_vote_score(self, obj: NovelFromSource):
        return obj.upvotes - obj.downvotes

    def _chapter_card(self, chapter, source):
        if chapter is None:
            return None
        chapter.novel_from_source = source  # its language labels the title; saves a query per card
        return self._child(ChapterSerializer).to_representation(chapter)

    def get_latest_available_chapter(self, obj: NovelFromSource):
        # The stored FK; sources_queryset selects it, so this costs no query.
        return self._chapter_card(obj.latest_available_chapter, obj)

    def get_first_available_chapter(self, obj: NovelFromSource):
        # Only detail views render this; sources_queryset selects it there only.
        if self.profile != 'detail':
            return None
        return self._chapter_card(obj.first_available_chapter, obj)

    def get_reading_history(self, obj: NovelFromSource):
        """Return the current user's reading position in this novel, whichever of its sources it was read from"""
        # Card views use the novel-level reading_source instead.
        if self.profile != 'detail':
            return None
        if hasattr(obj.novel, 'user_novel_history'):
            history = obj.novel.user_novel_history[0] if obj.novel.user_novel_history else None
        else:
            request = self.context.get('request')
            history = None
            if request and request.user.is_authenticated:
                history = reading_history_queryset(request.user, 'detail').filter(novel=obj.novel).first()
        if history and history.current_chapter:
            return ReadingHistorySerializer(history, profile='detail', context=self.context).data
        return None

    def get_volumes(self, obj: NovelFromSource):
        # Volume listing (id/title) is only needed for the download menu on the
        # detail page; lists skip the extra query.
        if self.profile != 'detail':
            return None
        return [
            {
                'volume_id': v.volume_id,
                'title': v.title,
                'start_chapter': v.start_chapter,
                'final_chapter': v.final_chapter,
                'chapter_count': v.chapter_count,
            }
            # sorted() keeps the prefetched cache (no query); .order_by() would
            # clone the manager and discard the prefetch.
            for v in sorted(obj.volumes.all(), key=lambda v: v.volume_id)
        ]


class GalleryImageSerializer(serializers.Serializer):
    """
    Serializes image information for the gallery
    """
    chapter_id = serializers.IntegerField()
    chapter_display_title = serializers.CharField()
    image_url = serializers.CharField()
    image_name = serializers.CharField()
