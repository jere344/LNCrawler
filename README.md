# LNCrawler

Self-hosted light novel reader. It has its own crawler: search a supported
source, download a novel with its chapters and metadata, and it lands in your
library. Everything runs with Docker Compose — Django REST API, React frontend,
PostgreSQL, background workers and an Nginx proxy.

## Architecture

Docker Compose runs six services:

| Service       | Role                                                                                     |
| ------------- | ---------------------------------------------------------------------------------------- |
| `db`          | PostgreSQL 17                                                                            |
| `api`         | Django + Gunicorn. REST API, admin, static/media/library files. Migrates and seeds the superuser on boot. |
| `crawler`     | Job workers. Each claims search/download jobs from the DB-backed queue and runs them isolated from the web. Scale with `CRAWLER_REPLICAS` or `--scale crawler=N`. |
| `scheduler`   | Singleton maintenance process. Runs periodic tasks (DB-locked) and the harvest feeder thread. Keep exactly one. |
| `frontend`    | React SPA, built at image build time and served by Nginx.                                 |
| `nginx-proxy` | Public entry point. Routes by `Host` to the API or frontend and serves `/static`, `/media`, `/lightnovels`. |

The crawler engine lives in `lncrawler-crawler/` (the `lncrawl` package plus
ported `sources/`). The API imports it and drives it through
`lncrawler-api/lncrawler_api/services/downloader_service.py`.

## Features

- Browse, search and read light novels in the browser.
- Download novels from supported sources straight into the library.
- Accounts: registration, login, password reset, profiles.
- Reader with configurable font, colors, margins, scroll/pagination and chapter
  preloading.
- Library, reading history with resume, and custom reading lists.
- Reviews, per-chapter comments, forums, friends.
- Admin panel for novels, sources, jobs and users.
- Sitemap, robots.txt, multi-language UI.
- Optional GitHub issue creation for unexpected errors.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- Docker Compose (the `docker compose` plugin)

## Quick Start

```bash
git clone https://github.com/jere344/LNCrawler.git
cd LNCrawler
cp .env.example .env
# set at least SECRET_KEY, POSTGRES_*, SITE_URL and SITE_API_URL
docker compose up -d --build
```

On first boot `api` applies migrations, collects static files and creates the
superuser from `DJANGO_SUPERUSER_*` if missing. Logs:

```bash
docker compose logs -f api
docker compose down          # add -v to also drop the database volume
```

## Accessing the Application

With the default `.env` the proxy listens on port 80:

- Frontend: http://localhost
- API: http://api.localhost
- Admin: http://api.localhost/admin (default `admin` / `admin` from `.env`)

If `*.localhost` doesn't resolve on your machine, add it to `/etc/hosts`:

```
127.0.0.1  localhost api.localhost
```

Change `NGINX_PORT` in `.env` if port 80 is taken.

## Public Deployment

`nginx-proxy` only speaks HTTP. Terminate TLS in front of it (Caddy, etc.) and
forward to `NGINX_PORT`. The proxy passes `X-Forwarded-Proto` to Django, so set
`SITE_URL` / `SITE_API_URL` to your public HTTPS URLs, plus `DEBUG=False` and
`CORS_ALLOW_ALL_ORIGINS=False`. `API_HOST`, `FRONTEND_HOST` and the frontend's
baked-in `VITE_API_BASE_URL` are derived from those URLs; nothing else to sync.
Rebuild the frontend image after changing `SITE_API_URL` (the URL is compiled
in).

## Scaling

Crawler workers are independent and safe to replicate:

```bash
CRAWLER_REPLICAS=4                              # in .env
docker compose up -d --scale crawler=4          # or one-off
```

Keep `scheduler` at one instance. It and the feeder use DB-level locking, so a
duplicate won't double-run work.

## Configuration

Everything lives in `.env`; `.env.example` documents the defaults.

**Database** — `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_HOST` (`db`), `POSTGRES_PORT` (`5432`).

**Django** — `SITE_URL` (public frontend URL, also used for absolute media and
library URLs), `SITE_API_URL`, `SECRET_KEY` (change it), `DEBUG` (`True` uses
the dev server, `False` uses Gunicorn), `CORS_ALLOW_ALL_ORIGINS`,
`LOG_LEVEL` (default `INFO`, or `DEBUG` when `DEBUG=True`).

**Superuser** — `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`,
`DJANGO_SUPERUSER_PASSWORD` (first boot only).

**Email** — password reset goes over standard SMTP. `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_USE_TLS` (defaults to MailPace, which uses the domain API token as both
user and password), `DEFAULT_FROM_EMAIL`, `EMAIL_SENDER_NAME`. With no
credentials, dev mode prints reset emails to the console.

**Nginx proxy** — `NGINX_PORT` (default `80`). `API_HOST`, `FRONTEND_HOST` and
`VITE_API_BASE_URL` are derived; don't set them.

**Crawler** — `CRAWLER_REPLICAS`, `CRAWLER_CONCURRENCY` (jobs per worker,
default `5`), `CRAWLER_MEM_LIMIT` (per-crawler cgroup cap, default `2g`),
`CRAWLER_POLL` / `CRAWLER_STALE_MINUTES` / `CRAWLER_REQUEUE_EVERY` (queue
tuning). For login-gated sources, `LNCRAWL_<KEY>_USERNAME` /
`LNCRAWL_<KEY>_PASSWORD` where `<KEY>` is the source's canonical domain label
uppercased.

**Scheduled maintenance** — `SCHEDULER_ENABLED` (default `True`; set `False` to
run tasks by hand, container stays up), `LNCRAWL_PRUNE_APPLY` (set `False` to
skip the destructive scheduled prune).

**Harvest feeder** — discovers novels from each source's browse page and queues
downloads. Runs inside `scheduler`, inert until enabled in the admin
(**Maintenance → Harvest**) — no restart needed. `HARVEST_INTERVAL`,
`HARVEST_REFRESH_SECONDS`, `HARVEST_SCAN_TIMEOUT` tune it.

**Error reporting** — `GITHUB_REPO` (`owner/repo`), `GITHUB_TOKEN`
(`issues:write` for a classic PAT), `GITHUB_ISSUES_ENABLED` to open a
deduplicated issue per unexpected error.

## Common Operations

The admin **Scheduled tasks → Maintenance** page can start/stop the harvest
feeder, trigger a scan, import from `imports/`, test a source and run any
scheduled task on demand. Otherwise, run management commands inside the API
container:

```bash
docker compose exec api python manage.py shell
docker compose exec api python manage.py run_import --action copy
docker compose exec api python manage.py check_source --url NOVEL_URL
docker compose exec api python manage.py help      # list all commands
```

## Project Structure

```
lncrawler/
├── docker-compose.yml
├── .env.example
├── nginx-proxy/             # public reverse proxy
├── lncrawler-api/           # Django REST API, workers, maintenance
│   ├── api_project/         # settings, URLs, logging, GitHub reporting
│   ├── lncrawler_api/       # models, views, services, management commands
│   ├── auth_app/            # user model, auth, email
│   └── start*.sh            # api / crawler / scheduler entrypoints
├── lncrawler-frontend/      # React + Vite SPA
├── lncrawler-crawler/       # crawler engine (lncrawl) and sources
├── Lightnovels/             # downloaded library files (volume)
└── imports/                 # drop folder for run_import (volume)
```

## Contributing

Issues and pull requests are welcome. Before adding or changing a crawler
source, run the source harness:

```bash
docker compose exec api python manage.py check_source --url NOVEL_URL
# or against a file before it is registered:
docker compose exec api python manage.py check_source --file sources/en/x/foo.py --query "reincarnation"
```

## License

See [LICENSE](LICENSE).
