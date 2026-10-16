import subprocess
import sys
import threading

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import connection
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils import timezone
from lncrawler_api.models import HarvestCandidate, HarvestConfig, ScheduledTask

from ..services import harvest_service

# One maintenance task of each kind at a time: these move folders / scan the
# network, so overlapping runs would corrupt state or hammer sources.
_scan_lock = threading.Lock()
_import_lock = threading.Lock()


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


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'colored_status', 
        'interval_display', 
        'last_run_at', 
        'next_run_at', 
        'worker_info',
        'updated_at'
    ]
    list_filter = ['status', 'created_at']
    readonly_fields = [
        'created_at', 
        'updated_at', 
        'worker_id', 
        'locked_until',
        'last_run_at'
    ]
    search_fields = ['name', 'worker_id']
    change_list_template = "admin/lncrawler_api/scheduler/change_list.html"
    
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
    
    def colored_status(self, obj):
        colors = {
            'pending': '#ffc107',
            'running': '#007bff',
            'completed': '#28a745',
            'failed': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        
        status_text = obj.status
        if obj.locked_until and obj.locked_until > timezone.now():
            status_text += " (locked)"
        elif obj.locked_until and obj.locked_until <= timezone.now():
            status_text += " (STALE LOCK)"
            color = '#dc3545'  # Red for stale locks
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status_text.upper()
        )
    colored_status.short_description = 'Status'
    
    def interval_display(self, obj):
        hours = obj.interval_seconds // 3600
        minutes = (obj.interval_seconds % 3600) // 60
        seconds = obj.interval_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    interval_display.short_description = 'Interval'
    
    def worker_info(self, obj):
        if obj.worker_id and obj.locked_until:
            if obj.locked_until > timezone.now():
                return format_html(
                    '<span style="color: #007bff;">{}</span>',
                    obj.worker_id
                )
            else:
                return format_html(
                    '<span style="color: #dc3545; text-decoration: line-through;">{}</span>',
                    obj.worker_id
                )
        return "-"
    worker_info.short_description = 'Worker'
    
    actions = ['reset_tasks', 'cleanup_stale_locks', 'run_now']
    
    def reset_tasks(self, request, queryset):
        count = 0
        for task in queryset:
            task.status = 'pending'
            task.locked_until = None
            task.worker_id = None
            task.error_message = ""
            task.save()
            count += 1
        
        self.message_user(request, f"Reset {count} tasks to pending state.")
    reset_tasks.short_description = "Reset selected tasks to pending state"
    
    def cleanup_stale_locks(self, request, queryset):
        count = 0
        for task in queryset.filter(locked_until__lt=timezone.now(), status='running'):
            task.status = 'pending'
            task.locked_until = None
            task.worker_id = None
            task.error_message = "Lock expired - cleaned up by admin"
            task.save()
            count += 1
        
        self.message_user(request, f"Cleaned up {count} stale locks.")
    cleanup_stale_locks.short_description = "Clean up stale locks in selected tasks"

    @admin.action(description="Run now (schedule for the next scheduler tick)")
    def run_now(self, request, queryset):
        # Heavy commands must not run inside the HTTP request; pull next_run_at
        # forward so the scheduler picks the task up on its next pass.
        updated = queryset.update(
            next_run_at=timezone.now(), status='pending', locked_until=None
        )
        self.message_user(request, f"Scheduled {updated} task(s) to run now.")

    # -- Maintenance page ----------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["management_url"] = reverse("admin:lncrawler_api_scheduledtask_management")
        return super().changelist_view(request, extra_context=extra_context)

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
        if not self.has_change_permission(request):
            raise PermissionDenied

        if request.method == "POST":
            self._handle_management_action(request)
            return redirect(reverse("admin:lncrawler_api_scheduledtask_management"))

        config = HarvestConfig.get_solo()
        from ..scheduler import scheduler_enabled

        counts = {
            status: HarvestCandidate.objects.filter(status=status).count()
            for status, _ in HarvestCandidate.STATUS_CHOICES
        }
        context = {
            **self.admin_site.each_context(request),
            "title": "Maintenance",
            "opts": self.model._meta,
            "config": config,
            "counts": counts,
            "tasks": ScheduledTask.objects.order_by("name"),
            "scheduler_enabled": scheduler_enabled(),
            "harvest_config_url": reverse("admin:lncrawler_api_harvestconfig_changelist"),
            "harvest_candidate_url": reverse("admin:lncrawler_api_harvestcandidate_changelist"),
            "result": request.session.pop("maintenance_result", None),
        }
        return render(request, "admin/lncrawler_api/scheduler/management.html", context)

    def _handle_management_action(self, request):
        action = request.POST.get("action")
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
            if _run_background(_scan_lock, harvest_service.run_scan_subprocess):
                messages.success(request, "Harvest scan started in the background.")
            else:
                messages.info(request, "A harvest scan is already running.")
        elif action == "run_import":
            if _run_background(_import_lock, lambda: call_command("run_import", verbosity=0)):
                messages.success(request, "Import started in the background.")
            else:
                messages.info(request, "An import is already running.")
        elif action == "run_task":
            name = request.POST.get("name", "")
            updated = ScheduledTask.objects.filter(name=name).update(
                next_run_at=timezone.now(), status="pending", locked_until=None
            )
            if updated:
                messages.success(request, f"'{name}' scheduled to run now.")
            else:
                messages.error(request, f"No task named '{name}'.")
        elif action == "test_source":
            url = (request.POST.get("url") or "").strip()
            if url:
                self._run_source_test(request, url)
            else:
                messages.error(request, "Enter a novel URL to test.")

    def _run_source_test(self, request, url):
        cmd = [sys.executable, "manage.py", "check_source", "--url", url, "--timeout", "60"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(settings.BASE_DIR),
                capture_output=True,
                text=True,
                timeout=90,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            request.session["maintenance_result"] = output.strip()
            if proc.returncode == 0:
                messages.success(request, "Source test PASSED.")
            else:
                messages.warning(request, f"Source test finished with exit code {proc.returncode}.")
        except subprocess.TimeoutExpired:
            request.session["maintenance_result"] = "Timed out after 90s"
            messages.error(request, "Source test timed out.")
