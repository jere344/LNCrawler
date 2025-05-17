# LNCrawler

LNCrawler is a web application for reading and managing light novels. It consists of a Django-based API backend and a React-based frontend, containerized using Docker.
LNCrawler use the lightnovel-crawler project by [dipudb](https://github.com/dipu-bd/lightnovel-crawler) as a base to allow a downloading feature on the website, allowing users to add novels to the website automatically.

The project is a rewrite of the original lightnovel-crawler-website react branch by [jere344](https://github.com/jere344). It is still still in very early stages of development.

## Table of Contents

- [LNCrawler](#lncrawler)
  - [Table of Contents](#table-of-contents)
  - [Project Structure](#project-structure)
  - [Features](#features)
  - [Technology Stack](#technology-stack)
  - [Prerequisites](#prerequisites)
  - [Getting Started](#getting-started)
    - [Configuration](#configuration)
    - [Running with Docker Compose](#running-with-docker-compose)
  - [Accessing the Application](#accessing-the-application)
  - [Environment Variables](#environment-variables)
    - [`api` Service:](#api-service)
    - [`frontend` Service:](#frontend-service)
    - [`db` Service:](#db-service)
  - [Contributing](#contributing)

## Project Structure

```
lncrawler/
├── dipudb-lncrawler-jere344-patches/  # The lightnovel-crawler project with minor patches allowing it to work with the current version of LNCrawler
├── lncrawler-api/                     # Django backend API
├── lncrawler-frontend/                # React frontend application
├── docker-compose.yml                 # Docker Compose configuration
└── README.md                          # This file
```

## Features

*   Browse and read light novels.
*   Add novels to the website using the lightnovel-crawler project.
*   User-configurable reader settings (font size, color, margins, etc.).
*   Chapter navigation and preloading.
*   Comment section for chapters.
*   Admin panel for managing novels and users.

## Technology Stack

*   **Backend:** Django, Django REST framework
*   **Frontend:** React, Vite, TypeScript, Material-UI
*   **Database:** PostgreSQL
*   **Containerization:** Docker, Docker Compose

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)

## Getting Started

### Configuration

1.  **Clone the repository and submodule (if you haven't already):**
    ```bash
    git clone https://github.com/jere344/LNCrawler.git --recurse-submodules
    cd lncrawler
    ```

2.  **Review Environment Variables:**
    Open `docker-compose.yml` and review the environment variables for the `api` and `frontend` services.
    Key variables to note:
    *   `SITE_URL`, `SITE_API_URL` (for `api` service)
    *   `VITE_API_BASE_URL` (for `frontend` service)
    *   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (for `db` and `api` services)
    *   `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD` (for `api` service)
    *   `SECRET_KEY` (for `api` service - **important to change for production**)

### Running with Docker Compose

1.  **Build and run the containers:**
    From the root directory of the project (`lncrawler/`), run:
    ```bash
    docker-compose up -d --build
    ```
    This command will build the images for the API and frontend services and start all services (database, API, frontend) in detached mode.

2.  **To stop the services:**
    ```bash
    docker-compose down
    ```

## Accessing the Application

Once the services are running:

*   **Frontend Application:** Open your browser and navigate to `http://localhost:8185` (or the adress you configured for `frontend`).
*   **API:** The API will be accessible at `http://localhost:8186` (or the adress you configured for `api`).
*   **Django Admin Panel:** Navigate to `http://localhost:8186/admin`.
    *   Default credentials (from `docker-compose.yml`):
        *   Username: `admin`
        *   Password: `admin`
    *   You can change these credentials via the admin panel after logging in or by modifying the `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` environment variables and restarting the `api` service.

## Environment Variables

Key environment variables are defined in the `docker-compose.yml` file for each service.

### `api` Service:

*   `SITE_URL`: Frontend URL (e.g., `http://localhost:8185`)
*   `SITE_API_URL`: API URL (e.g., `http://localhost:8186`)
*   `CORS_ORIGIN_WHITELIST`: Comma-separated list of allowed origins for CORS.
*   `ALLOWED_HOSTS`: Comma-separated list of allowed hostnames for Django.
*   `SECRET_KEY`: Django secret key. **Change this for any production deployment.**
*   `DEBUG`: Set to `True` for development, `False` for production.
*   `CORS_ALLOW_ALL_ORIGINS`: Set to `True` for development, `False` for production (use `CORS_ORIGIN_WHITELIST` instead).
*   `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`: Credentials for the initial superuser.
*   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`: Database connection details.

### `frontend` Service:

*   `VITE_API_BASE_URL`: The base URL for the API that the frontend will connect to (e.g., `http://localhost:8186`).

### `db` Service:

*   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: Database credentials.

**Note:** For production environments, it is highly recommended to use more secure methods for managing secrets and configurations, such as Docker secrets or environment-specific configuration files not committed to the repository.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.