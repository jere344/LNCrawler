"""The crawler supervisor's SQL keeps folder guard state right: a job back in the queue holds no novel."""

from django.db import connection
from django.test import TestCase

from ..models import Job
from .helpers import bare_novel


def _supervisor():
    import crawler_supervisor  # the module is standalone: it imports no Django

    return crawler_supervisor


class SupervisorRequeueTests(TestCase):
    def setUp(self):
        self.novel = bare_novel("queued", "queued")

    def _job(self, status, retry_count=0):
        return Job.objects.create(
            job_type=Job.JOB_TYPE_DOWNLOAD, status=status, novel=self.novel,
            retry_count=retry_count,
        )

    def _run(self, sql, params):
        with connection.cursor() as cur:
            cur.execute(sql, params)

    def test_requeue_clears_the_novel_of_a_stale_job(self):
        job = self._job(Job.STATUS_DOWNLOADING)
        Job.objects.filter(pk=job.pk).update(updated_at="2000-01-01T00:00:00+00:00")
        self._run(_supervisor().REQUEUE_SQL, (60,))
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_CREATED)
        self.assertIsNone(job.novel_id)

    def test_crash_requeue_clears_the_novel(self):
        job = self._job(Job.STATUS_DOWNLOADING, retry_count=0)
        self._run(_supervisor().FAIL_JOB_SQL, (str(job.pk),))
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_CREATED)
        self.assertIsNone(job.novel_id)

    def test_crash_after_the_last_retry_keeps_the_novel_on_the_failed_job(self):
        job = self._job(Job.STATUS_DOWNLOADING, retry_count=_supervisor().MAX_RETRIES)
        self._run(_supervisor().FAIL_JOB_SQL, (str(job.pk),))
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertEqual(job.novel_id, self.novel.pk)
