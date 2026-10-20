#!/bin/bash
set -e

. "$(dirname "$0")/wait_for_db.sh"
wait_for_db

echo "Waiting for the api service to apply migrations..."
until python manage.py migrate --check >/dev/null 2>&1; do
  sleep 2
done

echo "Starting crawler supervisor..."
export SERVICE_NAME=crawler
# Lightweight supervisor that claims jobs and runs each in a short-lived
# subprocess, so per-job memory (Django + lncrawl + Chromium) is released on exit.
exec python crawler_supervisor.py
