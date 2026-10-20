import re

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from ..models import NovelFromSource, PlaceholderCover
from ..services.covers.duplicates import duplicate_cover_groups
from ..services.covers.placeholders import mark_placeholder
from ..utils.media_utils import build_media_url

DUPLICATES_LIMIT = 100
SAMPLES_PER_GROUP = 5
PHASH_RE = re.compile(r"[0-9a-f]{16}")


def _min_novels(request):
    try:
        value = int(request.GET.get("min", 2))
    except (TypeError, ValueError):
        value = 2
    return max(value, 2)


@admin.register(PlaceholderCover)
class PlaceholderCoverAdmin(admin.ModelAdmin):
    list_display = ("preview", "cover_phash", "removed_count", "created_at")
    readonly_fields = ("preview", "cover_phash", "sample_path", "removed_count", "created_at")
    change_list_template = "admin/lncrawler_api/placeholdercover/change_list.html"

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_change_permission(request):
            extra_context["duplicates_button"] = {
                "url": reverse("admin:lncrawler_api_placeholdercover_duplicates"),
                "label": "Find duplicate covers",
            }
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Inserted before the defaults so "duplicates/" is not swallowed by the
        # "<path:object_id>/" change view.
        custom = [
            path(
                "duplicates/",
                self.admin_site.admin_view(self.duplicates_view),
                name="lncrawler_api_placeholdercover_duplicates",
            ),
        ]
        return custom + super().get_urls()

    @admin.display(description="Preview")
    def preview(self, obj):
        url = build_media_url(obj.sample_path)
        if not url:
            return "-"
        return format_html('<img src="{}" height="75">', url)

    def duplicates_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        min_novels = _min_novels(request)
        duplicates_url = reverse("admin:lncrawler_api_placeholdercover_duplicates")

        if request.method == "POST":
            # Marking removes covers from sources, so it needs more than page access.
            if not request.user.has_perm("lncrawler_api.change_novelfromsource"):
                raise PermissionDenied
            phash = (request.POST.get("phash") or "").strip().lower()
            if not PHASH_RE.fullmatch(phash):
                self.message_user(request, "Invalid cover hash.", level=messages.ERROR)
                return redirect(f"{duplicates_url}?min={min_novels}")
            pending = NovelFromSource.objects.filter(cover_phash=phash).count()
            mark_placeholder(phash)
            self.message_user(
                request,
                f"Removed {pending} cover(s) with hash {phash}; future imports will drop it.",
                level=messages.SUCCESS,
            )
            return redirect(f"{duplicates_url}?min={min_novels}")

        groups = [
            self._duplicate_group(group)
            for group in duplicate_cover_groups(min_novels)[:DUPLICATES_LIMIT]
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Duplicate covers",
            "opts": self.model._meta,
            "groups": groups,
            "min": min_novels,
        }
        return render(request, "admin/lncrawler_api/placeholdercover/duplicates.html", context)

    def _duplicate_group(self, group):
        """One row of the duplicates page: a hash, its sources and a few samples."""
        phash = group["cover_phash"]
        sources = (
            NovelFromSource.objects.filter(cover_phash=phash)
            .select_related("external_source")
            .order_by("pk")
        )
        samples = list(sources[:SAMPLES_PER_GROUP])
        cover_rel = next((s.cover_min_path for s in samples if s.cover_min_path), None)
        if cover_rel is None:
            cover_rel = (
                sources.exclude(cover_min_path__isnull=True)
                .exclude(cover_min_path="")
                .values_list("cover_min_path", flat=True)
                .first()
            )
        return {
            "phash": phash,
            "sources": group["sources"],
            "novels": group["novels"],
            "cover_url": build_media_url(cover_rel),
            "samples": [
                {
                    "title": s.title,
                    "source": s.external_source.source_name,
                    "url": reverse("admin:lncrawler_api_novelfromsource_change", args=[s.pk]),
                }
                for s in samples
            ],
            "more": group["sources"] - len(samples),
        }
