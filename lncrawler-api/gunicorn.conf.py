# Gunicorn configuration for production
bind = "0.0.0.0:8000"
workers = 2
worker_class = "gthread"
threads = 4
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
# Include request time (seconds, %(L)s) so real-world latency is visible in the
# access log without any extra tooling.
access_log_format = '%(h)s %(t)s "%(r)s" %(s)s %(b)s %(L)s'

# Load the app once in the master and fork workers: shared read-only pages via
# copy-on-write instead of 5 independent copies of Django + libs. Combined with
# max_requests, leaked per-worker memory is reclaimed on restart.
preload_app = True

# Keep worker heartbeat files off disk to avoid I/O stalls under load.
worker_tmp_dir = "/dev/shm"


def post_fork(server, worker):
    # A forked child must never reuse the master's DB connections.
    from django.db import connections
    connections.close_all()
