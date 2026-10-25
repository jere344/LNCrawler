"""Tests for reading search jobs while they run and downloading from them."""

import threading
import time
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase

from ..models import Job
from ..services import DownloaderService

PARTIAL_RESULTS = {
    "status": "success",
    "results": [
        {
            "index": 0,
            "title": "Solo Leveling",
            "sources": [
                {"index": 0, "url": "http://a.invalid/solo"},
                {"index": 1, "url": "http://b.invalid/solo"},
            ],
        },
    ],
    "partial": True,
}


class SearchSnapshotTests(TestCase):
    def setUp(self):
        self.job = Job.objects.create(
            status=Job.STATUS_SEARCHING,
            job_type=Job.JOB_TYPE_SEARCH,
            query="solo leveling",
            search_results=PARTIAL_RESULTS,
        )

    def test_results_are_readable_while_searching(self):
        data = DownloaderService.get_search_results(self.job.id)

        self.assertEqual(data["status"], "success")
        self.assertTrue(data["partial"])
        self.assertEqual(data["results"], PARTIAL_RESULTS["results"])

    def test_no_snapshot_yet_returns_empty_list(self):
        self.job.search_results = None
        self.job.save(update_fields=["search_results"])

        data = DownloaderService.get_search_results(self.job.id)

        self.assertEqual(data, {"status": "success", "results": [], "partial": True})

    def test_status_counts_source_entries(self):
        self.assertEqual(
            DownloaderService.get_search_status(self.job.id)["result_count"], 2
        )

    def test_status_count_is_zero_without_results(self):
        self.job.search_results = {"status": "success", "direct_novel": True}
        self.job.save(update_fields=["search_results"])

        self.assertEqual(
            DownloaderService.get_search_status(self.job.id)["result_count"], 0
        )


class StartDownloadFromSearchTests(TestCase):
    def setUp(self):
        self.search_job = Job.objects.create(
            status=Job.STATUS_SEARCHING,
            job_type=Job.JOB_TYPE_SEARCH,
            query="solo leveling",
            search_results=PARTIAL_RESULTS,
        )

    def test_url_while_searching_starts_a_new_download_job(self):
        data = DownloaderService.start_download(
            self.search_job.id, novel_url="http://a.invalid/solo"
        )

        self.assertEqual(data["status"], "success")
        self.assertNotEqual(data["job_id"], str(self.search_job.id))
        download = Job.objects.get(id=data["job_id"])
        self.assertEqual(download.job_type, Job.JOB_TYPE_DOWNLOAD)
        self.assertEqual(download.status, Job.STATUS_CREATED)
        self.assertEqual(download.query, "solo leveling")
        self.assertEqual(download.target_url, "http://a.invalid/solo")

        self.search_job.refresh_from_db()
        self.assertEqual(self.search_job.status, Job.STATUS_SEARCHING)
        self.assertEqual(self.search_job.search_results, PARTIAL_RESULTS)

    def test_url_not_in_results_is_rejected(self):
        data = DownloaderService.start_download(
            self.search_job.id, novel_url="http://c.invalid/solo"
        )

        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "Selected novel is not in the search results")
        self.assertEqual(Job.objects.count(), 1)

    def test_indices_while_searching_are_rejected(self):
        data = DownloaderService.start_download(self.search_job.id)

        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "Cannot start download: search not completed")

    def test_completed_search_with_url_reuses_the_job(self):
        self.search_job.status = Job.STATUS_SEARCH_COMPLETED
        self.search_job.save(update_fields=["status"])

        data = DownloaderService.start_download(
            self.search_job.id, novel_url="http://b.invalid/solo"
        )

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["job_id"], str(self.search_job.id))
        self.search_job.refresh_from_db()
        self.assertEqual(self.search_job.target_url, "http://b.invalid/solo")
        self.assertEqual(self.search_job.job_type, Job.JOB_TYPE_DOWNLOAD)


FAKE_SOURCES = [
    {"url": "http://a.invalid/solo", "info": "Webnovel", "title": "Solo Leveling"},
    {"url": "http://b.invalid/solo", "info": "NovelUpdates", "title": "Solo Leveling"},
    {"url": "http://c.invalid/solo", "info": "Mirror", "title": "Solo Leveling"},
]


class FakeApp:
    """Stands in for the crawler App and finds one source per step."""

    def __init__(self):
        self.progress = 0
        self.crawler = None
        self.crawler_links = []
        self.search_results = []

    def prepare_search(self):
        self.crawler = None
        self.crawler_links = [1, 2, 3]

    def search_novel(self):
        for step in range(1, len(FAKE_SOURCES) + 1):
            self.progress = step
            self.search_results = [{"title": "Solo Leveling", "novels": FAKE_SOURCES[:step]}]
            if step < len(FAKE_SOURCES):
                # Longer than the 1s monitor interval, so a snapshot is written in between.
                time.sleep(1.3)

    def cancel(self):
        pass

    def destroy(self):
        pass


class SearchMonitorTests(TransactionTestCase):
    """Runs the whole search, so the monitor thread must see committed rows."""

    def setUp(self):
        self.job = Job.objects.create(
            status=Job.STATUS_SEARCHING,
            job_type=Job.JOB_TYPE_SEARCH,
            query="solo leveling",
        )

    def test_monitor_writes_partial_snapshots_during_search(self):
        original_update = Job.update_search_results
        written = []

        def record(job, results):
            written.append(results)
            return original_update(job, results)

        with patch("lncrawler_api.services.downloader_service._load_app", return_value=FakeApp):
            with patch.object(DownloaderService, "_setup_django"):
                with patch.object(Job, "update_search_results", record):
                    DownloaderService._run_search_process(self.job.id, "solo leveling")

        self.job.refresh_from_db()
        partial = [results for results in written if results.get("partial")]
        self.assertTrue(any(results["results"] for results in partial))

        self.assertEqual(self.job.status, Job.STATUS_SEARCH_COMPLETED)
        self.assertNotIn("partial", written[-1])
        self.assertNotIn("partial", self.job.search_results)
        self.assertEqual(len(self.job.search_results["results"][0]["sources"]), len(FAKE_SOURCES))


class SlowSearchApp:
    """Finds one source per second until cancelled."""

    def __init__(self):
        self.progress = 0
        self.crawler = None
        self.crawler_links = []
        self.search_results = []
        self.cancel_calls = 0
        self._cancelled = threading.Event()

    def prepare_search(self):
        self.crawler_links = [1, 2, 3]

    def search_novel(self):
        for step in range(1, len(FAKE_SOURCES) + 1):
            if self._cancelled.wait(1.0):
                return
            self.progress = step
            self.search_results = [{"title": "Solo Leveling", "novels": FAKE_SOURCES[:step]}]

    def cancel(self):
        self.cancel_calls += 1
        self._cancelled.set()

    def destroy(self):
        pass


class SearchCancelTests(TransactionTestCase):
    """A search cancelled mid-run must stop the app and keep its FAILED status."""

    def test_cancel_stops_the_app_and_keeps_failed_status(self):
        job = Job.objects.create(
            status=Job.STATUS_CREATED,
            job_type=Job.JOB_TYPE_SEARCH,
            query="solo leveling",
        )
        app = SlowSearchApp()
        original_update = Job.update_search_results
        written = []

        def record(job, results):
            written.append(results)
            return original_update(job, results)

        with patch("lncrawler_api.services.downloader_service._load_app", return_value=lambda: app):
            with patch.object(DownloaderService, "_setup_django"):
                with patch.object(Job, "update_search_results", record):
                    worker = threading.Thread(
                        target=DownloaderService._run_search_process,
                        args=(job.id, "solo leveling"),
                    )
                    worker.start()
                    time.sleep(1.5)
                    Job.objects.filter(pk=job.id).update(status=Job.STATUS_FAILED)
                    worker.join(timeout=10)

        self.assertFalse(worker.is_alive())
        self.assertGreaterEqual(app.cancel_calls, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertTrue(all(results.get("partial") for results in written))
