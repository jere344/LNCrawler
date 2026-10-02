from enum import Enum
from typing import List, Optional

from .base import Model
from .chapter import Chapter
from .volume import Volume


class NovelStatus(str, Enum):
    unknown = "Unknown"
    ongoing = "Ongoing"
    completed = "Completed"
    hiatus = "Hiatus"


class Novel(Model):
    def __init__(
        self,
        url: str,
        title: str,
        authors: Optional[List[str]] = None,
        cover_url: Optional[str] = None,
        chapters: Optional[List[Chapter]] = None,
        volumes: Optional[List[Volume]] = None,
        is_rtl: Optional[bool] = None,
        synopsis: Optional[str] = None,
        language: Optional[str] = None,
        novel_tags: Optional[List[str]] = None,
        alternative_titles: Optional[List[str]] = None,
        has_manga: Optional[bool] = None,
        has_mtl: Optional[bool] = None,
        language_code: Optional[List[str]] = None,
        source: Optional[str] = None,
        editors: Optional[List[str]] = None,
        translators: Optional[List[str]] = None,
        status: Optional[NovelStatus] = NovelStatus.unknown,
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
        original_publisher: Optional[str] = None,
        english_publisher: Optional[str] = None,
        novelupdates_url: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.url = url
        self.title = title
        self.authors = authors if authors is not None else []
        self.cover_url = cover_url
        self.chapters = chapters if chapters is not None else []
        self.volumes = volumes if volumes is not None else []
        self.is_rtl = is_rtl
        self.synopsis = synopsis
        self.language = language
        self.novel_tags = novel_tags if novel_tags is not None else []
        self.alternative_titles = alternative_titles if alternative_titles is not None else []
        self.has_manga = has_manga
        self.has_mtl = has_mtl
        self.language_code = language_code if language_code is not None else []
        self.source = source
        self.editors = editors if editors is not None else []
        self.translators = translators if translators is not None else []
        self.status = status
        self.genres = genres if genres is not None else []
        self.tags = tags if tags is not None else []
        self.description = description
        self.original_publisher = original_publisher
        self.english_publisher = english_publisher
        self.novelupdates_url = novelupdates_url
        self.update(kwargs)
