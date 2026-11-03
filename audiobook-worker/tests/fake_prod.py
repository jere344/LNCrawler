"""In-memory fake of the lncrawler audiobook-worker contract (v1), for tests and local runs.

    python tests/fake_prod.py --chapters-dir <novel-source> --count 3 --port 8765 \
        --token t --language en [--out fake_prod_out]

Serves one part built from the first --count chapters of a lncrawler JSON folder (or synthetic
chapters when --chapters-dir is omitted). Prints state changes. On complete it writes the
received cast and qa to <out>/complete.json and keeps each uploaded ogg in <out>/.

The EPUB writer below is copied from a former bench script (removed with the bench).
"""

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from typing import Any

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_BITRATE_BPS = 40_000
MIN_DURATION_S = 10.0
API = "/api/audiobook-worker/"


class _Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paras, self._cur = [], []

    def _flush(self):
        text = " ".join("".join(self._cur).split())
        if text:
            self.paras.append(text)
        self._cur = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "div", "h1", "h2", "h3", "li"):
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("p", "div", "h1", "h2", "h3", "li"):
            self._flush()

    def handle_data(self, data):
        self._cur.append(data)

    def close(self):
        super().close()
        self._flush()


def paragraphs(body_html):
    parser = _Paragraphs()
    parser.feed(body_html or "")
    parser.close()
    return [html.unescape(p) for p in parser.paras]


def novel_meta(source_dir):
    title = os.path.basename(os.path.dirname(source_dir.rstrip("/")))
    author = "Unknown"
    try:
        with open(os.path.join(source_dir, "meta.json"), encoding="utf-8") as f:
            novel = json.load(f).get("novel") or {}
        title = novel.get("title") or title
        authors = novel.get("authors") or novel.get("author")
        if isinstance(authors, list) and authors:
            author = ", ".join(map(str, authors))
        elif isinstance(authors, str) and authors.strip():
            author = authors.strip()
    except (OSError, ValueError):
        pass
    return title, author


def xhtml(title, paras, lang):
    body = "\n".join(f"<p>{html.escape(p)}</p>" for p in paras)
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}">'
            f"<head><title>{html.escape(title)}</title></head>"
            f"<body><h1>{html.escape(title)}</h1>\n{body}</body></html>")


def write_epub(path, *, title, author, series, index, lang, chapters):
    book_id = f"urn:uuid:{uuid.uuid4()}"
    items, spine, nav_li, ncx_points = [], [], [], []
    for n, (ch_title, _) in enumerate(chapters, 1):
        items.append(f'<item id="c{n}" href="c{n}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{n}"/>')
        nav_li.append(f'<li><a href="c{n}.xhtml">{html.escape(ch_title)}</a></li>')
        ncx_points.append(f'<navPoint id="p{n}" playOrder="{n}"><navLabel><text>{html.escape(ch_title)}</text>'
                          f'</navLabel><content src="c{n}.xhtml"/></navPoint>')
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>{lang}</dc:language>
    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
    <meta name="calibre:series" content="{html.escape(series)}"/>
    <meta name="calibre:series_index" content="{index}"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {''.join(items)}
  </manifest>
  <spine toc="ncx">{''.join(spine)}</spine>
</package>"""
    nav = (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
           f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           f'<head><title>{html.escape(title)}</title></head><body>'
           f'<nav epub:type="toc"><ol>{"".join(nav_li)}</ol></nav></body></html>')
    ncx = (f'<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{book_id}"/></head>'
           f'<docTitle><text>{html.escape(title)}</text></docTitle><navMap>{"".join(ncx_points)}</navMap></ncx>')
    container = ('<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        for n, (ch_title, paras) in enumerate(chapters, 1):
            z.writestr(f"OEBPS/c{n}.xhtml", xhtml(ch_title, paras, lang), compress_type=zipfile.ZIP_DEFLATED)




# ---------------------------------------------------------------------------
# Part construction


@dataclass
class FakeChapter:
    chapter_id: int
    number: int
    title: str
    paragraphs: list[str]

    @property
    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)


@dataclass
class FakePart:
    part_id: str
    title: str
    author: str
    index: int
    chapters: list[FakeChapter]
    epub: bytes = b""
    language: str = "en"

    def claim_json(self) -> dict[str, Any]:
        words = sum(c.word_count for c in self.chapters)
        return {
            "part_id": self.part_id,
            "audiobook_id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.title)),
            "series": {"title": self.title, "authors": [self.author], "language": self.language, "slug": "fake-novel"},
            "part": {
                "index": self.index,
                "total_known": self.index,
                "chapter_start": self.chapters[0].number,
                "chapter_end": self.chapters[-1].number,
                "word_count": words,
            },
            "chapters": [
                {"chapter_id": c.chapter_id, "number": c.number, "title": c.title, "word_count": c.word_count}
                for c in self.chapters
            ],
            "epub_url": f"{API}parts/{self.part_id}/epub",
            "previous_cast": {},
            "lease_until": "2026-11-02T03:15:00Z",
        }


_SYNTH_SENTENCES = [
    "The lantern swayed above the cart as the road bent toward the river.",
    "She counted the bridges twice, once for the map and once for herself.",
    "Nobody in the village would say where the letters had come from.",
    "He answered without turning, his voice low under the rain.",
    "By morning the frost had covered every field between the hills.",
    "They argued about the price of bread until the bell rang for vespers.",
]


def synthetic_chapters(count: int, paragraphs_per_chapter: int = 40) -> list[tuple[str, list[str]]]:
    out = []
    for n in range(1, count + 1):
        paras = [
            _SYNTH_SENTENCES[(n + i) % len(_SYNTH_SENTENCES)] + f" Chapter {n}, paragraph {i + 1}."
            for i in range(paragraphs_per_chapter)
        ]
        out.append((f"Chapter {n}: The Road", paras))
    return out


def load_chapters(chapters_dir: str, count: int) -> tuple[str, str, list[tuple[str, list[str]]]]:
    """Reads <dir>/json/NNNNN.json (or <dir>/NNNNN.json). Returns (title, author, [(title, paragraphs)])."""
    json_dir = os.path.join(chapters_dir, "json")
    if not os.path.isdir(json_dir):
        json_dir = chapters_dir
    title, author = novel_meta(chapters_dir)
    files = sorted(f for f in os.listdir(json_dir) if re.fullmatch(r"\d+\.json", f))[:count]
    if len(files) < count:
        raise SystemExit(f"only {len(files)} chapters in {json_dir}, need {count}")
    chapters = []
    for f in files:
        with open(os.path.join(json_dir, f), encoding="utf-8") as fh:
            data = json.load(fh)
        paras = paragraphs(data.get("body"))
        ch_title = data.get("title") or f"Chapter {int(f[:-5])}"
        if paras and paras[0].strip().lower() == ch_title.strip().lower():
            paras = paras[1:]
        chapters.append((ch_title, paras))
    return title, author, chapters


def build_part(
    *,
    language: str = "en",
    count: int,
    chapters_dir: str | None = None,
    part_id: str | None = None,
) -> FakePart:
    if chapters_dir:
        title, author, raw = load_chapters(chapters_dir, count)
    else:
        title, author, raw = "Fake Novel", "Test Author", [(t, p) for t, p in synthetic_chapters(count)]
    chapters = [
        FakeChapter(chapter_id=1000 + i, number=i + 1, title=ch_title, paragraphs=paras)
        for i, (ch_title, paras) in enumerate(raw)
    ]
    part = FakePart(
        part_id=part_id or str(uuid.uuid4()),
        title=title,
        author=author,
        index=1,
        language=language,
        chapters=chapters,
    )
    fd, tmp = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    try:
        write_epub(
            tmp,
            title=f"{title} - Part 1",
            author=author,
            series=title,
            index=1,
            lang="en",
            chapters=[(c.title, c.paragraphs) for c in chapters],
        )
        with open(tmp, "rb") as fh:
            part.epub = fh.read()
    finally:
        os.remove(tmp)
    return part


# ---------------------------------------------------------------------------
# Server state and checks


def probe_failures(path: str) -> list[str]:
    """Subset of prod's upload checks: codec, container, channels, rate, duration, bitrate."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ["not a media file"]
    info = json.loads(proc.stdout or "{}")
    fmt = info.get("format", {})
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        return ["no audio stream"]
    stream = audio_streams[0]
    failures = []
    if stream.get("codec_name") != "opus":
        failures.append(f"codec {stream.get('codec_name')}, want opus")
    if "ogg" not in str(fmt.get("format_name", "")):
        failures.append("container is not ogg")
    if int(stream.get("channels") or 0) != 1:
        failures.append("not mono")
    if int(stream.get("sample_rate") or 0) != 48000:
        failures.append("sample rate is not 48000")
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        return failures + ["no declared duration"]
    if duration <= MIN_DURATION_S:
        failures.append(f"duration {duration:.1f} s is not over 10 s")
    elif os.path.getsize(path) * 8 / duration > MAX_BITRATE_BPS:
        failures.append("average bitrate above 40 kbps")
    return failures


class FakeState:
    def __init__(self, part: FakePart, token: str, *, out_dir: str | None, log) -> None:
        self.part = part
        self.token = token
        self.out_dir = out_dir
        self.log = log
        self.lock = threading.Lock()
        self.owner: str | None = None
        self.claimed = False
        self.cancelled = False
        self.uploads: dict[int, tuple[str, bytes]] = {}
        self.heartbeats: list[dict[str, Any]] = []
        self.pings: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.completed: dict[str, Any] | None = None

    def cancel(self) -> None:
        with self.lock:
            self.cancelled = True
        self.log("part cancelled: heartbeats and part calls now get 409")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-prod/1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet; the state log is printed instead
        return

    @property
    def fake(self) -> FakeState:
        return self.server.fake  # type: ignore[attr-defined]

    # -- helpers ---------------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str = "application/json", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj: Any, headers: dict[str, str] | None = None) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), headers=headers)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _auth_ok(self) -> bool:
        if self.headers.get("Authorization") != f"Token {self.fake.token}":
            self._error(401, "bad token")
            return False
        if self.headers.get("X-Worker-Contract") != "1":
            self._error(400, "X-Worker-Contract: 1 is required")
            return False
        return True

    def _json_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"null")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._error(400, "body must be a JSON object")
            return None
        return body

    def _part_guard(self, part_id: str) -> bool:
        if not self._auth_ok():
            return False
        worker = self.headers.get("X-Worker-Id")
        if not worker:
            self._error(400, "X-Worker-Id header is required")
            return False
        if part_id != self.fake.part.part_id:
            self._error(404, "no such part")
            return False
        if self.fake.owner is not None and worker != self.fake.owner:
            self._error(409, "part belongs to another worker")
            return False
        if self.fake.cancelled:
            self._error(409, "part cancelled")
            return False
        return True

    def _route(self) -> tuple[str, str | None, str | None]:
        """(action, part_id, chapter_id). action is '' for an unknown path."""
        path = self.path.split("?", 1)[0]
        if path == API + "claim":
            return "claim", None, None
        if path == API + "ping":
            return "ping", None, None
        m = re.fullmatch(re.escape(API) + r"parts/([^/]+)/(epub|heartbeat|complete|fail)", path)
        if m:
            return m.group(2), m.group(1), None
        m = re.fullmatch(re.escape(API) + r"parts/([^/]+)/chapters/(\d+)", path)
        if m:
            return "chapter", m.group(1), m.group(2)
        return "", None, None

    # -- verbs -----------------------------------------------------------

    def do_GET(self) -> None:
        action, part_id, _ = self._route()
        if action != "epub" or part_id is None:
            return self._error(404, "not found")
        if not self._part_guard(part_id):
            return
        self._send(200, self.fake.part.epub, content_type="application/epub+zip")

    def do_POST(self) -> None:
        if self.path == "/_test/cancel":
            self.fake.cancel()
            return self._json(200, {"cancelled": True})
        action, part_id, _ = self._route()
        if action == "claim":
            return self._claim()
        if action == "ping":
            return self._ping()
        if action == "heartbeat" and part_id is not None:
            return self._heartbeat(part_id)
        if action == "complete" and part_id is not None:
            return self._complete(part_id)
        if action == "fail" and part_id is not None:
            return self._fail(part_id)
        return self._error(404, "not found")

    def do_PUT(self) -> None:
        action, part_id, chapter_id = self._route()
        if action != "chapter" or part_id is None or chapter_id is None:
            return self._error(404, "not found")
        self._upload(part_id, int(chapter_id))

    # -- calls -----------------------------------------------------------

    def _claim(self) -> None:
        if not self._auth_ok():
            return
        body = self._json_body()
        if body is None:
            return
        worker = body.get("worker_id")
        languages = body.get("languages", ["en"])
        if (
            not isinstance(worker, str)
            or not worker
            or not isinstance(languages, list)
            or not all(isinstance(code, str) for code in languages)
            or not isinstance(body.get("version"), str)
        ):
            return self._error(400, "claim needs worker_id, version and languages (list of strings)")
        wanted = {code.lower() for code in languages}
        fake = self.fake
        with fake.lock:
            offered = not fake.claimed and fake.part.language.lower() in wanted
            if offered:
                fake.claimed = True
                fake.owner = worker
        if not offered:
            return self._send(204, b"", headers={"Retry-After": "1"})
        fake.log(f"claimed by {worker}: part {fake.part.part_id}, {len(fake.part.chapters)} chapters")
        self._json(200, fake.part.claim_json())

    def _ping(self) -> None:
        if not self._auth_ok():
            return
        body = self._json_body()
        if body is None:
            return
        if not isinstance(body.get("available"), bool) or not isinstance(body.get("message"), str):
            return self._error(400, "available must be a boolean and message a string")
        self.fake.pings.append(body)
        self.fake.log(f"ping: available={body['available']} message={body['message']!r}")
        self._json(200, {"ok": True})

    def _heartbeat(self, part_id: str) -> None:
        if not self._part_guard(part_id):
            return
        body = self._json_body()
        if body is None:
            return
        if not _is_number(body.get("progress")) or not isinstance(body.get("stage"), str) or not isinstance(body.get("message"), str):
            return self._error(400, "progress must be a number; stage and message strings")
        self.fake.heartbeats.append(body)
        self.fake.log(f"heartbeat: {body['stage']} {body['progress']:.3f} {body['message']}")
        self._json(200, {"lease_until": "2026-11-02T03:30:00Z"})

    def _upload(self, part_id: str, chapter_id: int) -> None:
        if not self._part_guard(part_id):
            return
        if self.headers.get("Transfer-Encoding"):
            return self._error(400, "chunked bodies are not accepted; send Content-Length")
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            return self._error(400, "Content-Length is required")
        length = int(length_header)
        if length > MAX_UPLOAD_BYTES:
            return self._error(413, "chapter file is over 64 MB")
        if self.headers.get("Content-Type") != "audio/ogg":
            return self._error(400, "Content-Type must be audio/ogg")
        data = self.rfile.read(length)
        sha = hashlib.sha256(data).hexdigest()
        if self.headers.get("X-Content-SHA256") != sha:
            return self._error(400, "X-Content-SHA256 does not match the body")
        if chapter_id not in {c.chapter_id for c in self.fake.part.chapters}:
            return self._error(404, "no such chapter in this part")
        with self.fake.lock:
            previous = self.fake.uploads.get(chapter_id)
        if previous and previous[0] == sha:
            return self._json(200, {"chapter_id": chapter_id, "sha256": sha, "duplicate": True})

        fd, tmp = tempfile.mkstemp(suffix=".ogg")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            failures = probe_failures(tmp)
        finally:
            os.remove(tmp)
        if failures:
            self.fake.log(f"upload chapter {chapter_id} rejected: {'; '.join(failures)}")
            return self._send(400, ("; ".join(failures)).encode("utf-8"), content_type="text/plain")
        with self.fake.lock:
            self.fake.uploads[chapter_id] = (sha, data)
        if self.fake.out_dir:
            os.makedirs(self.fake.out_dir, exist_ok=True)
            with open(os.path.join(self.fake.out_dir, f"{chapter_id}.ogg"), "wb") as fh:
                fh.write(data)
        self.fake.log(f"uploaded chapter {chapter_id}: {len(data)} bytes sha={sha[:12]}")
        self._json(201, {"chapter_id": chapter_id, "sha256": sha})

    def _complete(self, part_id: str) -> None:
        if not self._part_guard(part_id):
            return
        body = self._json_body()
        if body is None:
            return
        if not isinstance(body.get("cast"), dict) or not isinstance(body.get("qa"), dict):
            return self._error(400, "cast and qa must be objects")
        if not isinstance(body.get("engine"), str) or not isinstance(body.get("engine_version"), str):
            return self._error(400, "engine and engine_version must be strings")
        for code, entry in body["cast"].items():
            if not isinstance(entry, dict):
                return self._error(400, f"cast entry {code} must be an object")
            if "description" in entry and not isinstance(entry["description"], str):
                return self._error(400, f"cast entry {code} description must be a string")
        if not isinstance(body["qa"].get("passed"), bool):
            return self._error(400, "qa.passed must be a boolean")
        expected = [c.chapter_id for c in self.fake.part.chapters]
        missing = [cid for cid in expected if cid not in self.fake.uploads]
        if missing:
            self.fake.log(f"complete rejected, missing chapters {missing}")
            return self._json(400, {"error": "missing_chapters", "missing": missing})
        with self.fake.lock:
            self.fake.completed = body
        self.fake.log(f"complete: qa passed={body['qa']['passed']}, {len(body['cast'])} cast entries")
        if self.fake.out_dir:
            os.makedirs(self.fake.out_dir, exist_ok=True)
            with open(os.path.join(self.fake.out_dir, "complete.json"), "w", encoding="utf-8") as fh:
                json.dump(body, fh, indent=2, sort_keys=True)
        self._json(200, {"ok": True})

    def _fail(self, part_id: str) -> None:
        if not self._part_guard(part_id):
            return
        body = self._json_body()
        if body is None:
            return
        if not isinstance(body.get("error"), str) or not isinstance(body.get("retryable"), bool):
            return self._error(400, "error must be a string and retryable a boolean")
        self.fake.failures.append(body)
        self.fake.log(f"fail: retryable={body['retryable']} {body['error'][:200]}")
        self._json(200, {"ok": True})


class FakeProdServer:
    """Runs the fake on a background thread. Use port=0 for an ephemeral port."""

    def __init__(
        self,
        part: FakePart,
        token: str,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        out_dir: str | None = None,
        log=None,
    ) -> None:
        self.state = FakeState(part, token, out_dir=out_dir, log=log or (lambda msg: None))
        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self.httpd.fake = self.state  # type: ignore[attr-defined]
        self.base_url = f"http://{host}:{self.httpd.server_address[1]}"
        self.api_base = self.base_url + API
        self._thread: threading.Thread | None = None

    def start(self) -> "FakeProdServer":
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chapters-dir", help="lncrawler novel source folder (with json/); synthetic chapters if omitted")
    ap.add_argument("--count", type=int, default=3, help="chapters in the part")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--token", default="t")
    ap.add_argument("--language", default="en", help="the part's series language")
    ap.add_argument("--out", default="fake_prod_out", help="uploaded oggs and complete.json go here")
    args = ap.parse_args(argv)

    def log(msg: str) -> None:
        print(msg, flush=True)

    part = build_part(language=args.language, count=args.count, chapters_dir=args.chapters_dir)
    server = FakeProdServer(part, args.token, host=args.host, port=args.port, out_dir=args.out, log=log)
    log(f"part {part.part_id} ({len(part.chapters)} chapters, language {part.language}) at {server.api_base}")
    try:
        server.httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
