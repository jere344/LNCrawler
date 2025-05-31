from django.contrib import admin
from ..models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "query", "created_at", "updated_at", "progress", "total_items")
    list_filter = ("status", "created_at", "updated_at")
    search_fields = ("query", "output_path", "error_message", "import_message")
    readonly_fields = ("id", "created_at", "updated_at", "job_pid")

    fieldsets = (
        (
            "Job Information",
            {"fields": ("id", "status", "query", "job_pid", "created_at", "updated_at")},
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
