#!/bin/sh
# Blocks until the Postgres service accepts connections.
# Sourced by start.sh, start_crawler.sh and start_scheduler.sh, which run via sh.

wait_for_db() {
  echo "Waiting for database..."
  while ! pg_isready -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do
    sleep 1
  done
  echo "Database is ready!"
}
