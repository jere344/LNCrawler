from typing import Dict, List, Optional, Tuple

from .base import Model
from .formats import OutputFormat


class Session(Model):
    def __init__(
        self,
        user_input: str = "",
        output_path: str = "",
        completed: bool = False,
        pack_by_volume: bool = False,
        download_chapters: Optional[List[int]] = None,
        good_file_name: Optional[str] = None,
        no_append_after_filename: bool = False,
        login_data: Optional[Tuple[str, str]] = None,
        output_formats: Optional[Dict[OutputFormat, bool]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> None:
        self.user_input = user_input
        self.output_path = output_path
        self.completed = completed
        self.pack_by_volume = pack_by_volume
        self.download_chapters = download_chapters if download_chapters is not None else []
        self.good_file_name = good_file_name
        self.no_append_after_filename = no_append_after_filename
        self.login_data = login_data
        self.output_formats = output_formats if output_formats is not None else {}
        self.headers = headers if headers is not None else {}
        self.cookies = cookies if cookies is not None else {}
        self.proxies = proxies if proxies is not None else {}
        self.update(kwargs)
