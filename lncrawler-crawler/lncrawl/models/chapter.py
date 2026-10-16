from typing import Dict, Optional

from .base import Model


class Chapter(Model):
    def __init__(
        self,
        id: int,
        url: str = "",
        title: str = "",
        volume: Optional[int] = None,
        volume_title: Optional[str] = None,
        body: Optional[str] = None,
        images: Optional[Dict[str, str]] = None,
        success: bool = False,
        **kwargs,
    ) -> None:
        self.id = id
        self.url = url
        self.title = title
        self.volume = volume
        self.volume_title = volume_title
        self.body = body
        self.images = images if images is not None else {}
        self.success = success
        self.update(kwargs)

    @staticmethod
    def without_body(item: "Chapter") -> "Chapter":
        result = item.copy()
        result.body = None
        return result
