FROM nginx:alpine

# Copy the template config file
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Copy the entrypoint script
COPY docker-entrypoint.sh /

# Make the entrypoint script executable
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Baked crawler UA map (00- prefix so it is parsed before default.conf), the
# generator that refreshes it from ai.robots.txt, and its daily cron entry.
COPY render-seo-map.default.conf /etc/nginx/conf.d/00-render-seo-map.conf
COPY update-render-seo-map.sh /usr/local/bin/update-render-seo-map.sh
RUN sed -i 's/\r$//' /usr/local/bin/update-render-seo-map.sh \
    && chmod +x /usr/local/bin/update-render-seo-map.sh \
    && ln -sf /usr/local/bin/update-render-seo-map.sh /etc/periodic/daily/update-render-seo-map

EXPOSE 80

# Use the entrypoint script
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]