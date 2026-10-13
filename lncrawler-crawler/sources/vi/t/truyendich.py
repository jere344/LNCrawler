# -*- coding: utf-8 -*-
"""TruyenDich (truyendich.vn) - disabled as machine/LLM-translated content.

Synopses contain leftover LLM prompts (e.g. "Dịch đoạn văn từ dạng convert
Hán Việt sang thuần Việt..."), so the catalogue is likely machine/LLM-translated
from Han-Viet "convert" text. MTL is excluded by policy, so this is a disabled stub.
"""

from lncrawl.core.crawler import Crawler


class TruyenDichCrawler(Crawler):
    base_url = "https://truyendich.vn/"
    language = "vi"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "(Likely machine/LLM-translated from Han-Viet 'convert' text — leftover LLM prompts found in synopses; MTL intentionally excluded)"
    )
