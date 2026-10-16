"""Minimal Django settings for the crawler job executor.

The executor only needs the ORM and the project models to run a claimed job; it
never serves HTTP. Dropping the web-only apps (admin, sessions, messages,
staticfiles, DRF/simplejwt/corsheaders/sitemaps/authtoken) keeps each short-lived
job subprocess several MB smaller. Everything else is imported from the shared
settings so there is a single source of truth.

Used by ``crawler_supervisor.py`` via DJANGO_SETTINGS_MODULE=api_project.settings_crawler.
"""

from .settings import *  # noqa: F401,F403

# contenttypes is required by auth; postgres is required by ArrayField models.
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.postgres",
    "lncrawler_api",
    "auth_app",
]

# No HTTP request handling happens in a job subprocess.
MIDDLEWARE = []
TEMPLATES = []
ROOT_URLCONF = None
