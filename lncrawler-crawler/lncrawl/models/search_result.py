from typing import Optional

from .base import Model


class SearchResult(Model):
    def __init__(
        self,
        title: str,
        url: str,
        info: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.title = title
        self.url = url
        self.info = info
        self.update(kwargs)
