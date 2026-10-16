#!/bin/bash
set -e

echo "Waiting for database..."
while ! pg_isready -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do
  sleep 1
done

echo "Waiting for the api service to apply migrations..."
until python manage.py migrate --check >/dev/null 2>&1; do
  sleep 2
done

echo "Starting crawler supervisor..."
export SERVICE_NAME=crawler
# Lightweight supervisor that claims jobs and runs each in a short-lived
# subprocess, so per-job memory (Django + lncrawl + Chromium) is released on exit.
exec python crawler_supervisor.py
