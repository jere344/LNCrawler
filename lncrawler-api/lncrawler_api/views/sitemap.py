from django.contrib.sitemaps import Sitemap
from django.conf import settings
from urllib.parse import urlparse
from django.db import models
from django.db.models import F
from django.db.models.functions import Coalesce

from ..models import Novel, NovelFromSource
from ..services.audiobook_public import audiobook_path, visible_audiobooks
from ..utils.query_helpers import public_novels, public_sources

# Parse SITE_URL once
parsed_site_url = urlparse(settings.SITE_URL)
SITEMAP_PROTOCOL = parsed_site_url.scheme
SITEMAP_DOMAIN = parsed_site_url.netloc


class BaseSitemap(Sitemap):
    limit = 1000  # Limit items per sitemap file
    
    def get_domain(self, site=None):
        return SITEMAP_DOMAIN

    def get_protocol(self, site=None):
        return SITEMAP_PROTOCOL

class StaticViewSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'weekly'
    limit = 50  # Static pages don't need pagination

    def items(self):
        # These correspond to paths in your App.tsx
        return [
            '/',
            '/library',
            '/history',
            '/reading-lists',
            '/download',
            '/novels/search',
        ]

    def location(self, item):
        return item

class NovelSitemap(BaseSitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        return public_novels(Novel.objects.all()).only('slug', 'updated_at').order_by('slug')

    def lastmod(self, obj):
        return obj.updated_at

    def get_latest_lastmod(self):
        # One indexed query for the sitemap index instead of evaluating every
        # novel just to take max(updated_at).
        return (
            public_novels(Novel.objects.all()).order_by('-updated_at')
            .values_list('updated_at', flat=True)
            .first()
        )

    def location(self, obj):
        return f'/novels/{obj.slug}/'

class BaseSourceSitemap(BaseSitemap):
    changefreq = 'daily'
    page_suffix = ''
    # Per-URL lastmod. It is annotated as _lastmod so the sitemap index uses the same column.
    lastmod_expression = F('updated_at')
    only_fields = ('source_slug', 'updated_at', 'novel__slug')

    def source_queryset(self):
        return public_sources(NovelFromSource.objects.all()).exclude(
            models.Q(source_slug__isnull=True) | models.Q(source_slug='')
        )

    def items(self):
        return self.source_queryset().annotate(_lastmod=self.lastmod_expression).select_related('novel').only(
            *self.only_fields
        ).order_by('novel__slug', 'source_slug')

    def lastmod(self, obj):
        return obj._lastmod

    def get_latest_lastmod(self):
        return (
            self.source_queryset().annotate(_lastmod=self.lastmod_expression)
            .order_by('-_lastmod')
            .values_list('_lastmod', flat=True)
            .first()
        )

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/{self.page_suffix}'

class SourceSitemap(BaseSourceSitemap):
    priority = 0.8

class ChapterListSitemap(BaseSourceSitemap):
    priority = 0.7
    page_suffix = 'chapterlist/'
    lastmod_expression = Coalesce('last_chapter_update', 'updated_at')
    only_fields = ('source_slug', 'updated_at', 'last_chapter_update', 'novel__slug')


class ImageGallerySitemap(BaseSourceSitemap):
    priority = 0.5
    changefreq = 'monthly'
    # Linking all sources; frontend can handle empty galleries.
    page_suffix = 'gallery/'


class AudiobookSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'daily'

    def items(self):
        # The audiobooks section page first, then each audiobook the anonymous viewer may see.
        return ['/audiobooks/', *visible_audiobooks(adult='exclude').order_by('novel__slug', 'language')]

    def lastmod(self, obj):
        return None if isinstance(obj, str) else obj.last_part_at

    def get_latest_lastmod(self):
        return (
            visible_audiobooks(adult='exclude').order_by(F('last_part_at').desc(nulls_last=True))
            .values_list('last_part_at', flat=True)
            .first()
        )

    def location(self, obj):
        if isinstance(obj, str):
            return obj
        return audiobook_path(obj.novel.slug, obj.language)
