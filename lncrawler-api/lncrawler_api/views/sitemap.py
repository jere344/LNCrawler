from django.contrib.sitemaps import Sitemap
from django.conf import settings
from urllib.parse import urlparse
from django.db import models

from ..models import Novel, NovelFromSource, Chapter

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
            '/login',
            '/register',
            '/profile',
            '/library',
            '/history',
            '/download',
            '/novels/search',
        ]

    def location(self, item):
        return item

class NovelSitemap(BaseSitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        return Novel.objects.only('slug', 'updated_at').order_by('slug')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.slug}/'

class SourceSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'daily'

    def items(self):
        return NovelFromSource.objects.select_related('novel').only(
            'source_slug', 'updated_at', 'novel__slug'
        ).order_by('novel__slug', 'source_slug')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/'

class ChapterListSitemap(BaseSitemap):
    priority = 0.7
    changefreq = 'daily'

    def items(self):
        return NovelFromSource.objects.select_related('novel').only(
            'source_slug', 'updated_at', 'last_chapter_update', 'novel__slug'
        ).filter(chapters__isnull=False).distinct().order_by('novel__slug', 'source_slug')

    def lastmod(self, obj):
        return obj.last_chapter_update or obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/chapterlist/'

# class ChapterReaderSitemap(BaseSitemap):
#     priority = 0.6
#     changefreq = 'weekly'

#     def items(self):
#         chapters_to_include = []
#         novel_sources = NovelFromSource.objects.select_related('novel').all()

#         for nfs in novel_sources:
#             # Get the first chapter with content
#             first_chapter = Chapter.objects.filter(
#                 novel_from_source=nfs,
#                 has_content=True
#             ).order_by('chapter_id').first()

#             if first_chapter:
#                 chapters_to_include.append(first_chapter)

#             # Get the last chapter with content
#             last_chapter = Chapter.objects.filter(
#                 novel_from_source=nfs,
#                 has_content=True
#             ).order_by('-chapter_id').first()

#             if last_chapter:
#                 # Avoid adding the same chapter twice if it's the only chapter
#                 if not first_chapter or first_chapter.id != last_chapter.id:
#                     chapters_to_include.append(last_chapter)
        
#         return chapters_to_include

#     def lastmod(self, obj):
#         # obj is a Chapter instance.
#         # Use last_chapter_update from NovelFromSource if available, else NovelFromSource.updated_at.
#         # Chapter model itself does not have an updated_at field per user's file.
#         if obj.novel_from_source:
#             return obj.novel_from_source.last_chapter_update or obj.novel_from_source.updated_at
#         return None # Should ideally not happen if data is consistent

#     def location(self, obj):
#         return f'/novels/{obj.novel_from_source.novel.slug}/{obj.novel_from_source.source_slug}/chapter/{obj.chapter_id}/'

class ImageGallerySitemap(BaseSitemap):
    priority = 0.5
    changefreq = 'monthly'

    def items(self):
        # Consider only sources that actually have images (e.g., cover or chapter images)
        # For simplicity, linking all sources; frontend can handle empty galleries.
        return NovelFromSource.objects.select_related('novel').only(
            'source_slug', 'updated_at', 'novel__slug'
        ).order_by('novel__slug', 'source_slug')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return f'/novels/{obj.novel.slug}/{obj.source_slug}/gallery/'
