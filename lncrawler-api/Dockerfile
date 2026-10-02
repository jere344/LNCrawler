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

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the Chromium browser used by the crawler's Playwright backend.
# Native (curl_cffi) crawling works without it; the browser is the antibot fallback.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy the startup script
COPY start.sh /app/lncrawler-api/
RUN chmod +x /app/lncrawler-api/start.sh

# Create logs directory for gunicorn
RUN mkdir -p /app/lncrawler-api/logs

# Expose the port
EXPOSE 8000

# We don't need to define CMD here as it will be specified in docker-compose.yml
