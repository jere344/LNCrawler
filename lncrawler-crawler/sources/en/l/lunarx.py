# -*- coding: utf-8 -*-
"""lunarx.to — disabled: chapter text and EPUB volumes are wrapped in a rotating
custom DRM and the public content endpoint serves honeypots.

The site is a Next.js SPA behind Cloudflare (plain curl gets the "Just a
moment..." challenge; curl_cffi with ``impersonate="chrome"`` passes). Metadata
and chapter *lists* are readable over the public API at ``api.lunarx.to``
(``GET /api/novels/db/search``, ``GET /api/novels/chapters/<slug>``), but the
actual prose is not:

* ``GET /api/novels/r/<token>`` returns the chapter body encrypted. The token is
  minted client-side from a payload encrypting ``slug|language`` with a key
  derived from two rotating server-sealed values (``axis``/``pitch``); the
  response is then decrypted with CryptoJS AES-CBC using a key derived from
  those sealed values plus a SHA-256 hash of a WebCrypto P-256 public JWK. The
  sealed keys go stale every ~50 min and force a page reload for fresh ones.
* Downloaded EPUBs (``GET /api/novels/epub/<token>``) are the same DRM: the file
  is a ~2.8 KB encrypted blob, not a ZIP/EPUB.
* A garbage token returns HTTP 200 with fake placeholder text ending in
  ``[content protected]``; the reader JS explicitly detects these honeypots.

There is no native path and no metadata worth scraping without reproducing the
DRM, so the source is disabled rather than shipping a brittle bypass crawler.
See ``sources/en/n/noveldex.py`` for the same convention.
"""

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException


class LunarXCrawler(Crawler):
    base_url = ["https://lunarx.to/", "https://www.lunarx.to/"]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Chapter text and EPUB volumes are AES-encrypted with rotating "
        "server-issued keys (custom DRM) and the plain content API serves "
        "honeypot placeholders, so content cannot be downloaded."
    )

    def read_novel_info(self) -> None:
        raise LNException(self.disable_reason)
