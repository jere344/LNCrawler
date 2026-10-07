from django.contrib import admin

from ..models import HarvestCandidate, HarvestConfig


@admin.register(HarvestConfig)
class HarvestConfigAdmin(admin.ModelAdmin):
    """Singleton controlling the background harvest feeder.

    Start/stop and concurrency live here so no container restart is needed.
    """

    list_display = ("enabled", "max_concurrent", "muted_count", "last_harvest_at", "updated_at")
    readonly_fields = ("last_harvest_at", "updated_at")
    fields = ("enabled", "max_concurrent", "muted_sources", "last_harvest_at", "updated_at")
    actions = ("enable_harvest", "disable_harvest")

    def has_add_permission(self, request):
        return not HarvestConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Muted sources")
    def muted_count(self, obj):
        return len(obj.muted_sources or [])

    @admin.action(description="Enable harvest (start feeding)")
    def enable_harvest(self, request, queryset):
        HarvestConfig.objects.update(enabled=True)
        self.message_user(request, "Harvest enabled.")

    @admin.action(description="Disable harvest (stop feeding)")
    def disable_harvest(self, request, queryset):
        HarvestConfig.objects.update(enabled=False)
        self.message_user(request, "Harvest disabled.")


@admin.register(HarvestCandidate)
class HarvestCandidateAdmin(admin.ModelAdmin):
    list_display = ("source_name", "title", "status", "job_id", "created_at")
    list_filter = ("status", "source_name")
    search_fields = ("title", "novel_url", "source_name")
    readonly_fields = ("created_at", "updated_at", "job_id")
    actions = ("retry_failed", "mute_sources", "unmute_sources")

    @admin.action(description="Retry selected failed candidates")
    def retry_failed(self, request, queryset):
        updated = queryset.filter(status=HarvestCandidate.STATUS_FAILED).update(
            status=HarvestCandidate.STATUS_PENDING, job_id=None
        )
        self.message_user(request, f"Requeued {updated} failed candidate(s).")

    @admin.action(description="Mute the selected candidates' sources")
    def mute_sources(self, request, queryset):
        config = HarvestConfig.get_solo()
        for name in set(queryset.values_list("source_name", flat=True)):
            config.mute(name)
        self.message_user(request, "Muted the selected source(s).")

    @admin.action(description="Unmute the selected candidates' sources")
    def unmute_sources(self, request, queryset):
        config = HarvestConfig.get_solo()
        for name in set(queryset.values_list("source_name", flat=True)):
            config.unmute(name)
        self.message_user(request, "Unmuted the selected source(s).")
