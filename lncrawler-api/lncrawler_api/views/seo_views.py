"""Server-rendered pages for crawlers and social scrapers.

The public site is a client-side SPA, so non-JS clients (AI crawlers, search
bots, link-preview fetchers) only ever saw an empty shell. nginx rewrites those
User-Agents from the public content URLs to these views internally, so the URL
seen by the client is unchanged and canonical links stay consistent.

These pages are read-only: they never increment view counters and never expose
adult/R18 novels (matching the sitemap filters).
"""
import json
import os

from django.conf import settings
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from ..models import AudiobookChapter, AudiobookPart, Novel, NovelFromSource
from ..models.source_helpers import resolve_output_path
from ..models.sources_models import adult_novel_ids
from ..services import audiobook_media
from ..services.audiobook_public import (
    LISTENABLE_PART_Q,
    annotate_public_totals,
    audiobook_path,
    chapter_audio_url,
    cover_urls,
    get_visible_audiobook_or_404,
    narrator_credit,
    visible_audiobooks,
)
from ..utils import build_media_url, resolve_novel_slug
from ..utils.chapter_utils import get_chapter
from ..utils.query_helpers import preferred_source_key, public_novels
from ..utils.seo import _clean_text, _sanitize_body
from .audiobook_views import SORTS

SITE_URL = settings.SITE_URL.rstrip("/")
SITE_NAME = "LNCrawler"
DEFAULT_OG_IMAGE = f"{SITE_URL}/og-image.webp"

# Sitewide Organization entity, emitted on every page so answer engines resolve
# "LNCrawler" as a single entity. sameAs lists the only canonical external
# profile we have.
ORG = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": f"{SITE_URL}/#organization",
    "name": SITE_NAME,
    "url": f"{SITE_URL}/",
    "sameAs": ["https://github.com/jere344/LNCrawler"],
}

# Source/chapter pages can materialise a whole archive on first reader access,
# so let edges and crawlers reuse them for a while.
PAGE_CACHE_SECONDS = 3600


def _pick_default_source(sources):
    """Mirror the serializer's preferred source (see preferred_source_key)."""
    if not sources:
        return None
    return min(sources, key=preferred_source_key)


def _source_image(source):
    for path in (source.overview_picture_path, source.cover_path):
        if path and os.path.exists(resolve_output_path(path) or ""):
            return build_media_url(path)
    if source.cover_url:
        return source.cover_url
    return DEFAULT_OG_IMAGE


def _novel_image(sources):
    for source in sources:
        image = _source_image(source)
        if image != DEFAULT_OG_IMAGE:
            return image
    return DEFAULT_OG_IMAGE


def _chapter_label(chapter):
    title = (chapter.title or "").strip()
    return title or f"Chapter {chapter.chapter_id}"


def _is_adult_novel(novel):
    # Adult if more than half of its sources are; matches the sitemap filters.
    return adult_novel_ids().filter(novel_id=novel.pk).exists()


def _duration_label(seconds):
    """A length as people read it: '12 h 30 min'."""
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def _iso_duration(seconds):
    """A length as ISO 8601, e.g. PT12H30M."""
    hours, rest = divmod(round(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    text = "".join(
        f"{value}{unit}" for value, unit in ((hours, "H"), (minutes, "M"), (secs, "S")) if value
    )
    return f"PT{text or '0S'}"


def _jsonld(*objects):
    payload = json.dumps((ORG, *objects), ensure_ascii=False)
    # Never let crawled text close the script tag.
    return payload.replace("<", "\\u003c")


def _render(request, template, context, lastmod=None, status=200):
    response = render(request, template, context)
    response.status_code = status
    response["Content-Type"] = "text/html; charset=utf-8"
    response["Cache-Control"] = f"public, max-age={PAGE_CACHE_SECONDS}"
    # Same URL serves SEO HTML or the SPA shell depending on User-Agent, so any
    # shared cache must key on it.
    response["Vary"] = "User-Agent"
    if lastmod is not None:
        response["Last-Modified"] = lastmod.strftime("%a, %d %b %Y %H:%M:%S GMT")
    return response


def _gone(request, status, message):
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='robots' content='noindex'></head><body>"
        f"<h1>{status}</h1><p>{message}</p></body></html>"
    )
    return HttpResponse(body, status=status, content_type="text/html; charset=utf-8")


def seo_home(request):
    novels = (
        public_novels(Novel.objects.all())
        .order_by("-created_at")
        .only("slug", "title", "updated_at")[:100]
    )
    description = (
        "Read thousands of Asian light novels online for free. Browse by "
        "popularity, rating or latest updates on LNCrawler."
    )
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": f"{SITE_URL}/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{SITE_URL}/novels/search?query={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }
    return _render(
        request,
        "seo/home.html",
        {
            "title": f"{SITE_NAME} - Read Light Novels Online",
            "description": description,
            "keywords": "light novels, web novels, read online",
            "canonical": f"{SITE_URL}/",
            "og_image": DEFAULT_OG_IMAGE,
            "og_type": "website",
            "jsonld": _jsonld(website),
            "novels": novels,
            "lang": "en",
            "site_url": SITE_URL,
        },
    )


def seo_novel(request, novel_slug):
    novel = resolve_novel_slug(novel_slug)
    if novel.is_dmca:
        return _gone(request, 451, "This work is unavailable due to a DMCA request.")

    sources = list(
        novel.sources.select_related("external_source")
        .prefetch_related("authors", "tags", "alternative_titles")
        .exclude(Q(source_slug__isnull=True) | Q(source_slug=""))
        .annotate(
            chapter_total=Count("chapters"),
            # Read by preferred_source_key so it doesn't COUNT per source.
            annotated_available_chapters_count=Count(
                "chapters", filter=Q(chapters__has_content=True)
            ),
        )
    )
    if not sources or _is_adult_novel(novel):
        raise Http404("Novel not available")

    primary = _pick_default_source(sources)
    synopsis = _clean_text(primary.synopsis, 320)
    author_names = [a.name for a in primary.authors.all()]
    description = (
        f"Read {novel.title} online. {synopsis}"
        if synopsis
        else f"Read {novel.title} online for free on {SITE_NAME}. "
        f"Available in {len(sources)} source(s)."
    )

    book = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": novel.title,
        "url": f"{SITE_URL}/novels/{novel.slug}/",
        "inLanguage": sorted({s.language for s in sources if s.language})
        or primary.language
        or "en",
    }
    if author_names:
        book["author"] = [{"@type": "Person", "name": n} for n in author_names]
    if synopsis:
        book["description"] = synopsis
    if novel.updated_at:
        book["dateModified"] = novel.updated_at.isoformat()
    image = _novel_image(sources)
    if image:
        book["image"] = image
    ratings = list(novel.ratings.values_list("rating", flat=True))
    if ratings:
        book["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(sum(ratings) / len(ratings), 1),
            "ratingCount": len(ratings),
            "bestRating": 5,
            "worstRating": 1,
        }
    tags = [t.name for t in primary.tags.all()][:15]
    if tags:
        book["genre"] = tags
    if primary.novelupdates_url:
        book["sameAs"] = primary.novelupdates_url
    alt_titles = [t.name for t in primary.alternative_titles.all()][:5]
    if alt_titles:
        book["alternateName"] = alt_titles
    publisher = primary.original_publisher or primary.english_publisher
    if publisher:
        book["publisher"] = {"@type": "Organization", "name": publisher}

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": novel.title,
                "item": f"{SITE_URL}/novels/{novel.slug}/",
            },
        ],
    }

    audiobook_links = [
        {"url": f"{SITE_URL}{audiobook_path(novel.slug, a.language)}", "language": a.language}
        for a in visible_audiobooks(adult='exclude').filter(novel=novel).order_by("language")
    ]

    return _render(
        request,
        "seo/novel.html",
        {
            "title": f"{novel.title} - Read Light Novel Online | {SITE_NAME}",
            "description": description,
            "keywords": ", ".join([novel.title, *author_names, *tags][:15]),
            "canonical": f"{SITE_URL}/novels/{novel.slug}/",
            "og_image": image,
            "og_type": "book",
            "jsonld": _jsonld(book, crumbs),
            "novel": novel,
            "primary": primary,
            "sources": sources,
            "synopsis": synopsis,
            "languages": sorted({s.language for s in sources if s.language}),
            "chapter_total": sum(getattr(s, "chapter_total", 0) or 0 for s in sources),
            "tags": tags,
            "audiobook_links": audiobook_links,
            "lang": primary.language or "en",
            "site_url": SITE_URL,
        },
        lastmod=novel.updated_at,
    )


def seo_source(request, novel_slug, source_slug):
    novel = resolve_novel_slug(novel_slug)
    if novel.is_dmca:
        return _gone(request, 451, "This work is unavailable due to a DMCA request.")
    source = get_object_or_404(
        NovelFromSource.objects.select_related("novel", "external_source")
        .prefetch_related("authors", "tags", "alternative_titles")
        .filter(novel=novel),
        source_slug=source_slug,
    )
    if _is_adult_novel(novel):
        raise Http404("Source not available")

    synopsis = _clean_text(source.synopsis, 320)
    source_name = source.external_source.source_name
    author_names = [a.name for a in source.authors.all()]
    description = (
        f"Read {source.title} from {source_name}. {synopsis}"
        if synopsis
        else f"Read {source.title} from {source_name} on {SITE_NAME}."
    )
    image = _source_image(source)
    chapterlist_url = f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/chapterlist/"

    book = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": source.title,
        "url": f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/",
        "inLanguage": source.language,
        "bookFormat": "https://schema.org/EBook",
    }
    if author_names:
        book["author"] = [{"@type": "Person", "name": n} for n in author_names]
    if synopsis:
        book["description"] = synopsis
    if image:
        book["image"] = image
    tags = [t.name for t in source.tags.all()][:15]
    if tags:
        book["genre"] = tags
    if source.novelupdates_url:
        book["sameAs"] = source.novelupdates_url
    alt_titles = [t.name for t in source.alternative_titles.all()][:5]
    if alt_titles:
        book["alternateName"] = alt_titles
    publisher = source.original_publisher or source.english_publisher
    if publisher:
        book["publisher"] = {"@type": "Organization", "name": publisher}
    if source.last_chapter_update:
        book["dateModified"] = source.last_chapter_update.isoformat()

    # Aggregate ratings live on the novel, not the source.
    ratings = list(novel.ratings.values_list("rating", flat=True))
    if ratings:
        book["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(sum(ratings) / len(ratings), 1),
            "ratingCount": len(ratings),
            "bestRating": 5,
            "worstRating": 1,
        }

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": novel.title,
                "item": f"{SITE_URL}/novels/{novel.slug}/",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": source_name,
                "item": f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/",
            },
        ],
    }

    return _render(
        request,
        "seo/source.html",
        {
            "title": f"{source.title} ({source_name}) - Read on {SITE_NAME}",
            "description": description,
            "keywords": ", ".join([source.title, source_name, *author_names, *tags][:15]),
            "canonical": f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/",
            "og_image": image,
            "og_type": "book",
            "jsonld": _jsonld(book, crumbs),
            "novel": novel,
            "source": source,
            "source_name": source_name,
            "synopsis": synopsis,
            "chapterlist_url": chapterlist_url,
            "lang": source.language or "en",
            "site_url": SITE_URL,
        },
        lastmod=source.last_chapter_update or source.updated_at,
    )


def seo_chapterlist(request, novel_slug, source_slug):
    novel = resolve_novel_slug(novel_slug)
    if novel.is_dmca:
        return _gone(request, 451, "This work is unavailable due to a DMCA request.")
    source = get_object_or_404(
        NovelFromSource.objects.select_related("novel", "external_source").filter(
            novel=novel
        ),
        source_slug=source_slug,
    )
    if _is_adult_novel(novel):
        raise Http404("Source not available")

    chapters = (
        source.chapters.only("chapter_id", "title", "has_content").order_by("chapter_id")
    )
    count = chapters.count()
    source_name = source.external_source.source_name
    image = _source_image(source)
    canonical = f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/chapterlist/"

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": novel.title,
                "item": f"{SITE_URL}/novels/{novel.slug}/",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": f"{source_name} chapters",
                "item": canonical,
            },
        ],
    }

    return _render(
        request,
        "seo/chapterlist.html",
        {
            "title": f"Chapter List - {source.title} ({source_name}) | {SITE_NAME}",
            "description": (
                f"Browse all {count} chapters for {source.title} from source "
                f"{source_name} on {SITE_NAME}. Read light novels online with a "
                f"clean reading experience."
            ),
            "keywords": f"{source.title}, {source_name}, chapter list, read light novel",
            "canonical": canonical,
            "og_image": image,
            "og_type": "website",
            "jsonld": _jsonld(crumbs),
            "novel": novel,
            "source": source,
            "source_name": source_name,
            "chapters": chapters,
            "count": count,
            "lang": source.language or "en",
            "site_url": SITE_URL,
        },
        lastmod=source.last_chapter_update or source.updated_at,
    )


def seo_chapter(request, novel_slug, source_slug, chapter_number):
    novel = resolve_novel_slug(novel_slug)
    if novel.is_dmca:
        return _gone(request, 451, "This work is unavailable due to a DMCA request.")
    source = get_object_or_404(
        NovelFromSource.objects.select_related("novel", "external_source").filter(
            novel=novel
        ),
        source_slug=source_slug,
    )
    if _is_adult_novel(novel):
        raise Http404("Source not available")
    chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)
    if not chapter.has_content:
        raise Http404("Chapter content not available")

    parsed = get_chapter(source.absolute_source_path, chapter.chapter_id) or {}
    body = parsed.get("body") or ""
    if not body:
        raise Http404("Chapter content not available")

    images_path = (
        build_media_url(f"{source.source_path}/images") if chapter.images else None
    )
    body = _sanitize_body(body, images_path)

    label = _chapter_label(chapter)
    source_name = source.external_source.source_name
    description = (
        f"Read {label} of the light novel {source.title}. "
        + _clean_text(body, 150)
    )
    image = _source_image(source)
    canonical = (
        f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/"
        f"chapter/{chapter.chapter_id}/"
    )

    article = {
        "@context": "https://schema.org",
        "@type": "Chapter",
        "name": label,
        "headline": f"{label} - {source.title}",
        "url": canonical,
        "inLanguage": source.language,
        "isPartOf": {
            "@type": "Book",
            "name": source.title,
            "url": f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/",
        },
        "publisher": {"@id": f"{SITE_URL}/#organization"},
    }
    if image:
        article["image"] = image

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": source.title,
                "item": f"{SITE_URL}/novels/{novel.slug}/{source.source_slug}/",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": label,
                "item": canonical,
            },
        ],
    }

    return _render(
        request,
        "seo/chapter.html",
        {
            "title": f"Read {label} - {source.title} | {SITE_NAME}",
            "description": description,
            "keywords": f"{source.title}, {source_name}, {label}, read light novel",
            "canonical": canonical,
            "og_image": image,
            "og_type": "article",
            "jsonld": _jsonld(article, crumbs),
            "novel": novel,
            "source": source,
            "source_name": source_name,
            "chapter": chapter,
            "label": label,
            "body": body,
            "lang": source.language or "en",
            "site_url": SITE_URL,
        },
        lastmod=source.last_chapter_update or source.updated_at,
    )


SEO_AUDIOBOOK_LIST_SIZE = 100


def seo_audiobooks(request):
    audiobooks = (
        annotate_public_totals(visible_audiobooks(adult='exclude'))
        .order_by(*SORTS["popular"])[:SEO_AUDIOBOOK_LIST_SIZE]
    )
    items = [
        {
            "title": audiobook.novel.title,
            "url": f"{SITE_URL}{audiobook_path(audiobook.novel.slug, audiobook.language)}",
            "duration": _duration_label(audiobook.public_duration_s),
        }
        for audiobook in audiobooks
    ]
    return _render(
        request,
        "seo/audiobooks.html",
        {
            "title": f"Generated audiobooks - Listen to Light Novels | {SITE_NAME}",
            "description": (
                "Generated multi-voice audiobooks of popular light novels on LNCrawler, "
                "streamable and downloadable as .m4b."
            ),
            "keywords": "audiobooks, light novels, listen online",
            "canonical": f"{SITE_URL}/audiobooks/",
            "og_image": DEFAULT_OG_IMAGE,
            "og_type": "website",
            "jsonld": _jsonld(),
            "items": items,
            "lang": "en",
            "site_url": SITE_URL,
        },
    )


def seo_audiobook(request, novel_slug):
    novel = resolve_novel_slug(novel_slug)
    if novel.is_dmca:
        return _gone(request, 451, "This work is unavailable due to a DMCA request.")
    audiobook = get_visible_audiobook_or_404(
        None, novel_slug, request.GET.get("lang", "en"), adult='exclude'
    )

    parts = list(
        AudiobookPart.objects.filter(LISTENABLE_PART_Q, audiobook=audiobook).order_by("index")
    )
    first_chapter = (
        AudiobookChapter.objects.filter(part__in=parts)
        .select_related("part")
        .order_by("part__index", "chapter__chapter_id")
        .first()
    )
    audio_url = chapter_audio_url(first_chapter) if first_chapter else None
    cover_jpg = cover_urls(audiobook)[1]

    synopsis = _clean_text(audiobook.source.synopsis, 320)
    author_names = sorted(author.name for author in audiobook.source.authors.all())
    narrator = narrator_credit(audiobook)
    disclaimer = audiobook_media.audiobook_metadata(audiobook)['disclaimer']
    canonical = f"{SITE_URL}{audiobook_path(novel.slug, audiobook.language)}"
    description = f"Generated audiobook: {novel.title}, narrated with generated voices. {synopsis}".strip()

    book = {
        "@context": "https://schema.org",
        "@type": "Audiobook",
        "name": novel.title,
        "url": canonical,
        "readBy": {"@type": "Person", "name": narrator},
        "duration": _iso_duration(audiobook.public_duration_s),
        "inLanguage": audiobook.language,
        "bookFormat": "https://schema.org/AudiobookFormat",
        "publisher": {"@id": f"{SITE_URL}/#organization"},
    }
    if author_names:
        book["author"] = [{"@type": "Person", "name": n} for n in author_names]
    if synopsis:
        book["description"] = synopsis
    if cover_jpg:
        book["image"] = cover_jpg
    if audiobook.first_published_at:
        book["datePublished"] = audiobook.first_published_at.date().isoformat()

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Audiobooks",
                "item": f"{SITE_URL}/audiobooks/",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": novel.title,
                "item": canonical,
            },
        ],
    }

    return _render(
        request,
        "seo/audiobook.html",
        {
            "title": f"{novel.title} \u2013 Generated audiobook",
            "description": description,
            "keywords": ", ".join([novel.title, *author_names][:15]),
            "canonical": canonical,
            "og_image": cover_jpg or DEFAULT_OG_IMAGE,
            "og_type": "book",
            "jsonld": _jsonld(book, crumbs),
            "novel": novel,
            "authors": author_names,
            "narrator": narrator,
            "disclaimer": disclaimer,
            "duration": _duration_label(audiobook.public_duration_s),
            "synopsis": synopsis,
            "parts": [
                {
                    "index": part.index,
                    "chapter_start": part.chapter_start,
                    "chapter_end": part.chapter_end,
                    "duration": _duration_label(part.duration_s),
                }
                for part in parts
            ],
            "audio_url": audio_url,
            "cover_jpg": cover_jpg,
            "novel_url": f"{SITE_URL}/novels/{novel.slug}/",
            "feed_url": (
                f"{settings.SITE_API_URL}/audiobooks/{novel.slug}/feed.xml"
                f"?lang={audiobook.language}"
            ),
            "lang": audiobook.language,
            "site_url": SITE_URL,
        },
        lastmod=audiobook.last_part_at,
    )
