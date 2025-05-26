#!/bin/sh

# Replace environment variables in the Nginx template file
envsubst '${API_HOST} ${FRONTEND_HOST}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

# Execute the main process
exec "$@"
