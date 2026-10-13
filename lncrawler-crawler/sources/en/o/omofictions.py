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
        "Chapter bodies are login-gated: GET /api/v1/books/{id}/chapters/{id}/"
        "content returns HTTP 401 login_required for every chapter (even free "
        "ones), and the /viewer reader is client-rendered against the same "
        "endpoint. Official licensed/paywalled content — no anonymous prose."
    )
