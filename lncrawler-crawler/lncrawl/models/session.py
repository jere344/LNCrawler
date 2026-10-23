from typing import List, Optional

from .base import Model


class Session(Model):
    def __init__(
        self,
        user_input: str = "",
        output_path: str = "",
        completed: bool = False,
        download_chapters: Optional[List[int]] = None,
        good_file_name: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.user_input = user_input
        self.output_path = output_path
        self.completed = completed
        self.download_chapters = download_chapters if download_chapters is not None else []
        self.good_file_name = good_file_name
        self.update(kwargs)
