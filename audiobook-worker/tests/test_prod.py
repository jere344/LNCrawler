import hashlib
import subprocess

import pytest
import requests

from fake_prod import FakeProdServer, build_part
from worker.prod import CompleteRejected, PartGone, ProdClient, ProdUnavailable, UploadRejected, UploadTooLarge

TOKEN = "tok"
WORKER = "worker-a"
CAST = {"Narrator": {"engine": "qwen", "voice": "v", "model": "qwen3-tts-1.7b", "role": "narrator"}}
QA = {"passed": True, "checks": {}, "notes": []}


def make_ogg(path: str, seconds: int = 20) -> str:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"aevalsrc=0.2*sin(2*PI*220*t):s=48000:d={seconds}",
            "-ac", "1", "-c:a", "libopus", "-b:a", "24k", path,
        ],
        check=True,
    )
    return path


@pytest.fixture
def server():
    part = build_part(language="en", count=2)
    srv = FakeProdServer(part, TOKEN).start()
    yield srv
    srv.stop()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client(server, sleeps):
    return ProdClient(
        server.api_base,
        TOKEN,
        WORKER,
        ["en", "fr"],
        backoffs=(0, 0, 0),
        sleep=sleeps.append,
    )


def test_claim_returns_part_then_204_with_retry_after(client, server):
    claim, retry = client.claim()
    assert claim is not None
    assert claim.part_id == server.state.part.part_id
    assert claim.series["language"] == "en"
    assert len(claim.chapters) == 2
    assert retry is None

    again, retry = client.claim()
    assert again is None
    assert retry == 1.0


def test_claim_skips_languages_the_worker_does_not_run(server, sleeps):
    client = ProdClient(server.api_base, TOKEN, WORKER, ["fr"], backoffs=(0, 0, 0), sleep=sleeps.append)
    claim, retry = client.claim()
    assert claim is None
    assert retry == 1.0


def test_epub_download_writes_the_file(client, server, tmp_path):
    client.claim()
    dest = str(tmp_path / "part.epub")
    client.epub(server.state.part.part_id, dest)
    with open(dest, "rb") as fh:
        assert fh.read(2) == b"PK"


def test_heartbeat_ok_then_part_gone_after_cancel(client, server):
    client.claim()
    part_id = server.state.part.part_id
    assert client.heartbeat(part_id, 0.25, "generation", "rendering") == "2026-11-02T03:30:00Z"
    assert server.state.heartbeats[-1]["progress"] == 0.25

    server.state.cancel()
    with pytest.raises(PartGone):
        client.heartbeat(part_id, 0.5, "generation", "rendering")


def test_upload_is_idempotent_for_the_same_bytes(client, server, tmp_path):
    client.claim()
    part_id = server.state.part.part_id
    chapter_id = server.state.part.chapters[0].chapter_id
    ogg = make_ogg(str(tmp_path / "c.ogg"))
    expected = hashlib.sha256(open(ogg, "rb").read()).hexdigest()

    assert client.upload_chapter(part_id, chapter_id, ogg) == expected
    assert client.upload_chapter(part_id, chapter_id, ogg) == expected
    assert server.state.uploads[chapter_id][0] == expected

    # Same hash again is 200, a new file is 201.
    with open(ogg, "rb") as fh:
        data = fh.read()
    resp = requests.put(
        server.api_base + f"parts/{part_id}/chapters/{chapter_id}",
        data=data,
        headers={
            "Authorization": f"Token {TOKEN}",
            "X-Worker-Contract": "1",
            "X-Worker-Id": WORKER,
            "Content-Type": "audio/ogg",
            "X-Content-SHA256": expected,
        },
    )
    assert resp.status_code == 200


def test_upload_of_a_bad_file_is_rejected(client, server, tmp_path):
    client.claim()
    part_id = server.state.part.part_id
    chapter_id = server.state.part.chapters[0].chapter_id
    bad = tmp_path / "bad.ogg"
    bad.write_bytes(b"this is not audio")
    with pytest.raises(UploadRejected):
        client.upload_chapter(part_id, chapter_id, str(bad))


def test_complete_reports_missing_chapters(client, server):
    client.claim()
    part_id = server.state.part.part_id
    expected = [c.chapter_id for c in server.state.part.chapters]
    with pytest.raises(CompleteRejected) as info:
        client.complete(part_id, CAST, QA, "castwright+qwen-hz+kokoro", "castwright@x")
    assert info.value.missing == expected


def test_complete_succeeds_once_every_chapter_is_uploaded(client, server, tmp_path):
    client.claim()
    part_id = server.state.part.part_id
    ogg = make_ogg(str(tmp_path / "c.ogg"))
    for chapter in server.state.part.chapters:
        client.upload_chapter(part_id, chapter.chapter_id, ogg)
    client.complete(part_id, CAST, QA, "castwright+qwen-hz+kokoro", "castwright@x")
    assert server.state.completed["cast"] == CAST
    assert server.state.completed["qa"]["passed"] is True


def test_fail_and_ping_send_real_booleans(client, server):
    client.claim()
    client.fail(server.state.part.part_id, "boom", retryable=True)
    assert server.state.failures[-1] == {"error": "boom", "retryable": True}

    client.ping(False, "stopped")
    assert server.state.pings[-1]["available"] is False
    assert server.state.pings[-1]["worker_id"] == WORKER


def test_unreachable_prod_raises_after_three_retries(sleeps):
    client = ProdClient(
        "http://127.0.0.1:9/api/audiobook-worker/",
        TOKEN,
        WORKER,
        ["en"],
        backoffs=(2, 8, 30),
        sleep=sleeps.append,
    )
    with pytest.raises(ProdUnavailable):
        client.claim()
    assert sleeps == [2, 8, 30]


def test_call_without_worker_id_header_is_400(server):
    resp = requests.post(
        server.api_base + f"parts/{server.state.part.part_id}/heartbeat",
        json={"progress": 0.1, "stage": "x", "message": "y"},
        headers={"Authorization": f"Token {TOKEN}", "X-Worker-Contract": "1"},
    )
    assert resp.status_code == 400


def test_upload_without_content_length_is_400(client, server, tmp_path):
    client.claim()
    part_id = server.state.part.part_id
    chapter_id = server.state.part.chapters[0].chapter_id
    resp = requests.put(
        server.api_base + f"parts/{part_id}/chapters/{chapter_id}",
        data=iter([b"abc"]),  # a generator is sent chunked, with no Content-Length
        headers={
            "Authorization": f"Token {TOKEN}",
            "X-Worker-Contract": "1",
            "X-Worker-Id": WORKER,
            "Content-Type": "audio/ogg",
            "X-Content-SHA256": hashlib.sha256(b"abc").hexdigest(),
        },
    )
    assert resp.status_code == 400


class StubResponse:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text
        self.headers = {}

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body

    def close(self):
        pass


class StubSession:
    """Returns or raises the queued items, one per request."""

    def __init__(self, queue):
        self.headers = {}
        self.queue = list(queue)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_any_requests_error_is_retried_then_unavailable():
    sleeps = []
    session = StubSession([requests.exceptions.ChunkedEncodingError("cut") for _ in range(4)])
    client = ProdClient("http://x/", TOKEN, WORKER, ["en"], backoffs=(2, 8, 30), sleep=sleeps.append, session=session)
    with pytest.raises(ProdUnavailable):
        client.ping(True, "idle")
    assert session.calls == 4
    assert sleeps == [2, 8, 30]


def test_non_json_claim_body_is_unavailable_not_a_crash():
    session = StubSession([StubResponse(200, body=None)])
    client = ProdClient("http://x/", TOKEN, WORKER, ["en"], backoffs=(0, 0, 0), sleep=lambda s: None, session=session)
    with pytest.raises(ProdUnavailable):
        client.claim()


def test_oversize_upload_is_refused_before_sending(tmp_path):
    big = tmp_path / "big.ogg"
    with open(big, "wb") as fh:
        fh.truncate(64 * 1024 * 1024 + 1)
    session = StubSession([])
    client = ProdClient("http://x/", TOKEN, WORKER, ["en"], backoffs=(0, 0, 0), sleep=lambda s: None, session=session)
    with pytest.raises(UploadTooLarge):
        client.upload_chapter("part", 1, str(big))
    assert session.calls == 0


class BodyCapturingSession(StubSession):
    def __init__(self, queue):
        super().__init__(queue)
        self.bodies = []

    def request(self, method, url, **kwargs):
        self.bodies.append(kwargs.get("json"))
        return super().request(method, url, **kwargs)


def test_ping_and_claim_send_languages_not_engine_profiles():
    session = BodyCapturingSession([StubResponse(200, body={"ok": True}), StubResponse(204)])
    client = ProdClient("http://x/", TOKEN, WORKER, ["en", "fr"], backoffs=(0, 0, 0), sleep=lambda s: None, session=session)
    client.ping(True, "idle")
    client.claim()
    for body in session.bodies:
        assert body["languages"] == ["en", "fr"]
        assert "engine_profiles" not in body
        assert "engine_profile" not in body


def test_complete_rejects_a_non_string_description(server):
    client = ProdClient(server.api_base, TOKEN, WORKER, ["en"], backoffs=(0, 0, 0), sleep=lambda s: None)
    client.claim()
    part_id = server.state.part.part_id
    bad_cast = {"Mara": {"engine": "qwen", "voice": "v", "role": "main", "description": 5}}
    with pytest.raises(CompleteRejected):
        client.complete(part_id, bad_cast, QA, "castwright+qwen-hz+kokoro", "castwright@x")
    assert server.state.completed is None


def test_complete_409_after_a_lost_connection_is_the_finished_part_not_a_cancel():
    session = StubSession([requests.exceptions.ConnectionError("cut"), StubResponse(409)])
    client = ProdClient("http://x/", TOKEN, WORKER, ["en"], backoffs=(0, 0, 0), sleep=lambda s: None, session=session)
    client.complete("part-1", CAST, QA, "castwright+kokoro", "castwright@x")  # no PartGone
    assert session.calls == 2


def test_complete_409_on_the_first_attempt_is_a_cancel():
    session = StubSession([StubResponse(409)])
    client = ProdClient("http://x/", TOKEN, WORKER, ["en"], backoffs=(0, 0, 0), sleep=lambda s: None, session=session)
    with pytest.raises(PartGone):
        client.complete("part-1", CAST, QA, "castwright+kokoro", "castwright@x")
    assert session.calls == 1
