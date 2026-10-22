# syntax=docker/dockerfile:1
FROM python:3.14-slim


# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    gcc \
    python3-dev \
    libpq-dev \
    p7zip-full \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up the working directory
WORKDIR /app/lncrawler-api

# Install Playwright and its Chromium browser first, so changing another
# requirement does not download the browser again.
# Native (curl_cffi) crawling works without it; the browser is the antibot fallback.
COPY requirements-playwright.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-playwright.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Install the other Python dependencies (pip's download cache is kept between builds).
# The constraint fails the build if requirements.txt pins another Playwright
# version than requirements-playwright.txt (the browser above would not match).
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -c requirements-playwright.txt

# Copy the startup scripts
COPY start.sh start_crawler.sh start_scheduler.sh /app/lncrawler-api/
RUN sed -i 's/\r$//' /app/lncrawler-api/start.sh /app/lncrawler-api/start_crawler.sh /app/lncrawler-api/start_scheduler.sh \
    && chmod +x /app/lncrawler-api/start.sh /app/lncrawler-api/start_crawler.sh /app/lncrawler-api/start_scheduler.sh

# Create logs directory for gunicorn
RUN mkdir -p /app/lncrawler-api/logs

# Expose the port
EXPOSE 8000

# We don't need to define CMD here as it will be specified in docker-compose.yml
