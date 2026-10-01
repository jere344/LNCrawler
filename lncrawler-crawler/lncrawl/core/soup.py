import logging
from typing import Optional, Union

from bs4 import BeautifulSoup, Tag

from .exeptions import LNException

logger = logging.getLogger(__name__)

DEFAULT_PARSER = "lxml"


class SoupMaker:
    def __init__(self, parser: Optional[str] = None) -> None:
        self.init_parser(parser)

    def init_parser(self, parser: Optional[str] = None) -> None:
        """Select the BeautifulSoup parser. Sources may override this."""
        self._parser = parser or DEFAULT_PARSER

    def make_soup(
        self,
        data: Union[object, bytes, str],
        encoding: Optional[str] = None,
    ) -> BeautifulSoup:
        if hasattr(data, "content"):
            return self.make_soup(getattr(data, "content"), encoding)
        if isinstance(data, bytes):
            html = data.decode(encoding or "utf8", "ignore")
        elif isinstance(data, str):
            html = data
        else:
            raise LNException("Could not parse response")
        return BeautifulSoup(html, features=self._parser)

    def make_tag(
        self,
        data: Union[object, bytes, str],
        encoding: Optional[str] = None,
    ) -> Tag:
        soup = self.make_soup(data, encoding)
        body = soup.find("body")
        assert body is not None
        return next(body.children)
