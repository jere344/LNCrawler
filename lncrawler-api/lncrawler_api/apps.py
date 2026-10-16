from django.apps import AppConfig


class LncrawlerApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lncrawler_api"

    def ready(self):
        # The database scheduler used to auto-start in every process that
        # imported the app (all gunicorn workers + the crawler worker), which
        # meant several scheduler threads competed for the same locks and the
        # tasks were effectively never executed. It now runs in exactly one
        # place: the dedicated `scheduler` service via
        # `manage.py run_scheduler` (see start_scheduler.sh).
        pass
