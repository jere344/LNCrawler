from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseRedirect
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
from ..models.sources_models import refresh_adult, refresh_adult_for_tags, refresh_novel_adult
from ..services.chapter_stats import refresh_chapter_stats
from ..services.folder_guard import BUSY_MESSAGE, FolderBusy
from ..services.novel_deletion import after_source_deleted
from ..services.novel_operations import FileOperationError, file_journal
from ..services.author_block_service import block_authors, unblock_authors
from ..services.merge_service import MergeError, merge_tags, rename_tag
from ..utils.tag_utils import normalize_tag
from django.utils.html import format_html
from .perf import CappedCountPaginator


# ``Tag`` has no FK to itself, so borrow the FK-to-Tag field from ``TagAlias``
# to power an autocomplete widget for picking tags.
TAG_AUTOCOMPLETE_FIELD = TagAlias._meta.get_field("tag")


class DeletedAuthorFilter(admin.SimpleListFilter):
    """The soft-delete flag of an author, under the label "Deleted"."""

    title = "Deleted"
    parameter_name = "is_blocked"

    def lookups(self, request, model_admin):
        return (("1", "Deleted"), ("0", "Active"))

    def queryset(self, request, queryset):
        if self.value() in ("0", "1"):
            return queryset.filter(is_blocked=self.value() == "1")
        return queryset


# Register all novel-related models
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "deleted")
    list_filter = (DeletedAuthorFilter,)
    search_fields = ("name",)
    actions = ["soft_delete_selected", "restore_selected"]

    def get_queryset(self, request):
        # The autocomplete of other forms only offers the visible authors, as their form fields accept.
        if request.resolver_match and request.resolver_match.url_name == "autocomplete":
            return super().get_queryset(request)
        # Soft-deleted authors stay listed here, so they can be restored.
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def has_delete_permission(self, request, obj=None):
        # Soft delete replaces deletion: a real delete lets the next import recreate the author.
        return False

    @admin.display(boolean=True, description="Deleted")
    def deleted(self, obj):
        return obj.is_blocked

    @admin.action(description="Soft delete selected authors")
    def soft_delete_selected(self, request, queryset):
        count = block_authors(list(queryset.values_list("pk", flat=True)))
        self.message_user(
            request,
            f"Soft-deleted {count} author(s): removed from their sources, kept so imports don't recreate them.",
            messages.SUCCESS,
        )

    @admin.action(description="Restore selected authors")
    def restore_selected(self, request, queryset):
        count = unblock_authors(list(queryset.values_list("pk", flat=True)))
        self.message_user(
            request,
            f"Restored {count} author(s). Their source links come back on re-import.",
            messages.SUCCESS,
        )


@admin.register(Editor)
class EditorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Translator)
class TranslatorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class TagAdminForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ("name", "is_adult")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        key = normalize_tag(name)
        clash = Tag.objects.filter(normalized=key).exclude(pk=self.instance.pk).first()
        if clash is not None:
            raise ValidationError(f"'{name}' duplicates the existing tag '{clash.name}'.")
        alias = (
            TagAlias.objects.filter(normalized=key)
            .exclude(tag_id=self.instance.pk)
            .select_related("tag")
            .first()
        )
        if alias is not None:
            raise ValidationError(
                f"'{name}' is already an alias of the tag '{alias.tag.name}'."
            )
        return name


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    form = TagAdminForm
    list_display = ("name", "is_adult", "source_count")
    list_filter = ("is_adult",)
    search_fields = ("name",)
    actions = ["mark_r18", "unmark_r18"]
    ordering = ("name",)
    readonly_fields = ("normalized",)
    change_list_template = "admin/lncrawler_api/tag/change_list.html"

    def save_model(self, request, obj, form, change):
        # Renames go through rename_tag so the old name becomes an alias.
        if change and "name" in form.changed_data:
            rename_tag(Tag.objects.get(pk=obj.pk), obj.name)
            if "is_adult" in form.changed_data:
                Tag.objects.filter(pk=obj.pk).update(is_adult=obj.is_adult)
        else:
            super().save_model(request, obj, form, change)
        if "is_adult" in form.changed_data:
            # Both ways: unflagging clears the sources only this tag made adult.
            refresh_adult_for_tags([obj.pk])

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # changeform_view runs in a transaction, so a MergeError raised while saving
        # rolls the whole change back; report it instead of returning a 500.
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except MergeError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return HttpResponseRedirect(request.path)

    def delete_model(self, request, obj):
        self._delete_tags([obj.pk])

    def delete_queryset(self, request, queryset):
        self._delete_tags(list(queryset.values_list("pk", flat=True)))

    def _delete_tags(self, pks):
        """Delete tags. Their sources lose the link (a cascade that bypasses the sources), so their adult
        flags, and the novels of those sources, are re-derived in the same transaction."""
        with transaction.atomic():
            source_pks = list(
                NovelFromSource.tags.through.objects.filter(tag_id__in=pks)
                .values_list("novelfromsource_id", flat=True).distinct()
            )
            Tag.objects.filter(pk__in=pks).delete()
            refresh_adult(NovelFromSource.objects.filter(pk__in=source_pks))

    def _set_r18(self, request, queryset, is_adult):
        pks = list(queryset.values_list("pk", flat=True))
        with transaction.atomic():
            Tag.objects.filter(pk__in=pks).update(is_adult=is_adult)
            flagged, cleared = refresh_adult_for_tags(pks)
        if is_adult:
            message = f"Marked {len(pks)} tag(s) as R18; {flagged} novel source(s) flagged adult."
        else:
            message = (
                f"Unmarked {len(pks)} tag(s); {cleared} novel source(s) no longer adult "
                "(sources adult on their own or through another R18 tag stay adult)."
            )
        self.message_user(request, message, messages.SUCCESS)

    @admin.action(description="Mark selected tags as R18")
    def mark_r18(self, request, queryset):
        self._set_r18(request, queryset, is_adult=True)

    @admin.action(description="Unmark selected tags as R18")
    def unmark_r18(self, request, queryset):
        self._set_r18(request, queryset, is_adult=False)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(source_count=Count("novels"))

    def source_count(self, obj):
        return obj.source_count

    source_count.short_description = "Novel From Source Count"
    source_count.admin_order_field = "source_count"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_change_permission(request):
            extra_context["merge_button"] = {
                "url": reverse("admin:lncrawler_api_tag_merge"),
                "label": "Merge tags",
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
    search_fields = ("title", "novel__canonical_source__title", "external_source__source_name")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "chapters_count",
        "available_chapters_count",
        "first_available_chapter",
        "latest_available_chapter",
        "link_to_novel",
        "upvotes",
        "downvotes",
        "vote_score",
        "view_chapters_link",
        # Derived from adult_from_source and the R18 tags (refresh_adult).
        "is_adult",
    )
    raw_id_fields = ("novel",)
    autocomplete_fields = ("external_source", "authors", "editors", "translators", "tags")
    inlines = [SourceVoteInline]  # Removed ChapterInline
    paginator = CappedCountPaginator
    list_select_related = ("external_source", "novel")
    show_full_result_count = False

    def save_model(self, request, obj, form, change):
        # The novel field is editable: the novel the source leaves must be refreshed too.
        previous_novel_id = (
            NovelFromSource.objects.filter(pk=obj.pk).values_list("novel_id", flat=True).first()
            if change else None
        )
        super().save_model(request, obj, form, change)
        # adult_from_source may have changed: re-derive the effective flag, and its novels.
        refresh_adult(NovelFromSource.objects.filter(pk=obj.pk))
        if previous_novel_id is not None:
            refresh_novel_adult([previous_novel_id])
        # The full save wrote the chapter stats this form loaded back to the row: refresh them.
        refresh_chapter_stats([obj.pk])

    def link_to_novel(self, obj):
        url = reverse("admin:lncrawler_api_novel_change", args=[obj.novel.id])
        return format_html('<a href="{}">{}</a>', url, obj.novel)

    link_to_novel.short_description = "Novel"

    def vote_score_display(self, obj):
        return obj.vote_score

    vote_score_display.short_description = "Vote Score"

    def delete_model(self, request, obj):
        self._delete_source(obj)

    def delete_queryset(self, request, queryset):
        """
        Override the default delete_queryset method to call delete() on each object
        This ensures the model's delete method runs for bulk deletions from the list page.
        A busy novel is skipped with a message; the others are still deleted.
        """
        for obj in queryset:
            try:
                self._delete_source(obj)
            except FolderBusy:
                messages.error(request, BUSY_MESSAGE)
            except FileOperationError as exc:
                messages.error(request, str(exc))

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except FolderBusy:
            messages.error(request, BUSY_MESSAGE)
            return HttpResponseRedirect(reverse("admin:lncrawler_api_novelfromsource_changelist"))
        except FileOperationError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("admin:lncrawler_api_novelfromsource_changelist"))

    def _delete_source(self, obj):
        """Delete one source, then re-derive its novel: the source may have been the majority's.

        When it was the novel's last source, the novel is deleted too. ``FolderBusy`` propagates
        (nothing is deleted) when the novel is busy; a failed folder rename is undone with the rows.
        """
        novel_id = obj.novel_id
        with file_journal() as files, transaction.atomic():
            obj.delete(files=files)
            refresh_novel_adult([novel_id])
            after_source_deleted(novel_id, files=files)

    def view_chapters_link(self, obj):
        if obj.pk:
            url = f"/admin/lncrawler_api/chapter/?novel_from_source__id__exact={obj.pk}"
            return format_html('<a href="{}" target="_blank">View Chapters ({})</a>', url, obj.chapters_count)
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

    # Deleting a site deletes its sources (CASCADE), in whichever novels they are: refresh those novels.
    def delete_model(self, request, obj):
        self._delete_with_sources(obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            try:
                self._delete_with_sources(obj)
            except FolderBusy:
                messages.error(request, BUSY_MESSAGE)
            except FileOperationError as exc:
                messages.error(request, str(exc))

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except FolderBusy:
            messages.error(request, BUSY_MESSAGE)
            return HttpResponseRedirect(reverse("admin:lncrawler_api_externalsource_changelist"))
        except FileOperationError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("admin:lncrawler_api_externalsource_changelist"))

    def _delete_with_sources(self, obj):
        """Delete the site's sources one by one, then the site.

        Each source goes through ``NovelFromSource.delete()`` (its folder is renamed aside and removed
        on commit), and a novel left without sources is deleted with it. When one novel is busy
        (``FolderBusy``), the whole site is rolled back: the sources already deleted come back.
        """
        with file_journal() as files, transaction.atomic():
            novel_ids = list(obj.novels.values_list("novel_id", flat=True).distinct())
            for source in obj.novels.order_by("pk"):
                novel_id = source.novel_id
                source.delete(files=files)
                after_source_deleted(novel_id, files=files)
            obj.delete()
            refresh_novel_adult(novel_ids)