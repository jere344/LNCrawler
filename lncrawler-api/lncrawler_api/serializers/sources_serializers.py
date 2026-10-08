from rest_framework import serializers
from ..models import NovelFromSource
from ..utils import build_media_url, get_client_ip
from ..utils.crawler_registry import has_crawler
from .mixins import ProfileFieldsMixin
from .reading_history_serializers import ReadingHistorySerializer
from .chapter_serializers import ChapterSerializer

class NovelSourceSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """Serializes a novel source through one of three profiles.

    ``card`` is the trimmed payload novel cards read (default), which lets
    ``sources_queryset(detailed=False)`` skip the matching prefetches and
    annotations; ``featured`` is the home card (card plus the synopsis and
    novel_id truthiness flag); ``detail`` is everything the source page needs.
    """

    authors = serializers.SerializerMethodField()
    editors = serializers.SerializerMethodField()
    translators = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    alternative_titles = serializers.SerializerMethodField()
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
    chapters_count = serializers.SerializerMethodField()
    volumes_count = serializers.SerializerMethodField()
    volumes = serializers.SerializerMethodField()
    source_name = serializers.CharField(source='external_source.source_name', read_only=True)
    synopsis = serializers.SerializerMethodField()
    has_crawler = serializers.SerializerMethodField()
    is_adult = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'title', 'source_slug', 'novel_slug', 'novel_id', 'cover_min_url',
            'authors', 'tags', 'chapters_count', 'last_chapter_update',
            'latest_available_chapter', 'is_adult',
        ],
        # Home featured card: everything a card shows plus the synopsis (and
        # novel_id, which the card uses as a truthiness flag). Skips the
        # detail-only volumes / first-chapter / editors / translators / votes.
        'featured': [
            'id', 'title', 'source_slug', 'novel_slug', 'cover_min_url',
            'authors', 'tags', 'chapters_count', 'last_chapter_update',
            'latest_available_chapter', 'synopsis', 'novel_id', 'is_adult',
        ],
        'detail': [
            'id', 'title', 'source_url', 'source_name', 'source_slug',
            'authors', 'tags', 'language', 'synopsis', 'has_crawler', 'cover_min_url',
            'chapters_count', 'volumes_count', 'volumes', 'last_chapter_update',
            'upvotes', 'downvotes', 'vote_score', 'user_vote', 'novel_id', 'novel_slug',
            'novel_title', 'cover_url', 'latest_available_chapter',
            'first_available_chapter', 'reading_history', 'overview_url',
            'novelupdates_url', 'status', 'editors', 'translators', 'alternative_titles',
            'original_publisher', 'english_publisher', 'is_adult',
        ],
    }

    class Meta:
        model = NovelFromSource

    def get_synopsis(self, obj: NovelFromSource):
        # Synopsis is a large text field; only load it for detail views (and the
        # single-source featured card) so list endpoints don't pull every
        # source's synopsis.
        return obj.synopsis if self.profile in ('detail', 'featured') else None

    def get_has_crawler(self, obj: NovelFromSource):
        # Only detail views show the update button; skip the registry import in
        # list contexts (which don't render it).
        return has_crawler(obj.source_url or '') if self.profile == 'detail' else None

    def get_is_adult(self, obj: NovelFromSource):
        # A novel is adult if any of its sources is; the source payload drives
        # cover blurring, so report the novel-level flag when the queryset
        # annotated it (sources_queryset) and fall back to this source's flag.
        if hasattr(obj, 'novel_is_adult'):
            return obj.novel_is_adult
        return obj.is_adult

    def get_cover_url(self, obj: NovelFromSource):
        return build_media_url(obj.cover_path)

    def get_cover_min_url(self, obj: NovelFromSource):
        return build_media_url(obj.cover_min_path)

    def get_overview_url(self, obj: NovelFromSource):
        return build_media_url(obj.overview_picture_path)

    def get_authors(self, obj: NovelFromSource):
        return [author.name for author in obj.authors.all()]

    def get_editors(self, obj: NovelFromSource):
        return [editor.name for editor in obj.editors.all()]

    def get_translators(self, obj: NovelFromSource):
        return [translator.name for translator in obj.translators.all()]

    def get_tags(self, obj: NovelFromSource):
        return [tag.name for tag in obj.tags.all()]

    def get_alternative_titles(self, obj: NovelFromSource):
        return [title.name for title in obj.alternative_titles.all()]

    def get_user_vote(self, obj: NovelFromSource):
        # Only detail views show the current user's vote; skipping the lookup
        # in list contexts removes one query per source.
        if self.profile != 'detail':
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

    def get_latest_available_chapter(self, obj: NovelFromSource):
        """Return the latest available chapter with content"""
        # List querysets annotate this so the whole page resolves in one query.
        if 'latest_chapter_id' in obj.__dict__:
            chapter_id = obj.latest_chapter_id
            if chapter_id is None:
                return None
            return {
                'id': None,
                'chapter_id': chapter_id,
                'title': obj.latest_chapter_title,
                'url': obj.latest_chapter_url,
                'volume': 0,
                'volume_title': None,
                'has_content': True,
            }
        latest_chapter = obj.chapters.filter(has_content=True).order_by('-chapter_id').first()
        if latest_chapter:
            return ChapterSerializer(latest_chapter).data
        return None

    def get_first_available_chapter(self, obj: NovelFromSource):
        """Return the first available chapter with content"""
        # Detail querysets annotate this (see sources_queryset detailed mode).
        if 'first_chapter_id' in obj.__dict__:
            chapter_id = obj.first_chapter_id
            if chapter_id is None:
                return None
            return {
                'id': None,
                'chapter_id': chapter_id,
                'title': obj.first_chapter_title,
                'url': obj.first_chapter_url,
                'volume': 0,
                'volume_title': None,
                'has_content': True,
            }
        # Only detail views render this; lists skip the extra query.
        if self.profile != 'detail':
            return None
        first_chapter = obj.chapters.filter(has_content=True).order_by('chapter_id').first()
        if first_chapter:
            return ChapterSerializer(first_chapter).data
        return None

    def get_reading_history(self, obj: NovelFromSource):
        """Return the reading history for the current user"""
        # Card views use the novel-level reading_source instead.
        if self.profile != 'detail':
            return None
        if hasattr(obj, 'user_read_history'):
            history = obj.user_read_history[0] if obj.user_read_history else None
            if history and history.last_read_chapter:
                return ReadingHistorySerializer(history).data
            return None
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            history = obj.read_by_users.filter(user=request.user).first()
            if history and history.last_read_chapter:
                return ReadingHistorySerializer(history).data
        return None

    def get_chapters_count(self, obj: NovelFromSource):
        if 'annotated_chapters_count' in obj.__dict__:
            return obj.annotated_chapters_count or 0
        return obj.chapters_count

    def get_volumes_count(self, obj: NovelFromSource):
        if 'annotated_volumes_count' in obj.__dict__:
            return obj.annotated_volumes_count or 0
        return obj.volumes_count

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
    chapter_title = serializers.CharField()
    image_url = serializers.CharField()
    image_name = serializers.CharField()
