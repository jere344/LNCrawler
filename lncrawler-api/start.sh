#!/bin/bash
set -e

echo "Waiting for database..."
while ! pg_isready -h db -U $POSTGRES_USER -d $POSTGRES_DB -q; do
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

# Collect static files for production
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn server..."
if [ "$DEBUG" = "True" ]; then
  # Use Django development server in debug mode
  python manage.py runserver 0.0.0.0:8000
else
  # Use Gunicorn for production
  gunicorn api_project.wsgi:application -c gunicorn.conf.py
fi
