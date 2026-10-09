"""Tests for the harvest service."""

from django.test import TestCase

from ..models import Job


class HarvestServiceTests(TestCase):
    def setUp(self):
        from ..models import HarvestCandidate, HarvestConfig
        from ..services import harvest_service

        self.harvest_service = harvest_service
        self.HarvestCandidate = HarvestCandidate
        self.config = HarvestConfig.get_solo()
        self.config.enabled = True
        self.config.max_concurrent = 2
        self.config.muted_sources = []
        self.config.save()

    def _candidate(self, source, url):
        return self.HarvestCandidate.objects.create(
            source_name=source, novel_url=url, title=url.rsplit("/", 1)[-1]
        )

    def test_enqueue_is_round_robin_one_per_source(self):
        self._candidate("srcA", "https://a.example/1")
        self._candidate("srcA", "https://a.example/2")
        self._candidate("srcB", "https://b.example/1")

        self.assertEqual(self.harvest_service.enqueue_ready(self.config), 2)

        queued = set(
            Job.objects.filter(query__startswith="harvest:").values_list("query", flat=True)
        )
        self.assertEqual(queued, {"harvest:srcA", "harvest:srcB"})
        # Only one candidate per source is promoted.
        self.assertEqual(
            self.HarvestCandidate.objects.filter(status="queued").count(), 2
        )

    def test_enqueue_rotates_across_sources_not_one_source_backlog(self):
        self.config.max_concurrent = 1
        self.config.save()

        # srcA has a backlog and was discovered first; srcB is discovered later.
        self._candidate("srcA", "https://a.example/1")
        self._candidate("srcA", "https://a.example/2")
        self._candidate("srcB", "https://b.example/1")

        # First turn: srcA (never harvested, oldest candidate).
        self.assertEqual(self.harvest_service.enqueue_ready(self.config), 1)
        first = Job.objects.get(query="harvest:srcA")
        first.status = Job.STATUS_DOWNLOAD_COMPLETED
        first.output_slug = "novel/srcA"
        first.save()
        self.harvest_service.reconcile()

        # srcA's backlog must NOT be picked again before srcB gets its first turn.
        self.assertEqual(self.harvest_service.enqueue_ready(self.config), 1)
        self.assertEqual(
            Job.objects.filter(query="harvest:srcB").count(),
            1,
        )

    def test_enqueue_respects_concurrency_and_disabled_flag(self):
        running = self._candidate("srcA", "https://a.example/run")
        self._candidate("srcB", "https://b.example/1")
        self._candidate("srcC", "https://c.example/1")
        job = Job.objects.create(
            status=Job.STATUS_DOWNLOADING,
            job_type=Job.JOB_TYPE_DOWNLOAD,
            query="harvest:srcA",
            target_url="https://a.example/run",
        )
        running.mark_queued(job.id)
        # One queued + max_concurrent=2 -> exactly one more slot.
        self.assertEqual(self.harvest_service.enqueue_ready(self.config), 1)

        self.config.enabled = False
        self.assertEqual(self.harvest_service.enqueue_ready(self.config), 0)

    def test_reconcile_marks_terminal_statuses(self):
        done = self._candidate("srcA", "https://a.example/1")
        failed = self._candidate("srcB", "https://b.example/1")
        done_job = Job.objects.create(
            status=Job.STATUS_DOWNLOAD_COMPLETED,
            job_type=Job.JOB_TYPE_DOWNLOAD,
            output_slug="novel/srcA",
        )
        failed_job = Job.objects.create(
            status=Job.STATUS_FAILED, job_type=Job.JOB_TYPE_DOWNLOAD
        )
        done.mark_queued(done_job.id)
        failed.mark_queued(failed_job.id)

        self.assertEqual(self.harvest_service.reconcile(), 2)
        done.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual(done.status, "done")
        self.assertEqual(failed.status, "failed")

    def test_reconcile_marks_failed_when_import_did_not_run(self):
        candidate = self._candidate("srcA", "https://a.example/1")
        job = Job.objects.create(
            status=Job.STATUS_DOWNLOAD_COMPLETED, job_type=Job.JOB_TYPE_DOWNLOAD
        )
        candidate.mark_queued(job.id)

        self.assertEqual(self.harvest_service.reconcile(), 1)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, "failed")
