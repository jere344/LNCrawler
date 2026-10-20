#!/bin/bash
set -e

. "$(dirname "$0")/wait_for_db.sh"
wait_for_db

echo "Waiting for the api service to apply migrations..."
until python manage.py migrate --check >/dev/null 2>&1; do
  sleep 2
done

echo "Starting database scheduler..."
export SERVICE_NAME=scheduler
exec python manage.py run_scheduler
