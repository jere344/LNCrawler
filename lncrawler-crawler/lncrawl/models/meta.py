from typing import Optional

from .base import Model
from .novel import Novel
from .session import Session


class MetaInfo(Model):
    def __init__(
        self,
        novel: Optional[Novel] = None,
        session: Optional[Session] = None,
        **kwargs,
    ) -> None:
        self.novel = novel
        self.session = session
        self.update(kwargs)

    @staticmethod
    def from_novel(novel: Novel, session: Optional[Session] = None) -> "MetaInfo":
        return MetaInfo(novel=novel, session=session)
