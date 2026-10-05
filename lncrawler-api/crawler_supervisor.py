#!/usr/bin/env python
"""Lightweight crawler job supervisor (no Django imports).

Runs as the long-lived process of each crawler container. It stays tiny (~18MB)
because it never imports Django or lncrawl: it claims a queued job with a single
atomic PostgreSQL statement, then runs the job in a short-lived
``manage.py run_crawler_job`` subprocess and reaps it. All of a job's memory
(Django, lncrawl, Chromium) is released when that subprocess exits, so leaks
cannot accumulate here. Isolation is preserved at both the job (fresh process)
and container (separate cgroup) level.

Env: POSTGRES_* (connection), CRAWLER_CONCURRENCY (default 1),
CRAWLER_POLL (seconds, default 2), CRAWLER_STALE_MINUTES (default 10),
CRAWLER_REQUEUE_EVERY (seconds, default 300).

Self-check: ``python crawler_supervisor.py --self-check`` (needs the DB; rolls
back its transaction).
"""

import logging
import os
import signal
import subprocess
import sys
import time

import psycopg

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="[CRAWLER] %(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("crawler_supervisor")

TABLE = "lncrawler_api_job"

# Claim the oldest queued job atomically. FOR UPDATE SKIP LOCKED lets several
# supervisors claim concurrently without a lost-race retry loop.
CLAIM_SQL = f"""
WITH next AS (
    SELECT id FROM {TABLE}
    WHERE status = 'created'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE {TABLE} AS job
SET status = CASE WHEN job.job_type = 'download' THEN 'downloading' ELSE 'searching' END,
    updated_at = now()
FROM next
WHERE job.id = next.id
RETURNING job.id, job.job_type,
    CASE WHEN job.job_type = 'download'
         THEN COALESCE(job.target_url, '')
         ELSE COALESCE(job.query, '') END
"""

REQUEUE_SQL = f"""
UPDATE {TABLE} SET status = 'created', updated_at = now()
WHERE status IN ('searching', 'downloading')
  AND updated_at < now() - make_interval(secs => %s)
"""

# A job subprocess that exits non-zero (crash, OOM, import error) leaves the row
# in a running state; reset it to the queue immediately instead of waiting out
# the stale window. Guarded on the running status so a row another worker has
# since moved cannot be clobbered.
FAIL_JOB_SQL = f"""
UPDATE {TABLE} SET status = 'created', updated_at = now()
WHERE id = %s AND status IN ('searching', 'downloading')
"""


def connect(autocommit=True):
    return psycopg.connect(
        dbname=os.environ.get("POSTGRES_DB", "lncrawler"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        autocommit=autocommit,
    )


def claim(conn):
    """Return (job_id, job_type, payload) for the next queued job, or None."""
    with conn.cursor() as cur:
        cur.execute(CLAIM_SQL)
        return cur.fetchone()


def requeue_stale(conn, age_seconds):
    with conn.cursor() as cur:
        cur.execute(REQUEUE_SQL, (age_seconds,))
        return cur.rowcount


def release_failed_job(conn, job_id):
    with conn.cursor() as cur:
        cur.execute(FAIL_JOB_SQL, (str(job_id),))
        return cur.rowcount


class Supervisor:
    def __init__(self, concurrency=1, poll=2.0, stale_minutes=10.0, requeue_every=300.0):
        self.concurrency = max(1, concurrency)
        self.poll = poll
        self.stale_seconds = stale_minutes * 60
        self.requeue_every = requeue_every
        self.running = True
        self.conn = None
        self.children = {}
        self.last_requeue = 0.0

    def _ensure_conn(self):
        if self.conn is not None and not self.conn.closed:
            return self.conn
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        try:
            self.conn = connect()
        except Exception:
            log.exception("DB connection failed; retrying in %ss", self.poll)
            self.conn = None
            time.sleep(self.poll)
        return self.conn

    def _reap(self):
        for pid in [p for p, (proc, _job) in self.children.items() if proc.poll() is not None]:
            proc, job_id = self.children.pop(pid)
            if proc.returncode != 0:
                log.warning(
                    "Job %s process %s exited with code %s; releasing for retry",
                    job_id, pid, proc.returncode,
                )
                conn = self._ensure_conn()
                if conn is not None:
                    try:
                        release_failed_job(conn, job_id)
                    except Exception:
                        log.exception("Failed to release job %s after non-zero exit", job_id)
            else:
                log.info("Job %s process %s exited cleanly", job_id, pid)

    def _spawn(self, job_id, job_type, payload):
        env = dict(
            os.environ,
            SERVICE_NAME="crawler",
            DJANGO_SETTINGS_MODULE="api_project.settings_crawler",
        )
        cmd = [
            sys.executable,
            "manage.py",
            "run_crawler_job",
            str(job_id),
            job_type,
            payload,
        ]
        log.info("Starting executor for %s job %s", job_type, job_id)
        try:
            proc = subprocess.Popen(cmd, env=env, start_new_session=True)
        except Exception:
            log.exception("Failed to spawn executor for job %s; releasing", job_id)
            conn = self._ensure_conn()
            if conn is not None:
                try:
                    release_failed_job(conn, job_id)
                except Exception:
                    log.exception("Failed to release job %s after spawn error", job_id)
            return
        self.children[proc.pid] = (proc, job_id)
        # Best-effort: prefer OOM-killing a runaway job over this supervisor.
        try:
            with open(f"/proc/{proc.pid}/oom_score_adj", "w") as handle:
                handle.write("500")
        except OSError:
            pass

    def _on_signal(self, signum, frame):
        log.info("Received signal %s; draining %s job(s)", signum, len(self.children))
        self.running = False

    def run(self):
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        log.info(
            "Crawler supervisor started (concurrency=%s, poll=%ss, stale=%smin)",
            self.concurrency,
            self.poll,
            self.stale_seconds // 60,
        )

        conn = self._ensure_conn()
        if conn is not None:
            try:
                n = requeue_stale(conn, self.stale_seconds)
                if n:
                    log.warning("Requeued %s stale job(s) at startup", n)
            except Exception:
                log.exception("Startup requeue failed")
            self.last_requeue = time.monotonic()

        while self.running:
            self._reap()
            conn = self._ensure_conn()
            if conn is None:
                continue

            if self.requeue_every > 0 and (time.monotonic() - self.last_requeue) >= self.requeue_every:
                try:
                    n = requeue_stale(conn, self.stale_seconds)
                    if n:
                        log.warning("Requeued %s stale job(s)", n)
                    self.last_requeue = time.monotonic()
                except Exception:
                    log.exception("Requeue failed; reconnecting")
                    self.conn = None
                    continue

            if len(self.children) >= self.concurrency:
                time.sleep(self.poll)
                continue

            try:
                row = claim(conn)
            except Exception:
                log.exception("Claim failed; reconnecting")
                self.conn = None
                continue

            if row is None:
                time.sleep(self.poll)
                continue

            self._spawn(*row)

        self._drain()

    def _drain(self):
        for pid in list(self.children):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + 30
        while self.children and time.monotonic() < deadline:
            self._reap()
            if self.children:
                time.sleep(0.5)
        for pid, (proc, _job) in list(self.children.items()):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
            self.children.pop(pid, None)
        log.info("Supervisor stopped")


def self_check():
    """Insert a probe job older than any real one, claim it, verify, roll back."""
    conn = connect(autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {TABLE} "
                "(id, status, job_type, query, created_at, updated_at, progress, "
                "total_items, progress_unit) "
                "VALUES (gen_random_uuid(), 'created', 'search', 'selfcheck', "
                "now() - interval '100 years', now(), 0, 0, 'chapters') RETURNING id"
            )
            job_id = cur.fetchone()[0]
        row = claim(conn)
        assert row is not None and str(row[0]) == str(job_id), f"claim returned {row}"
        with conn.cursor() as cur:
            cur.execute(f"SELECT status FROM {TABLE} WHERE id = %s", (job_id,))
            assert cur.fetchone()[0] == "searching", "status not set to searching"
        print("self-check OK")
    finally:
        conn.rollback()
        conn.close()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        log.warning("Invalid %s=%r; using %s", name, os.environ.get(name), default)
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        log.warning("Invalid %s=%r; using %s", name, os.environ.get(name), default)
        return default


def main():
    if "--self-check" in sys.argv:
        self_check()
        return
    Supervisor(
        concurrency=_env_int("CRAWLER_CONCURRENCY", 1),
        poll=_env_float("CRAWLER_POLL", 2.0),
        stale_minutes=_env_float("CRAWLER_STALE_MINUTES", 10),
        requeue_every=_env_float("CRAWLER_REQUEUE_EVERY", 300),
    ).run()


if __name__ == "__main__":
    main()
