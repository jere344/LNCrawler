import logging
import threading

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.urls import path, reverse
from django.shortcuts import redirect
from django.utils import timezone
from lncrawler_api.models import HarvestCandidate, HarvestConfig, ScheduledTask

from ..services import harvest_service

logger = logging.getLogger("lncrawler_api.harvest")

# One harvest scan at a time: it hits the network, so overlapping runs would hammer sources.
# This thread lock covers one process; the Postgres advisory lock taken in _scan_in_thread covers all of them.
_scan_lock = threading.Lock()

# Operations actions that change the harvest settings or start a scan; they need change_harvestconfig.
HARVEST_ACTIONS = {"toggle_harvest", "set_concurrency", "run_scan"}


def _run_background(lock, fn) -> bool:
    """Run ``fn`` in a daemon thread unless one is already running.

    Returns False when the lock is held. Closes the thread's DB connection on
    exit so repeated clicks do not leak Postgres sessions.
    """
    if not lock.acquire(blocking=False):
        return False

    def wrapper():
        try:
            fn()
        finally:
            connection.close()
            lock.release()

    threading.Thread(target=wrapper, daemon=True).start()
    return True


def _scan_in_thread():
    if not harvest_service.acquire_scan_lock():
        logger.info("Harvest scan skipped: another process is already scanning.")
        return
    try:
        harvest_service.run_scan_subprocess()
    finally:
        harvest_service.release_scan_lock()


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'last_run_at', 'next_run_at', 'updated_at']
    list_filter = ['status', 'created_at']
    readonly_fields = [
        'created_at',
        'updated_at',
        'worker_id',
        'locked_until',
        'last_run_at'
    ]
    search_fields = ['name', 'worker_id']

    fieldsets = (
        (None, {
            'fields': ('name', 'interval_seconds', 'status')
        }),
        ('Scheduling', {
            'fields': ('last_run_at', 'next_run_at'),
        }),
        ('Lock Info', {
            'fields': ('locked_until', 'worker_id'),
            'classes': ['collapse'],
        }),
        ('Error Info', {
            'fields': ('error_message',),
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse'],
        }),
    )

    # -- Operations (on the admin home) ---------------------------------------

    def get_model_perms(self, request):
        # Kept out of the sidebar: the tasks list lives on the admin home. The change page stays
        # reachable from the "failed" link there.
        return {}

    def changelist_view(self, request, extra_context=None):
        # The tasks list lives on the admin home.
        return redirect(reverse("admin:index"))

    def get_urls(self):
        custom = [
            path(
                "management/",
                self.admin_site.admin_view(self.management_view),
                name="lncrawler_api_scheduledtask_management",
            ),
        ]
        return custom + super().get_urls()

    def management_view(self, request):
        # Receives the harvest and task forms of the admin home, then goes back there.
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            self._handle_management_action(request)
        return redirect(reverse("admin:index"))

    def _handle_management_action(self, request):
        from ..scheduler import scheduler

        action = request.POST.get("action")
        if action in HARVEST_ACTIONS and not request.user.has_perm("lncrawler_api.change_harvestconfig"):
            messages.error(request, "You need permission to change the harvest settings.")
            return
        config = HarvestConfig.get_solo()

        if action == "toggle_harvest":
            config.enabled = not config.enabled
            config.save(update_fields=["enabled", "updated_at"])
            messages.success(request, f"Harvest {'enabled' if config.enabled else 'disabled'}.")
        elif action == "set_concurrency":
            try:
                config.max_concurrent = max(1, int(request.POST.get("max_concurrent", 3)))
                config.save(update_fields=["max_concurrent", "updated_at"])
                messages.success(request, f"Max concurrent set to {config.max_concurrent}.")
            except (TypeError, ValueError):
                messages.error(request, "Invalid concurrency value.")
        elif action == "run_scan":
            if _run_background(_scan_lock, _scan_in_thread):
                messages.success(request, "Harvest scan started in the background.")
            else:
                messages.info(request, "A harvest scan is already running.")
        elif action == "run_task":
            # Heavy commands must not run inside the HTTP request; pull next_run_at
            # forward so the scheduler picks the task up on its next pass.
            name = request.POST.get("name", "")
            # Same source as the table: only the tasks the scheduler registered can be run from here.
            if name not in scheduler.registered_tasks:
                messages.error(request, f"No task named '{name}'.")
                return
            now = timezone.now()
            # A live lock means the task is running now; only the worker that holds it may change its status.
            if ScheduledTask.objects.filter(name=name, status="running", locked_until__gt=now).exists():
                messages.info(request, f"'{name}' is already running.")
                return
            updated = ScheduledTask.objects.filter(name=name).update(next_run_at=now)
            if updated:
                messages.success(request, f"'{name}' scheduled to run now.")
            else:
                messages.error(request, f"No task named '{name}'.")


def operations_context(request):
    """Harvest status and the scheduled tasks, for the admin home; None without the permission to act on them."""
    if not request.user.has_perm("lncrawler_api.change_scheduledtask"):
        return None
    from ..scheduler import scheduler, scheduler_enabled

    counts = {
        status: HarvestCandidate.objects.filter(status=status).count()
        for status, _ in HarvestCandidate.STATUS_CHOICES
    }
    return {
        "action_url": reverse("admin:lncrawler_api_scheduledtask_management"),
        "config": HarvestConfig.get_solo(),
        "can_change_harvest": request.user.has_perm("lncrawler_api.change_harvestconfig"),
        "counts": counts,
        # Only tasks the scheduler still runs; rows of removed tasks are not listed.
        "tasks": ScheduledTask.objects.filter(name__in=list(scheduler.registered_tasks)).order_by("name"),
        "scheduler_enabled": scheduler_enabled(),
        "harvest_config_url": reverse("admin:lncrawler_api_harvestconfig_changelist"),
        "harvest_candidate_url": reverse("admin:lncrawler_api_harvestcandidate_changelist"),
    }
