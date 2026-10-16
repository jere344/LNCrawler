# -*- coding: utf-8 -*-
"""TangThuVien - disabled source.

Disabled: Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host.
"""

from lncrawl.core.crawler import Crawler


class TangThuVienCrawler(Crawler):
    base_url = [
        "https://truyen.tangthuvien.vn/",
        "https://tangthuvien.vn/",
    ]
    language = "vi"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host'
