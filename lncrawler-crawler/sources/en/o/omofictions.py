# -*- coding: utf-8 -*-
"""OmoFictions (omofictions.com) — officially licensed English BL web novels.

Verified 2026-10: the marketing site (Vercel/Next.js) is fully crawlable and the
public Translation API (https://api.omofictions.com) exposes series metadata:

    GET /api/v1/books/all-series            list + search (title, author, tags,
                                            cover, description, chapter count)
    GET /api/v1/books/{uuid}                full metadata + chapter list
    GET /api/v1/content/editions/{id}/chapters

but the chapter prose itself is login-gated:

    GET /api/v1/books/{uuid}/chapters/{cid}/content
        -> HTTP 401 {"code":"login_required"}

Every chapter (including ``is_free`` ones) returns 401 anonymously, and the
``/viewer/<slug>`` reader is client-rendered and fetches the same protected
endpoint. The only public text is a ~200-char teaser in ``chapters[].description``.

Since no chapter body can be retrieved without an account, this source is
disabled rather than shipped as a metadata-only crawler.
"""

import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class OmoFictionsCrawler(Crawler):
    base_url = "https://omofictions.com/"
    language = "en"

    is_disabled = True
    disable_reason = (
        "Chapter bodies are login-gated, not blocked: tested with curl_cffi "
        "browser impersonation (chrome), the API returns 200 for metadata but "
        "GET /api/v1/books/{id}/chapters/{id}/content is HTTP 401 login_required "
        "for every chapter, including the 3 is_free ones. The /viewer page has no "
        "prose in its HTML. Chapter files are EPUB-backed (content_file_url null). "
        "Not tested in a full headless browser. Still unusable anonymously."
    )
