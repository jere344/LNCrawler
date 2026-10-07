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

# Execute the main process
exec "$@"
