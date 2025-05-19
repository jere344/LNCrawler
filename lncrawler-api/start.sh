#!/bin/bash
set -e

echo "Waiting for database..."
while ! pg_isready -h db -U $POSTGRES_USER -q; do
  sleep 1
done
echo "Database is ready!"

# echo "Checking migration status..."
# python manage.py showmigrations

echo "Applying migrations..."
python manage.py migrate --noinput

# echo "Migration status after applying..."
# python manage.py showmigrations

# Create superuser if it doesn't exist
echo "Creating superuser if needed..."
python manage.py createsuperuser --noinput || echo "Superuser already exists or could not be created"

echo "Starting server..."
python manage.py runserver 0.0.0.0:8000
