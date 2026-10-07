from django.contrib import admin
from ..models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "job_type", "query", "target_url", "created_at", "updated_at", "progress", "total_items")
    list_filter = ("status", "job_type", "created_at", "updated_at")
    search_fields = ("query", "target_url", "output_path", "error_message", "import_message")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Job Information",
            {"fields": ("id", "status", "job_type", "query", "target_url", "created_at", "updated_at")},
        ),
        ("Progress", {"fields": ("progress", "total_items")}),
        (
            "Results",
            {
                "fields": (
                    "search_results",
                    "selected_novel",
                    "output_path",
                    "output_files",
                    "import_message",
                )
            },
        ),
        ("Error Information", {"fields": ("error_message",)}),
    )
