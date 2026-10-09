from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import path, reverse
from ..models import (
    NovelFromSource,
    Author,
    Editor,
    Translator,
    Tag,
    TagAlias,
    ExternalSource,
    SourceVote,
    Volume,
)
from ..services.merge_service import MergeError, merge_similar_tags, merge_tags
from django.utils.html import format_html
from .perf import CappedCountPaginator


# ``Tag`` has no FK to itself, so borrow the FK-to-Tag field from ``TagAlias``
# to power an autocomplete widget for picking tags.
TAG_AUTOCOMPLETE_FIELD = TagAlias._meta.get_field("tag")


# Register all novel-related models
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Editor)
class EditorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Translator)
class TranslatorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "source_count")
    search_fields = ("name",)
    ordering = ("name",)
    change_list_template = "admin/lncrawler_api/tag/change_list.html"

    def source_count(self, obj):
        return obj.novels.count()

    source_count.short_description = "Novel From Source Count"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_change_permission(request):
            extra_context["merge_button"] = {
                "url": reverse("admin:lncrawler_api_tag_merge"),
                "label": "Merge tags",
            }
            extra_context["auto_merge_button"] = {
                "url": reverse("admin:lncrawler_api_tag_merge_similar"),
                "label": "Merge similar tags",
            }
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Inserted before the defaults so "merge/" is not swallowed by the
        # "<path:object_id>/" change view.
        custom = [
            path(
                "merge/",
                self.admin_site.admin_view(self.merge_view),
                name="lncrawler_api_tag_merge",
            ),
            path(
                "merge-similar/",
                self.admin_site.admin_view(self.merge_similar_view),
                name="lncrawler_api_tag_merge_similar",
            ),
        ]
        return custom + super().get_urls()

    def merge_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Merge tags",
            "opts": self.model._meta,
        }

        if request.method == "POST":
            form = MergeTagForm(request.POST)
            if form.is_valid():
                source = form.cleaned_data["source_tag"]
                target = form.cleaned_data["target_tag"]

                if "confirm" in request.POST:
                    try:
                        merge_tags(source, target)
                    except MergeError as e:
                        messages.error(request, str(e))
                    else:
                        messages.success(
                            request,
                            f"Merged tag '{source.name}' into '{target.name}'.",
                        )
                        return redirect(
                            reverse("admin:lncrawler_api_tag_changelist")
                        )
                else:
                    context["source"] = source
                    context["target"] = target
                    context["preview"] = True
        else:
            form = MergeTagForm()

        context["form"] = form
        return render(request, "admin/lncrawler_api/tag/merge.html", context)

    def merge_similar_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Merge similar tags",
            "opts": self.model._meta,
        }

        if request.method == "POST" and "confirm" in request.POST:
            results = merge_similar_tags()
            if results:
                messages.success(
                    request,
                    f"Merged {sum(len(d) for _, d in results)} tag(s) "
                    f"into {len(results)} canonical tag(s).",
                )
            else:
                messages.info(request, "No similar tags found.")
            return redirect(reverse("admin:lncrawler_api_tag_changelist"))

        context["results"] = merge_similar_tags(dry_run=True)
        return render(request, "admin/lncrawler_api/tag/merge_similar.html", context)


class MergeTagForm(forms.Form):
    """Pick the duplicate tag and the canonical one to merge it into."""

    source_tag = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        label="Duplicate tag (deleted after merge)",
        widget=AutocompleteSelect(TAG_AUTOCOMPLETE_FIELD, admin.site),
    )
    target_tag = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        label="Canonical tag (kept)",
        widget=AutocompleteSelect(TAG_AUTOCOMPLETE_FIELD, admin.site),
    )

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source_tag")
        target = cleaned.get("target_tag")
        if source and target and source.pk == target.pk:
            raise forms.ValidationError("A tag cannot be merged into itself.")
        return cleaned


@admin.register(TagAlias)
class TagAliasAdmin(admin.ModelAdmin):
    list_display = ("name", "tag", "created_at")
    search_fields = ("name", "tag__name")
    raw_id_fields = ("tag",)


# Add inline for showing votes in NovelFromSource admin
class SourceVoteInline(admin.TabularInline):
    model = SourceVote
    extra = 0
    fields = ("ip_address", "vote_type", "created_at")
    readonly_fields = ("ip_address", "created_at")
    can_delete = True
    max_num = 100  # Limit displayed votes


@admin.register(NovelFromSource)
class NovelFromSourceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "external_source__source_name",
        "link_to_novel",
        "status",
        "chapters_count",
        "vote_score_display",
        "last_chapter_update",
        "id",
    )
    list_filter = ("external_source__source_name", "status", "language")
    search_fields = ("title", "novel__title", "external_source__source_name")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "chapters_count",
        "link_to_novel",
        "upvotes",
        "downvotes",
        "vote_score",
        "view_chapters_link",
    )
    raw_id_fields = ("novel",)
    inlines = [SourceVoteInline]  # Removed ChapterInline
    paginator = CappedCountPaginator
    list_select_related = ("external_source", "novel")
    show_full_result_count = False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_chapters_count=Count("chapters"))

    def chapters_count(self, obj):
        return obj._chapters_count

    chapters_count.short_description = "Chapters"
    chapters_count.admin_order_field = "_chapters_count"

    def link_to_novel(self, obj):
        url = reverse("admin:lncrawler_api_novel_change", args=[obj.novel.id])
        return format_html('<a href="{}">{}</a>', url, obj.novel.title)

    link_to_novel.short_description = "Novel"

    def vote_score_display(self, obj):
        return obj.vote_score

    vote_score_display.short_description = "Vote Score"

    def delete_queryset(self, request, queryset):
        """
        Override the default delete_queryset method to call delete() on each object
        This ensures the model's delete method runs for bulk deletions from the list page
        """
        for obj in queryset:
            obj.delete()

    def view_chapters_link(self, obj):
        if obj.pk:
            url = f"/admin/lncrawler_api/chapter/?novel_from_source__id__exact={obj.pk}"
            return format_html('<a href="{}" target="_blank">View Chapters ({})</a>', url, obj._chapters_count)
        return "Save first to view chapters"

    view_chapters_link.short_description = "Chapters"


@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = ("title", "novel_from_source", "volume_id", "chapter_count")
    list_filter = ("novel_from_source__external_source__source_name",)
    search_fields = ("title", "novel_from_source__title")
    raw_id_fields = ("novel_from_source",)
    paginator = CappedCountPaginator
    list_select_related = ("novel_from_source", "novel_from_source__external_source")
    show_full_result_count = False


# Register new models
@admin.register(SourceVote)
class SourceVoteAdmin(admin.ModelAdmin):
    list_display = ("source", "ip_address", "vote_type", "created_at")
    list_filter = ("vote_type", "created_at")
    search_fields = ("source__title", "ip_address")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("source",)

@admin.register(ExternalSource)
class ExternalSourceAdmin(admin.ModelAdmin):
    list_display = ("source_name", "status")
    search_fields = ("source_name",)
    list_filter = ("status",)