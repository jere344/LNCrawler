"""Background harvest feeder: discover novels, queue downloads, track results.

The feeder is a long-running process (``manage.py run_harvest``) that owns a
singleton PostgreSQL advisory lock. Each loop it:

1. reconciles queued candidates with their Job's terminal status,
2. runs a browse scan in a *short-lived subprocess* (``manage.py harvest_browse``)
   when the pending catalogue runs low, so lncrawl's memory is released on exit,
3. enqueues at most one download Job per non-muted source, up to
   ``HarvestConfig.max_concurrent`` concurrent harvest jobs.

Everything is controlled from the admin via the ``HarvestConfig`` singleton
(start/stop, mute sources, concurrency); the process itself is always up.
"""

import logging
import os
import subprocess
import sys

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("lncrawler_api")

HARVEST_QUERY_PREFIX = "harvest:"


def harvest_query(source_name: str) -> str:
    return f"{HARVEST_QUERY_PREFIX}{source_name}"


def get_config():
    from ..models import HarvestConfig

    return HarvestConfig.get_solo()


def _active_source_names() -> set:
    """Sources whose candidate is currently queued (i.e. a job is in flight)."""
    from ..models import HarvestCandidate

    return set(
        HarvestCandidate.objects.filter(status=HarvestCandidate.STATUS_QUEUED)
        .values_list("source_name", flat=True)
    )


def reconcile() -> int:
    """Sync queued candidates with their Job result. Returns rows touched."""
    from ..models import HarvestCandidate, Job

    queued = list(
        HarvestCandidate.objects.filter(status=HarvestCandidate.STATUS_QUEUED)
        .exclude(job_id__isnull=True)
    )
    if not queued:
        return 0
    jobs = {
        str(job.id): job
        for job in Job.objects.filter(id__in=[c.job_id for c in queued])
    }
    touched = 0
    for candidate in queued:
        job = jobs.get(str(candidate.job_id))
        if job is None:
            # Job was pruned/removed; let it be retried.
            candidate.mark_pending()
        elif job.status == Job.STATUS_DOWNLOAD_COMPLETED:
            # The downloader sets download_completed even when the DB import
            # failed; output_slug is only written on a successful import, so an
            # empty slug means the novel never reached the library.
            if job.output_slug:
                candidate.mark_done()
            else:
                candidate.mark_failed()
        elif job.status == Job.STATUS_FAILED:
            candidate.mark_failed()
        else:
            continue  # still running
        touched += 1
    return touched


def pending_candidates(config=None):
    """Pending, non-muted candidates ordered oldest first."""
    from ..models import HarvestCandidate

    config = config or get_config()
    muted = list(config.muted_sources or [])
    return (
        HarvestCandidate.objects.filter(status=HarvestCandidate.STATUS_PENDING)
        .exclude(source_name__in=muted)
        .order_by("created_at")
    )


def enqueue_ready(config=None) -> int:
    """Queue one download Job per idle source, up to the concurrency budget."""
    from ..models import HarvestCandidate, Job

    config = config or get_config()
    if not config.enabled:
        return 0

    # A queued candidate == an in-flight harvest job (mark_queued is set right
    # after the Job is created, and reconcile() clears it on terminal status).
    running = HarvestCandidate.objects.filter(
        status=HarvestCandidate.STATUS_QUEUED
    ).count()
    capacity = max(0, config.max_concurrent - running)
    if capacity <= 0:
        return 0

    active_sources = _active_source_names()
    chosen_sources = set()
    enqueued = 0
    for candidate in pending_candidates(config).iterator():
        if enqueued >= capacity:
            break
        # One in-flight harvest job per source: skip sources already active or
        # already picked this pass.
        if candidate.source_name in active_sources or candidate.source_name in chosen_sources:
            continue
        chosen_sources.add(candidate.source_name)
        job = Job.objects.create(
            status=Job.STATUS_CREATED,
            job_type=Job.JOB_TYPE_DOWNLOAD,
            target_url=candidate.novel_url,
            query=harvest_query(candidate.source_name),
        )
        candidate.mark_queued(job.id)
        enqueued += 1
    return enqueued


def should_scan(config) -> bool:
    """True when the pending catalogue is low and the cooldown has elapsed."""
    if not config.enabled:
        return False
    low = pending_candidates(config).count() <= config.max_concurrent
    if not low:
        return False
    cooldown = int(os.environ.get("HARVEST_REFRESH_SECONDS", "3600"))
    if config.last_harvest_at is None:
        return True
    return (timezone.now() - config.last_harvest_at).total_seconds() >= cooldown


def run_scan_subprocess() -> int:
    """Run one browse scan in a short-lived subprocess (memory isolation)."""
    cmd = [sys.executable, "manage.py", "harvest_browse"]
    env = dict(os.environ)
    env.setdefault("SERVICE_NAME", "harvest")
    timeout = int(os.environ.get("HARVEST_SCAN_TIMEOUT", "1800"))
    logger.info("Starting harvest scan subprocess: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(settings.BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error("Harvest scan timed out after %ss", timeout)
        return -1
    if proc.stdout:
        logger.info("Harvest scan output:\n%s", proc.stdout.strip())
    if proc.returncode != 0:
        logger.error("Harvest scan failed (rc=%s): %s", proc.returncode, proc.stderr.strip())
    return proc.returncode


def acquire_feeder_lock() -> bool:
    """Try to become the single feeder. Uses a session-level advisory lock."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext('lncrawler_harvest_feeder'))")
        return bool(cur.fetchone()[0])


def release_feeder_lock():
    from django.db import connection

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext('lncrawler_harvest_feeder'))")
    except Exception:
        pass
