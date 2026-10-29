"""The podcast RSS feed of an audiobook: one episode per chapter of each listenable part.

Built on Django's RSS 2.0 writer, with the iTunes and Podcast Index namespaces added, so podcast apps can list,
subscribe to and download the chapters. The catalog feed is a plain RSS 2.0 feed of the newest parts.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils.feedgenerator import Enclosure, Rss201rev2Feed
from django.utils.text import Truncator

from ..models import AudiobookChapter, AudiobookPart
from ..utils.text import strip_html
from . import audiobook_media
from .audiobook_public import (
    LISTENABLE_PART_Q, audiobook_path, chapter_audio_url, cover_urls, narrator_credit, visible_audiobooks,
)

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
PODCAST_NS = "https://podcastindex.org/namespace/1.0"
CATEGORY = "Arts"
SUBCATEGORY = "Books"
CATALOG_LIMIT = 50  # newest parts in the catalog feed
CATALOG_TITLE_SUFFIX = {'exclude': '', 'include': ' (all)', 'only': ' (adult)'}


class PodcastFeed(Rss201rev2Feed):
    def rss_attributes(self):
        attributes = super().rss_attributes()
        attributes["xmlns:itunes"] = ITUNES_NS
        attributes["xmlns:podcast"] = PODCAST_NS
        return attributes

    def add_root_elements(self, handler):
        super().add_root_elements(handler)
        feed = self.feed
        if feed["image_url"]:
            handler.startElement("image", {})
            handler.addQuickElement("url", feed["image_url"])
            handler.addQuickElement("title", feed["title"])
            handler.addQuickElement("link", feed["link"])
            handler.endElement("image")
            handler.addQuickElement("itunes:image", None, {"href": feed["image_url"]})
        handler.addQuickElement("itunes:author", feed["itunes_author"])
        handler.startElement("itunes:category", {"text": CATEGORY})
        handler.addQuickElement("itunes:category", None, {"text": SUBCATEGORY})
        handler.endElement("itunes:category")
        handler.addQuickElement("itunes:explicit", "false")
        handler.addQuickElement("itunes:type", "serial")
        handler.addQuickElement("itunes:summary", feed["description"])
        handler.addQuickElement("podcast:person", feed["narrator"], {"role": "narrator"})
        for name in feed["authors"]:
            handler.addQuickElement("podcast:person", name, {"role": "author"})

    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        handler.addQuickElement("itunes:duration", str(item["itunes_duration"]))
        handler.addQuickElement("itunes:season", str(item["itunes_season"]))
        handler.addQuickElement("itunes:episode", str(item["itunes_episode"]))
        handler.addQuickElement("itunes:episodeType", "full")


def podcast_feed_xml(audiobook):
    """The feed of an audiobook as an XML string. ``audiobook`` carries the public totals and is visible to
    anonymous viewers (see ``get_visible_audiobook_or_404``)."""
    novel = audiobook.novel
    authors = sorted(author.name for author in audiobook.source.authors.all())
    disclaimer = audiobook_media.audiobook_metadata(audiobook)['disclaimer']
    synopsis = " ".join(strip_html(audiobook.source.synopsis).split())
    page_url = f"{settings.SITE_URL}{audiobook_path(novel.slug, audiobook.language)}"
    feed = PodcastFeed(
        title=f"{novel.title} (Generated audiobook)",
        link=page_url,
        description=f"{disclaimer} {synopsis}".strip(),
        language=audiobook.language,
        feed_url=f"{settings.SITE_API_URL}/audiobooks/{novel.slug}/feed.xml?lang={audiobook.language}",
        itunes_author=", ".join(authors),
        image_url=cover_urls(audiobook)[1],
        narrator=narrator_credit(audiobook),
        authors=authors,
    )
    # Newest part first, and within a part the highest chapter first.
    rows = (
        AudiobookChapter.objects.filter(part__in=AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=audiobook))
        .select_related('part', 'chapter')
        .order_by('-part__index', '-chapter__chapter_id')
    )
    for row in rows:
        part = row.part
        feed.add_item(
            title=row.chapter.title or f"Chapter {row.chapter.chapter_id}",
            link=page_url,
            description=None,
            unique_id=f"{row.chapter_id}-g{part.generation}",
            unique_id_is_permalink=False,
            # Sorting apps order episodes by date: each chapter is placed at its offset within the part.
            pubdate=(part.completed_at or part.created_at) + timedelta(seconds=row.offset_s),
            enclosures=[Enclosure(chapter_audio_url(row), str(row.size_bytes), "audio/ogg")],
            itunes_duration=round(row.duration_s),
            itunes_season=part.index,
            itunes_episode=row.chapter.chapter_id,
        )
    return feed.writeString("utf-8")


def _duration_text(seconds):
    hours, minutes = divmod(round((seconds or 0) / 60), 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def catalog_feed_xml(adult):
    """The site-wide feed: the newest listenable parts of the visible audiobooks, as plain RSS 2.0 (no podcast
    tags, no enclosures). ``adult`` is 'exclude', 'include' or 'only' (see ``visible_audiobooks``)."""
    audiobooks = visible_audiobooks(adult=adult).prefetch_related(None).values('pk')
    feed = Rss201rev2Feed(
        title=f"LNCrawler generated audiobooks{CATALOG_TITLE_SUFFIX[adult]}",
        link=f"{settings.SITE_URL}/audiobooks/",
        description="Newly available parts of the generated audiobooks. Generated, not official.",
        feed_url=f"{settings.SITE_API_URL}/audiobooks/feed.xml?adult={adult}",
    )
    parts = (
        AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook__in=audiobooks)
        .select_related('audiobook__novel', 'audiobook__source')
        .order_by(F('completed_at').desc(nulls_last=True), '-pk')[:CATALOG_LIMIT]
    )
    for part in parts:
        audiobook = part.audiobook
        novel = audiobook.novel
        description = (
            f"Chapters {part.chapter_start}\u2013{part.chapter_end}, {_duration_text(part.duration_s)}. "
            "Generated audiobook, not an official one."
        )
        if part.index == 1:
            synopsis = Truncator(" ".join(strip_html(audiobook.source.synopsis).split())).chars(200)
            description = f"{description} {synopsis}".strip()
        feed.add_item(
            title=f"{novel.title} \u2014 Part {part.index} (Generated audiobook)",
            link=f"{settings.SITE_URL}{audiobook_path(novel.slug, audiobook.language)}",
            description=description,
            unique_id=f"{part.pk}-g{part.generation}",
            unique_id_is_permalink=False,
            pubdate=part.completed_at or part.created_at,
        )
    return feed.writeString("utf-8")
