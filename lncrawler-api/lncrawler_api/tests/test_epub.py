"""EPUB builds run as background jobs; the download endpoints only serve or queue."""

import os
import zipfile

from django.urls import reverse

from ..models import ExternalSource, Job, Novel
from ..services.epub_service import (
    cached_epub,
    enqueue_epub_job,
    epub_job_key,
    parse_epub_job_key,
    run_epub_job,
)
from .helpers import MergeTestCase


class EpubJobTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Book", slug="book", novel_path="book")
        self.source = self.make_source(
            self.novel,
            ExternalSource.objects.create(source_name="site"),
            "Book",
            "http://site/book",
            "book",
            "site",
            chapters=2,
        )
        self.source.chapters.update(has_content=True)

    def _url(self, name):
        return reverse(name, args=[self.novel.slug, self.source.source_slug])

    def test_job_key_round_trip(self):
        self.assertEqual(parse_epub_job_key(epub_job_key(7)), (7, None))
        self.assertEqual(parse_epub_job_key(epub_job_key(7, 3)), (7, 3))
        with self.assertRaises(ValueError):
            parse_epub_job_key("harvest:x")

    def test_enqueue_reuses_active_job(self):
        first = enqueue_epub_job(self.source)
        self.assertEqual(enqueue_epub_job(self.source).id, first.id)
        # A different volume is a different build.
        self.assertNotEqual(enqueue_epub_job(self.source, 1).id, first.id)

        first.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
        self.assertNotEqual(enqueue_epub_job(self.source).id, first.id)

    def test_prepare_queues_then_reports_ready(self):
        response = self.client.post(self._url("prepare_source_epub"))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "pending")
        job_id = response.json()["job"]["id"]

        run_epub_job(job_id, epub_job_key(self.source.id))

        job = Job.objects.get(id=job_id)
        self.assertEqual(job.status, Job.STATUS_DOWNLOAD_COMPLETED)
        self.assertEqual(job.progress, 2)
        self.assertEqual(job.total_items, 2)
        self.assertTrue(zipfile.is_zipfile(job.output_path))

        response = self.client.post(self._url("prepare_source_epub"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})

    def test_download_queues_when_not_cached_and_serves_when_fresh(self):
        response = self.client.get(self._url("download_source_epub"))
        self.assertEqual(response.status_code, 202)
        job = Job.objects.get(id=response.json()["job"]["id"])
        self.assertEqual(job.job_type, Job.JOB_TYPE_EPUB)

        run_epub_job(job.id, job.query)
        self.assertIsNotNone(cached_epub(self.source))

        response = self.client.get(self._url("download_source_epub"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/epub+zip")

    def test_no_chapters_is_404_and_job_failure_is_recorded(self):
        self.source.chapters.update(has_content=False)
        response = self.client.post(self._url("prepare_source_epub"))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Job.objects.filter(job_type=Job.JOB_TYPE_EPUB).exists())

        job = Job.objects.create(
            job_type=Job.JOB_TYPE_EPUB, query=epub_job_key(self.source.id)
        )
        run_epub_job(job.id, job.query)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertIn("No downloadable chapters", job.error_message)

    def test_epub_jobs_hidden_from_job_list(self):
        enqueue_epub_job(self.source)
        response = self.client.get(reverse("list_jobs"))
        self.assertEqual(response.json()["jobs"], [])

    def test_prune_removes_only_expired_files(self):
        from django.core.management import call_command

        path, _ = enqueue_and_build(self.source)
        call_command("prune_epub_cache", stdout=open(os.devnull, "w"))
        self.assertTrue(os.path.exists(path))

        old = os.path.getmtime(path) - 3 * 24 * 3600
        os.utime(path, (old, old))
        call_command("prune_epub_cache", stdout=open(os.devnull, "w"))
        self.assertFalse(os.path.exists(path))


def enqueue_and_build(source):
    job = enqueue_epub_job(source)
    run_epub_job(job.id, job.query)
    job.refresh_from_db()
    return job.output_path, job.output_files[0]
