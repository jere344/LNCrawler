import logging

from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)


class CkandawritesOnline(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    base_url = ["https://ckandawrites.online/"]

    def initialize(self) -> None:
        super().initialize()
        # The site's bot check blocks curl_cffi's default chrome TLS
        # fingerprint but lets firefox through.
        self.scraper.impersonate = "firefox"

