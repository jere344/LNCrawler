#!/bin/sh

# Derive the Host-based routing names from the public URLs so .env only needs
# SITE_URL / SITE_API_URL (plus NGINX_PORT for the published port).
strip_host() {
    host="${1#*://}"   # drop scheme
    host="${host%%/*}" # drop path
    host="${host%%:*}" # drop port
    printf '%s' "$host"
}

API_HOST=$(strip_host "$SITE_API_URL")
FRONTEND_HOST=$(strip_host "$SITE_URL")
export API_HOST FRONTEND_HOST

# Replace environment variables in the Nginx template file
envsubst '${API_HOST} ${FRONTEND_HOST}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

# Refresh the crawler User-Agent map (best effort; keeps the baked copy on
# failure). Backgrounded so a slow/offline fetch never delays nginx startup.
/usr/local/bin/update-render-seo-map.sh &

# Run periodic jobs (the daily UA-map refresh) in the background. -d logs to
# stderr: no syslog daemon runs in this image, so -S would hide failures.
crond -b -d 8

# Execute the main process
exec "$@"
