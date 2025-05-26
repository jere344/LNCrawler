from django.contrib.sitemaps import Sitemap
from django.conf import settings
from urllib.parse import urlparse

from ..models import Novel, NovelFromSource, Chapter

# Parse SITE_URL once
parsed_site_url = urlparse(settings.SITE_URL)
SITEMAP_PROTOCOL = parsed_site_url.scheme
SITEMAP_DOMAIN = parsed_site_url.netloc


class BaseSitemap(Sitemap):
    def get_domain(self, site=None):
        return SITEMAP_DOMAIN

    def get_protocol(self, site=None):
        return SITEMAP_PROTOCOL

class StaticViewSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        # These correspond to paths in your App.tsx
        return [
            '/',
            '/login',
            '/register',
            '/profile', # Generic link
            '/library', # Generic link
            '/history', # Generic link
            '/download',
            '/novels/search',
        ]

    def location(self, item):
        return item

class NovelSitemap(BaseSitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        return Novel.objects.all()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.slug}/'

class SourceSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'daily'

    def items(self):
        return NovelFromSource.objects.select_related('novel').all()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/'

class ChapterListSitemap(BaseSitemap):
    priority = 0.7
    changefreq = 'daily'

    def items(self):
        return NovelFromSource.objects.select_related('novel').filter(chapters__isnull=False).distinct()

    def lastmod(self, obj):
        return obj.last_chapter_update or obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/chapterlist/'

class ChapterReaderSitemap(BaseSitemap):
    priority = 0.6
    changefreq = 'weekly'

    def items(self):
        return Chapter.objects.select_related('novel_from_source__novel').filter(has_content=True).order_by('novel_from_source_id', 'chapter_id')

    def lastmod(self, obj):
        # obj is a Chapter instance.
        # Use last_chapter_update from NovelFromSource if available, else NovelFromSource.updated_at.
        # Chapter model itself does not have an updated_at field per user's file.
        if obj.novel_from_source:
            return obj.novel_from_source.last_chapter_update or obj.novel_from_source.updated_at
        return None # Should ideally not happen if data is consistent

    def location(self, obj):
        return f'/novels/{obj.novel_from_source.novel.slug}/{obj.novel_from_source.source_slug}/chapter/{obj.chapter_id}/'

class ImageGallerySitemap(BaseSitemap):
    priority = 0.5
    changefreq = 'monthly'

    def items(self):
        # Consider only sources that actually have images (e.g., cover or chapter images)
        # For simplicity, linking all sources; frontend can handle empty galleries.
        return NovelFromSource.objects.select_related('novel').all()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/gallery/'
