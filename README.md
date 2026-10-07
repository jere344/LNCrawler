# LNCrawler

LNCrawler is a self-hosted web application for reading and managing light
novels. It ships its own crawler engine: users can search supported sources,
download a novel (with its chapters and metadata) and add it to the site
library. Everything runs with Docker Compose: a Django REST API, a React
frontend, PostgreSQL, dedicated background workers and an Nginx reverse proxy.

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Accessing the Application](#accessing-the-application)
- [TLS / Public Deployment](#tls--public-deployment)
- [Scaling](#scaling)
- [Configuration Reference](#configuration-reference)
- [Common Operations](#common-operations)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

## Architecture

Docker Compose runs six services:

| Service | Role |
| --- | --- |
| `db` | PostgreSQL 17, the single source of truth. |
| `api` | Django + Gunicorn. Serves the REST API, the admin, and static/media/library files. Runs migrations and creates the initial superuser on boot. |
| `crawler` | Identical, horizontally scalable job workers. Each claims queued search/download jobs from a DB-backed queue (`Job` rows) and runs them in isolation from the web workers. Scale with `CRAWLER_REPLICAS` or `--scale crawler=N`. |
| `scheduler` | Singleton process running periodic database-backed tasks with DB-level locking so two replicas never run the same task. Keep exactly one running. |
| `frontend` | React single-page app, built at image build time and served by Nginx. |
| `nginx-proxy` | The public entry point. Listens on port 80 and routes by `Host` header to the API (`API_HOST`) or the frontend (`FRONTEND_HOST`), and serves `/static`, `/media` and `/lightnovels` directly. |

The library is the crawler engine under `lncrawler-crawler/` (`lncrawl`
package plus ported `sources/`). The API imports it as a library and drives it
through `lncrawler-api/lncrawler_api/services/downloader_service.py`.

## Features

- Browse, search and read light novels in the browser.
- Search supported sources and download novels (chapters, metadata, covers)
  straight into the library.
- User accounts: registration, login, password reset (email), profiles.
- Reader with configurable settings (font, colors, margins, pagination or
  scroll) and chapter navigation/preloading.
- Library, reading history with progress resume, and custom reading lists.
- Reviews, per-chapter comments, boards/forums, and friends.
- Admin panel for managing novels, sources, jobs and users.
- Sitemap, robots.txt and i18n (multi-language UI).
- Optional automatic GitHub issue creation for unexpected errors.

## Technology Stack

- **Backend:** Django 6, Django REST framework, Gunicorn, PostgreSQL 17.
- **Frontend:** React 19, Vite, TypeScript, Material-UI, i18next.
- **Crawler:** `lncrawl` engine with `curl_cffi` (native HTTP) and Playwright
  (Chromium, anti-bot fallback).
- **Containerization:** Docker, Docker Compose, Nginx.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (the `docker
  compose` plugin)

## Quick Start

1. **Clone the repository:**

   ```bash
   git clone https://github.com/jere344/LNCrawler.git
   cd LNCrawler
   ```

2. **Create your environment file:**

   ```bash
   cp .env.example .env
   ```

   Open `.env` and set at least `SECRET_KEY`, the `POSTGRES_*` credentials,
   `SITE_URL`, `SITE_API_URL`, `API_HOST`, `FRONTEND_HOST` and
   `VITE_API_BASE_URL`. See [Configuration Reference](#configuration-reference).

3. **Build and start everything:**

   ```bash
   docker compose up -d --build
   ```

   On first boot the `api` service applies migrations, collects static files
   and creates the superuser from `DJANGO_SUPERUSER_*` if it does not exist.

4. **Follow the logs if needed:**

   ```bash
   docker compose logs -f api
   ```

5. **Stop the stack:**

   ```bash
   docker compose down
   ```

   Add `-v` to also remove the database volume (destroys all data).

## Accessing the Application

With the default `.env` (`localhost` / `api.localhost`), the proxy listens on
port 80:

- **Frontend:** http://localhost
- **API:** http://api.localhost
- **Django admin:** http://api.localhost/admin
  - Default credentials come from `DJANGO_SUPERUSER_*` (`admin` / `admin` in
    the example). Change them in the admin or in `.env` before the first boot.

The default hostnames resolve to `127.0.0.1` in most browsers/OSes. If yours
does not resolve `*.localhost`, add entries to `/etc/hosts`:

```
127.0.0.1  localhost api.localhost
```

The proxy is the only published port (`80:80`). Change the host side of the
mapping in `docker-compose.yml` if port 80 is taken.

## TLS / Public Deployment

`nginx-proxy` itself only speaks HTTP. In production, terminate TLS in front of
it (for example with Caddy) and forward to the proxy's port 80. The proxy reads
`X-Forwarded-Proto` and passes it to Django, so set:

- `SITE_URL` / `SITE_API_URL` to your public HTTPS URLs.
- `API_HOST` / `FRONTEND_HOST` to the public hostnames.
- `VITE_API_BASE_URL` to the public API URL (baked into the frontend at build
  time — rebuild the frontend after changing it).
- `DEBUG=False` and `CORS_ALLOW_ALL_ORIGINS=False`.

## Scaling

Crawler workers are independent and safe to replicate:

```bash
# Set the replica count in .env...
CRAWLER_REPLICAS=4

# ...or override it for a single run
docker compose up -d --scale crawler=4
```

The `scheduler` and `harvest` services must each stay at one instance. Both are
designed so that even if a second one starts, DB-level locking prevents
duplicate work.

## Configuration Reference

All variables live in `.env` (loaded by `docker compose`). `.env.example`
documents the defaults.

### Database

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — credentials.
- `POSTGRES_HOST` (`db`), `POSTGRES_PORT` (`5432`) — point the API at the
  Compose database service.

### Django

- `SITE_URL` — public frontend URL. Also used to build absolute media and
  library URLs.
- `SITE_API_URL` — public API URL.
- `SECRET_KEY` — Django secret key. **Change it for any real deployment.**
- `DEBUG` — `True` uses Django's dev server, `False` uses Gunicorn. Use
  `False` in production.
- `CORS_ALLOW_ALL_ORIGINS` — `False` in production.
- `LOG_LEVEL` *(optional)* — defaults to `INFO` (or `DEBUG` when `DEBUG=True`).
- `HOME_PAGE_CACHE_SECONDS` *(optional)* — per-worker home page cache TTL.

### Superuser

- `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`,
  `DJANGO_SUPERUSER_PASSWORD` — created on first boot only.

### Email

Password-reset emails go out over standard SMTP, so any provider works and
switching is a config change only.

- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` — SMTP server. Defaults are
  MailPace (`smtp.mailpace.com:587`, STARTTLS). MailPace uses the domain's
  API token as **both** `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`.
- `DEFAULT_FROM_EMAIL`, `EMAIL_SENDER_NAME`.

Without credentials, local development (`DEBUG=True`) prints reset emails to
the console instead of sending them.

### Frontend build

- `VITE_API_BASE_URL` — API base URL compiled into the frontend. Rebuild the
  frontend image after changing it.

### Nginx proxy

- `API_HOST` — hostname routed to the API.
- `FRONTEND_HOST` — hostname routed to the frontend.

### Crawler

- `CRAWLER_REPLICAS` — number of worker replicas (default `1`).
- `CRAWLER_CONCURRENCY` *(optional)* — concurrent job subprocesses per worker
  (default `5`). Each job is its own process, so raise `CRAWLER_MEM_LIMIT`
  alongside it.
- `CRAWLER_MEM_LIMIT` *(optional)* — per-crawler cgroup memory cap (default
  `2g`); a runaway job OOM-kills the worker, not the host.
- `CRAWLER_POLL`, `CRAWLER_STALE_MINUTES`, `CRAWLER_REQUEUE_EVERY` *(optional)*
  — queue polling and stale-job retry tuning.
- `LNCRAWL_<KEY>_USERNAME` / `LNCRAWL_<KEY>_PASSWORD` — credentials for
  login-gated sources, where `<KEY>` is the source's canonical domain label
  uppercased (e.g. `LNCRAWL_CYRISIA_USERNAME`).

### Scheduled maintenance

- `SCHEDULER_ENABLED` *(optional)* — master switch for all background
  maintenance tasks (default `True`). Set to `False` to stop them and run the
  commands by hand instead. The scheduler container stays up either way.
- `LNCRAWL_PRUNE_APPLY` *(optional)* — set to `False` to skip the destructive
  scheduled library prune (it defaults to enabled).

### Harvest feeder

The `harvest` service discovers novels from each source's browse page and
queues download jobs. It is always running but inert until enabled in the
admin (**Maintenance → Harvest**). Control it there — no `.env` change or
restart is needed.

- `HARVEST_INTERVAL` *(optional)* — seconds between feeder loop iterations.
- `HARVEST_REFRESH_SECONDS` *(optional)* — minimum gap between browse scans.
- `HARVEST_SCAN_TIMEOUT` *(optional)* — seconds before a browse scan is killed.

### Error reporting

- `GITHUB_REPO` — repository to open issues in (`owner/repo`).
- `GITHUB_TOKEN` — needs `issues:write` (classic PAT) or Issues read/write
  (fine-grained PAT).
- `GITHUB_ISSUES_ENABLED` — `True` to open a deduplicated issue for every
  unexpected error (web, crawler, scheduler).

## Common Operations

Most routine maintenance runs automatically. The admin **Scheduled tasks →
Maintenance** page can start/stop the harvest feeder, trigger a scan, import
from `imports/`, test a source, and run any scheduled task on demand.

Run Django management commands inside the running API container:

```bash
# Manual migration / shell
docker compose exec api python manage.py migrate
docker compose exec api python manage.py shell

# Import novels dropped as files into imports/ (default action: move)
docker compose exec api python manage.py run_import --action copy

# Smoke-test a crawler source (add --inspect to dump its HTML + metadata)
docker compose exec api python manage.py check_source --url NOVEL_URL
```

Useful commands: `calculate_similarities`, `compress_low_traffic_novels`,
`consolidate_source_views`, `check_source`, `prune_library`, `prune_jobs`,
`update_popular_sources`. List them all with:

```bash
docker compose exec api python manage.py help
```

## Project Structure

```
lncrawler/
├── docker-compose.yml       # Service definitions and wiring
├── .env.example             # Documented environment template
├── nginx-proxy/             # Public reverse proxy (Host-based routing)
├── lncrawler-api/           # Django REST API + workers + scheduler + harvest
│   ├── api_project/         # Settings, URLs, logging, GitHub reporting
│   ├── lncrawler_api/       # Models, views, services, management commands
│   ├── auth_app/            # User model, auth and email
│   └── start*.sh            # api / crawler / scheduler / harvest entrypoints
├── lncrawler-frontend/      # React + Vite SPA
├── lncrawler-crawler/       # Crawler engine (lncrawl) and source definitions
│   ├── lncrawl/             # Core engine, models, browser backends
│   └── sources/             # Ported sources, grouped by language
├── Lightnovels/             # Downloaded library files (volume)
└── imports/                 # Drop folder consumed by run_import (volume)
```

## Contributing

Contributions are welcome. Please open an issue or a pull request. When adding
or changing a crawler source, run the source harness first:

```bash
docker compose exec api python manage.py check_source --url NOVEL_URL
# or, against a source file before it is registered:
docker compose exec api python manage.py check_source --file sources/en/x/foo.py --query "reincarnation"
```

## License

See [LICENSE](LICENSE).
