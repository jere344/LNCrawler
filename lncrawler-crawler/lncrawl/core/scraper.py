import base64
import ipaddress
import logging
import os
import random
import socket
from functools import lru_cache
from io import BytesIO
from typing import Any, Callable, Dict, MutableMapping, Optional, Tuple, Union
from urllib.parse import ParseResult, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi
from PIL import Image, UnidentifiedImageError
from tenacity import (retry, retry_if_exception, stop_after_attempt,
                      wait_random_exponential)

from ..assets.user_agents import user_agents
from ..constants import TIMEOUT
from .exeptions import FallbackToBrowser, LNException
from .soup import SoupMaker
from .taskman import TaskManager

logger = logging.getLogger(__name__)

try:  # curl_cffi versions differ in where RequestsError lives
    from curl_cffi.requests.errors import RequestsError as _CurlError
except Exception:  # pragma: no cover
    try:
        from curl_cffi.requests.exceptions import RequestException as _CurlError
    except Exception:
        _CurlError = Exception  # type: ignore[assignment,misc]

# curl_cffi sentence about the browser TLS fingerprint to impersonate.
DEFAULT_IMPERSONATE = os.getenv("LNCRAWL_IMPERSONATE", "chrome")


@lru_cache(maxsize=2048)
def _host_is_public(host: str) -> bool:
    """Whether every address ``host`` resolves to is a public IP.

    Blocks blind SSRF: a crawled page can point an image/cover URL at an
    internal address (loopback/private/link-local/cloud metadata) and make the
    server fetch it. Cached, so per-request cost is nil; DNS-rebinding is out of
    scope for this threat model.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def merge_headers(
    base: Optional[MutableMapping], extra: Optional[MutableMapping]
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(extra or {})
    lowered = {k.lower() for k in out}
    for key, value in (base or {}).items():
        if key.lower() not in lowered:
            out[key] = value
    return out


def _retry_wait(retry_state) -> float:
    """Wait per a ``Retry-After`` header, else random exponential backoff.

    LiteSpeed/Cloudflare throttle by IP and tell the client how long to hold
    off; ignoring the header makes the retry burn its whole budget in seconds
    and fail a request that one compliant sleep would have served.
    """
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    headers = getattr(getattr(exc, "response", None), "headers", None)
    retry_after = headers.get("Retry-After") if headers is not None else None
    if retry_after is not None:
        try:
            return min(float(retry_after), 120.0)
        except (TypeError, ValueError):
            pass  # HTTP-date form: fall back to exponential
    return wait_random_exponential(multiplier=0.5, max=60)(retry_state)


class Scraper(TaskManager, SoupMaker):
    """Native request backend built on curl_cffi (TLS impersonation)."""

    def __init__(
        self,
        origin: str,
        workers: Optional[int] = None,
        parser: Optional[str] = None,
    ) -> None:
        # Sources concatenate paths directly onto home_url (f"{home_url}search"),
        # and _register() strips the trailing slash from base_url, so normalize
        # it back here or those requests hit hosts like "site.comsearch".
        self.home_url = str(origin or "")
        if self.home_url and not self.home_url.endswith("/"):
            self.home_url += "/"
        self.last_soup_url = ""
        self.last_soup = None
        self.use_proxy = os.getenv("use_proxy")
        # Per-instance default; search tightens this (see core/search.py).
        self.request_timeout = TIMEOUT

        SoupMaker.__init__(self, parser)
        self.init_scraper()
        self.change_user_agent()
        TaskManager.__init__(self, workers)

    # ------------------------------------------------------------------ #
    # Initializers
    # ------------------------------------------------------------------ #

    def init_scraper(self) -> None:
        # Verify TLS by default. Some sources serve incomplete/expired chains and
        # will now fail; set LNCRAWL_VERIFY=0 to opt back into skipping checks.
        verify = os.getenv("LNCRAWL_VERIFY", "1").lower() not in ("0", "false", "no")
        for kwargs in (
            {"impersonate": DEFAULT_IMPERSONATE, "verify": verify},
            {"verify": verify},
            {},
        ):
            try:
                self.scraper = cffi.Session(**kwargs)
                return
            except Exception:
                continue
        logger.exception("Failed to initialize curl_cffi session")
        self.scraper = cffi.Session()

    def change_user_agent(self) -> None:
        self.user_agent = random.choice(user_agents)
        try:
            self.scraper.headers["User-Agent"] = self.user_agent
        except Exception:
            pass

    def close(self) -> None:
        """Release the thread pool and the underlying curl session.

        Called when a crawler is done so a long-lived process does not
        accumulate libcurl handles/sockets across searches and downloads.
        """
        self.shutdown()
        scraper = getattr(self, "scraper", None)
        if scraper is not None:
            try:
                scraper.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def __get_proxies(self, scheme: str) -> Dict[str, str]:
        if self.use_proxy and scheme:
            return {scheme: self.use_proxy}
        return {}

    def __process_request(
        self,
        method: str,
        url: str,
        *args,
        max_retries: Optional[int] = None,
        headers: Optional[MutableMapping] = None,
        **kwargs,
    ):
        method_call: Callable = getattr(self.scraper, method)
        # Space every request on sources that configured a rate limit. Applying
        # it at the HTTP funnel (not in submit_task) covers every submission
        # path: download chapters, TOC bursts and images alike. (Browser
        # requests do not pass through here.)
        limiter = getattr(self, "_limiter", None)
        if limiter is not None:
            method_call = limiter.wrap(method_call)
        parsed = urlparse(url)

        if parsed.scheme in ("http", "https"):
            if not parsed.hostname or not _host_is_public(parsed.hostname):
                raise LNException(
                    f"Refusing to fetch non-public host: {parsed.hostname or url!r}"
                )

        kwargs = kwargs or {}
        kwargs.setdefault("allow_redirects", True)
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.request_timeout
        proxies = self.__get_proxies(parsed.scheme)
        if proxies:
            kwargs["proxies"] = proxies

        default_headers = {
            "Origin": self.home_url.strip("/"),
            "Referer": self.last_soup_url or self.home_url,
            "User-Agent": self.user_agent,
        }
        request_headers = merge_headers(default_headers, headers)

        def _is_retryable(exc: BaseException) -> bool:
            # Retry transport errors and 5xx/429, but never a plain 4xx:
            # retrying a 404/403 wastes the whole backoff budget per dead URL.
            if not isinstance(exc, _CurlError):
                return False
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return status is None or status == 429 or status >= 500

        @retry(
            stop=stop_after_attempt(
                (self.workers + 3) if max_retries is None else max_retries + 1
            ),
            wait=_retry_wait,
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        def _do_request():
            with self.domain_gate(parsed.hostname):
                response = method_call(url, *args, **kwargs, headers=request_headers)
                response.raise_for_status()
                response.encoding = "utf8"
            return response

        return _do_request()

    # ------------------------------------------------------------------ #
    # Properties / helpers
    # ------------------------------------------------------------------ #

    @property
    def origin(self) -> ParseResult:
        return urlparse(self.home_url)

    @property
    def headers(self) -> Dict[str, Any]:
        try:
            return dict(self.scraper.headers)
        except Exception:
            return {}

    def set_header(self, key: str, value: str) -> None:
        self.scraper.headers[key] = value

    @property
    def cookies(self) -> Dict[str, Optional[str]]:
        cookies = self.scraper.cookies
        if hasattr(cookies, "get_dict"):
            try:
                return dict(cookies.get_dict())
            except Exception:
                pass
        try:
            return {k: v for k, v in cookies.items()}
        except Exception:
            return {}

    def set_cookie(self, name: str, value: str) -> None:
        self.scraper.cookies.set(name, value)

    def absolute_url(self, url: str, page_url: Optional[str] = None) -> str:
        from urllib.parse import urljoin

        url = str(url or "").strip()
        if not url:
            return url
        if url.startswith("data:") or len(url) >= 1024:
            return url
        if not page_url:
            page_url = str(self.last_soup_url or self.home_url)
        return urljoin(page_url, url).rstrip("/")

    # ------------------------------------------------------------------ #
    # Request helpers
    # ------------------------------------------------------------------ #

    def get_response(
        self,
        url: str,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        **kwargs,
    ):
        return self.__process_request("get", url, timeout=timeout, **kwargs)

    def post_response(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        max_retries: Optional[int] = 0,
        **kwargs,
    ):
        return self.__process_request(
            "post", url, data=data, max_retries=max_retries, **kwargs
        )

    def submit_form(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        multipart: bool = False,
        headers: Optional[MutableMapping] = None,
        **kwargs,
    ):
        headers = merge_headers(
            {
                "Content-Type": (
                    "multipart/form-data"
                    if multipart
                    else "application/x-www-form-urlencoded; charset=UTF-8"
                )
            },
            headers,
        )
        return self.post_response(url, data=data, headers=headers, **kwargs)

    def download_file(self, url: str, output_file: str, **kwargs) -> None:
        response = self.__process_request("get", url, **kwargs)
        with open(output_file, "wb") as f:
            f.write(response.content)

    def download_image(self, url: str, headers: Optional[MutableMapping] = None, **kwargs):
        if url.startswith("data:"):
            content = base64.b64decode(url.split("base64,")[-1])
            return Image.open(BytesIO(content))

        headers = merge_headers({"Origin": None, "Referer": None}, headers)
        try:
            response = self.__process_request("get", url, headers=headers, **kwargs)
            return Image.open(BytesIO(response.content))
        except UnidentifiedImageError:
            headers = merge_headers(
                {"Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.9"},
                headers,
            )
            response = self.__process_request("get", url, headers=headers, **kwargs)
            return Image.open(BytesIO(response.content))

    def get_json(self, url: str, headers: Optional[MutableMapping] = None, **kwargs) -> Any:
        headers = merge_headers({"Accept": "application/json,text/plain,*/*"}, headers)
        return self.get_response(url, headers=headers, **kwargs).json()

    def post_json(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        **kwargs,
    ) -> Any:
        headers = merge_headers(
            {"Content-Type": "application/json", "Accept": "application/json,text/plain,*/*"},
            headers,
        )
        return self.post_response(url, data=data, headers=headers, **kwargs).json()

    def submit_form_json(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        multipart: bool = False,
        **kwargs,
    ) -> Any:
        headers = merge_headers({"Accept": "application/json,text/plain,*/*"}, headers)
        return self.submit_form(
            url, data=data, headers=headers, multipart=bool(multipart), **kwargs
        ).json()

    def get_soup(
        self,
        url: str,
        headers: Optional[MutableMapping] = None,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> BeautifulSoup:
        headers = merge_headers(
            {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}, headers
        )
        response = self.get_response(url, headers=headers, **kwargs)
        self.last_soup_url = url
        soup = self.make_soup(response, encoding)
        self.last_soup = soup
        return soup

    def post_soup(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> BeautifulSoup:
        headers = merge_headers(
            {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}, headers
        )
        response = self.post_response(url, data=data, headers=headers, **kwargs)
        return self.make_soup(response, encoding)

    def submit_form_for_soup(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        multipart: bool = False,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> BeautifulSoup:
        headers = merge_headers(
            {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}, headers
        )
        response = self.submit_form(
            url, data=data, headers=headers, multipart=bool(multipart), **kwargs
        )
        return self.make_soup(response, encoding)


__all__ = ["Scraper", "FallbackToBrowser", "LNException"]


if __name__ == "__main__":
    # Run from lncrawler-crawler/: python -m lncrawl.core.scraper
    class _Resp:
        headers = {"Retry-After": "7"}

    class _Exc:
        response = _Resp()

    class _Outcome:
        @staticmethod
        def exception():
            return _Exc()

    class _State:
        outcome = _Outcome()

    assert _retry_wait(_State()) == 7.0
    _Resp.headers = {"Retry-After": "999"}
    assert _retry_wait(_State()) == 120.0
    print("self-check OK")
