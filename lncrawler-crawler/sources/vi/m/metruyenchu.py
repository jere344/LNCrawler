# -*- coding: utf-8 -*-
"""MeTruyenChu (metruyenchu.com.vn) - Vietnamese reader, disabled as MTL.

The site describes its own library as "truyện convert" (footer: "truyện
convert mới nhất từ Metruyenchu") and the synopsis of each novel says it was
"được Convert chuyên nghiệp". The catalogue is auto-converted (machine
translated) content, which is excluded by policy, so this is a disabled stub.
"""

from lncrawl.core.crawler import Crawler


class MeTruyenChuCrawler(Crawler):
    base_url = ["https://metruyenchu.com.vn/", "https://metruyenchuvn.com/"]
    language = "vi"
    has_manga = False
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "(Machine-translated (MTL) content — extremely low quality, intentionally excluded)"
    )
