#!/bin/bash
set -e

. "$(dirname "$0")/wait_for_db.sh"
wait_for_db

# echo "Checking migration status..."
# python manage.py showmigrations

echo "Applying migrations..."
python manage.py migrate --noinput

# echo "Migration status after applying..."
# python manage.py showmigrations

# Create superuser if it doesn't exist (idempotent, safe if the api is scaled)
echo "Creating superuser if needed..."
python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
U = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if username and password and not U.objects.filter(username=username).exists():
    U.objects.create_superuser(username, os.environ.get('DJANGO_SUPERUSER_EMAIL', ''), password)
    print('Superuser created.')
else:
    print('Superuser already exists.')
" || echo "Superuser creation skipped."

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
