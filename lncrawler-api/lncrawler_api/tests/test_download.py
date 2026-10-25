"""Tests for download/import failure handling."""

import tempfile
import time

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


class DownloadExpectedErrorTests(TransactionTestCase):
    """A source-level LNException (novel unavailable: removed from the site, no
    downloads) must fail the job but stay below ERROR so it does not open an
    auto-issue; unexpected errors still report."""

    def _run_with(self, exc):
        from unittest import mock

        from ..services import downloader_service as ds

        ds._load_app()  # put the crawler package on sys.path for isinstance
        job = Job.objects.create(
            status=Job.STATUS_CREATED, job_type=Job.JOB_TYPE_DOWNLOAD
        )

        class FakeApp:
            crawler = object()

            def prepare_search(self):
                pass

            def get_novel_info(self):
                raise exc

        # _setup_django runs django.setup(), which re-applies LOGGING and would
        # strip assertLogs' handler mid-run. It only refreshes the DB
        # connection here, which the test does not need.
        with mock.patch.object(ds, "_load_app", return_value=FakeApp), mock.patch.object(
            ds.DownloaderService, "_setup_django", return_value=None
        ), mock.patch.object(
            ds, "_poll_download_progress", return_value=None
        ), mock.patch.object(
            ds.DownloaderService, "_inject_existing_chapters", return_value=None
        ):
            ds.DownloaderService._run_download_process(
                job.id, "http://example.invalid/novel"
            )
        return job

    def test_source_error_fails_job_without_error_log(self):
        from ..services.downloader_service import _load_app

        _load_app()
        from lncrawl.core.exeptions import LNException

        with self.assertLogs("lncrawler_api", level="WARNING") as cm:
            job = self._run_with(
                LNException("No EPUB downloads found on this novel page")
            )

        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertIn("No EPUB downloads found", job.error_message)
        self.assertFalse(any(r.levelname == "ERROR" for r in cm.records))

    def test_transport_error_fails_job_without_error_log(self):
        from urllib.error import URLError

        with self.assertLogs("lncrawler_api", level="WARNING") as cm:
            job = self._run_with(URLError("server error"))

        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertFalse(any(r.levelname == "ERROR" for r in cm.records))

    def test_unexpected_error_logs_error(self):
        with self.assertLogs("lncrawler_api", level="ERROR") as cm:
            self._run_with(RuntimeError("boom"))

        self.assertTrue(any(r.levelname == "ERROR" for r in cm.records))


class DownloadCancelTests(TransactionTestCase):
    """A download cancelled while running must not be imported."""

    def test_cancelled_download_is_not_imported(self):
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

            def cancel(self):
                pass

            def start_download(self):
                # The user cancels while chapters are being fetched.
                Job.objects.filter(pk=job.id).update(status=Job.STATUS_FAILED)

        with tempfile.TemporaryDirectory() as tmp, override_settings(
            LNCRAWL_OUTPUT_PATH=tmp
        ), mock.patch.object(ds, "_load_app", return_value=FakeApp), mock.patch.object(
            ds, "_poll_download_progress", return_value=None
        ), mock.patch.object(
            ds.DownloaderService, "_inject_existing_chapters", return_value=None
        ), mock.patch.object(
            ds.DownloaderService, "_import_novel_to_database"
        ) as import_mock:
            ds.DownloaderService._run_download_process(
                job.id, "http://example.invalid/novel"
            )

        import_mock.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)

    def test_monitor_cancels_the_app_when_job_is_cancelled(self):
        from unittest import mock

        from ..services import downloader_service as ds

        job = Job.objects.create(
            status=Job.STATUS_CREATED, job_type=Job.JOB_TYPE_DOWNLOAD
        )
        cancel_calls = []

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

            def cancel(self):
                cancel_calls.append(True)

            def start_download(self):
                # The user cancels; the app itself does not notice, the monitor must.
                Job.objects.filter(pk=job.id).update(status=Job.STATUS_FAILED)
                deadline = time.monotonic() + 10
                while not cancel_calls and time.monotonic() < deadline:
                    time.sleep(0.1)

        with tempfile.TemporaryDirectory() as tmp, override_settings(
            LNCRAWL_OUTPUT_PATH=tmp
        ), mock.patch.object(ds, "_load_app", return_value=FakeApp), mock.patch.object(
            ds, "_poll_download_progress", return_value=None
        ), mock.patch.object(
            ds.DownloaderService, "_inject_existing_chapters", return_value=None
        ), mock.patch.object(
            ds.DownloaderService, "_import_novel_to_database"
        ) as import_mock:
            ds.DownloaderService._run_download_process(
                job.id, "http://example.invalid/novel"
            )

        self.assertTrue(cancel_calls)
        import_mock.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
