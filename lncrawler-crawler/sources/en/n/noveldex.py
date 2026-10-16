# -*- coding: utf-8 -*-
"""noveldex.io — disabled: paywalled, DRM-gated reader.

The novel and chapter pages are server-rendered (the reader keeps an
``initialBuckets``/chapter id table in its RSC payload), but the actual chapter
text is not:

* ``GET /api/chapters/content?chapterId=...`` returns ``401 Unauthorized`` to
  guests, even for chapters the page marks ``isLocked: false``.
* The browser reader fetches AES-GCM encrypted ``fragments`` and decrypts them
  client-side with a per-chapter key from ``/api/fragments/<id>/key``, behind an
  interactive-auth + fingerprint/behaviour trust-score gate.
* ``robots.txt`` disallows ``/api/`` and sets ``ai-input=no``; the operator's
  ``/ai.txt`` and ``/llms.txt`` explicitly forbid automated extraction.

There is no native path and no metadata worth scraping without the DRM bypass,
so the source is disabled rather than shipping a broken/browser-bypass crawler.
"""

from lncrawl.core.crawler import Crawler


class NovelDexCrawler(Crawler):
    base_url = ["https://noveldex.io/", "https://www.noveldex.io/"]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Reader content is DRM-gated: /api/chapters/content returns 401 to guests "
        "and the browser decrypts AES-GCM fragments behind an interactive-auth / "
        "behaviour trust-score gate. robots.txt disallows /api/ and ai.txt/llms.txt "
        "forbid automated extraction."
    )
