"""Tests for download/import failure handling."""

import tempfile

from django.test import TestCase, TransactionTestCase, override_settings

from ..models import Job


class ChapterFailureReportingTests(TestCase):
    """Unexpected chapter-download errors are escalated to ERROR to reach the
    issue reporter; expected transient network/IO failures stay at WARNING."""

    def _run(self, exc):
        from lncrawler_api.services.downloader_service import _load_app

        _load_app()
        from lncrawl.core.crawler import Crawler

        class Boom(Crawler):
            base_url = "http://example.invalid"
            source_name = "example.invalid"

            def download_chapter_body(self, chapter):
                raise exc

        class FakeChapter:
            body = ""
            images = {}
            success = False

        list(Boom().download_chapters([FakeChapter()]))

    def test_unicode_error_logs_error_with_fingerprint(self):
        with self.assertLogs("lncrawl.core.crawler", level="ERROR") as cm:
            self._run(UnicodeDecodeError("ascii", b"\xe7", 0, 1, "boom"))
        record = cm.records[-1]
        self.assertEqual(record.levelname, "ERROR")
        self.assertTrue(getattr(record, "github_fingerprint", None))

    def test_unexpected_error_logs_error(self):
        with self.assertLogs("lncrawl.core.crawler", level="ERROR") as cm:
            self._run(RuntimeError("boom"))
        self.assertEqual(cm.records[-1].levelname, "ERROR")

    def test_transient_error_stays_warning(self):
        from urllib.error import URLError

        with self.assertLogs("lncrawl.core.crawler", level="WARNING") as cm:
            self._run(URLError("boom"))
        self.assertEqual([r.levelname for r in cm.records], ["WARNING"])


class DownloadImportFailureTests(TransactionTestCase):
    """A download whose meta.json cannot be imported must fail the job."""

    def test_failed_import_fails_job(self):
        from unittest import mock

        from ..services import downloader_service as ds

        job = Job.objects.create(
            status=Job.STATUS_CREATED, job_type=Job.JOB_TYPE_DOWNLOAD
        )

        class FakeCrawler:
            novel_title = "Untitled"
            novel_url = "http://example.invalid/novel"
            source_name = "example.invalid"
            volumes = []
            chapters = []

        class FakeApp:
            def __init__(self):
                self.crawler = FakeCrawler()
                self.chapters = []
                self.output_path = ""

            def prepare_search(self):
                pass

            def get_novel_info(self):
                pass

            def start_download(self):
                pass

        with tempfile.TemporaryDirectory() as tmp, override_settings(
            LNCRAWL_OUTPUT_PATH=tmp
        ), mock.patch.object(ds, "_load_app", return_value=FakeApp), mock.patch.object(
            ds, "_poll_download_progress", return_value=None
        ), mock.patch.object(
            ds.DownloaderService, "_inject_existing_chapters", return_value=None
        ), mock.patch.object(
            ds.DownloaderService,
            "_import_novel_to_database",
            return_value=(False, "The meta.json file does not contain a novel title"),
        ):
            ds.DownloaderService._run_download_process(
                job.id, "http://example.invalid/novel"
            )

        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertIn("import failed", job.error_message)
