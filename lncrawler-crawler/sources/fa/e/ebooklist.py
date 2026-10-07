# -*- coding: utf-8 -*-
"""ebooklist.ir — Persian site-exclusive translations, disabled.

Novel metadata is public (WordPress + Yoast JSON-LD, custom ``novel`` post type
with an ACF block: ``novel_author``, ``novel_translator``, ``novel_status``,
``novel_rating``, ``novel_alt_titles``; genres/staff/publisher taxonomies via
``/wp-json/wp/v2/novel/<id>``). The chapter list is only reachable through the
``/novel/<slug>/<chapter>/`` rewrite, and every one of those reader URLs is
answered by the site's *NovelGuard* plugin with an HTTP 200 access-denied page
("عامل کاربری غیرمجاز / دسترسی وب مستقیم مسدود است") telling the reader to use
the vendor app. The user-agent is irrelevant (tested browser and app UAs), the
browser fallback sees the same page, and the app-only export API
(``/wp-json/novelguard/v1/offline-chapter``) rejects anonymous requests with
``missing_params`` / HTTP 401. Chapter bodies are therefore app-gated, so the
source is registered but hidden until a public reader appears.
"""

from lncrawl.core.crawler import Crawler


class EbookListCrawler(Crawler):
    base_url = ["https://ebooklist.ir/"]
    language = "fa"

    is_disabled = True
    disable_reason = (
        "Chapter bodies are app-only: the NovelGuard plugin returns an access-"
        "denied page for every /novel/<slug>/<chapter>/ URL regardless of user "
        "agent, and the offline-chapter API requires an authenticated account. "
        "Metadata is public but there is no readable web chapter text."
    )
