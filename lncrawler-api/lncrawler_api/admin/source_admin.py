from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
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
from ..services.author_block_service import block_authors, unblock_authors
from ..services.author_merge_service import merge_authors, pick_target
from ..services.merge_service import MergeError, merge_tags, rename_tag
from ..utils.tag_utils import normalize_tag
from django.utils.html import format_html
from .perf import CappedCountPaginator


# ``Tag`` has no FK to itself, so borrow the FK-to-Tag field from ``TagAlias``
# to power an autocomplete widget for picking tags.
TAG_AUTOCOMPLETE_FIELD = TagAlias._meta.get_field("tag")


# Register all novel-related models
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "is_blocked")
    list_filter = ("is_blocked",)
    search_fields = ("name",)
    actions = ["merge_into_most_used", "block_selected", "unblock_selected"]

    def get_queryset(self, request):
        # Blocked authors stay listed here, so they can be unblocked.
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def has_delete_permission(self, request, obj=None):
        # Blocking replaces deletion: a real delete lets the next import recreate the author.
        return False

    @admin.action(description="Block selected authors")
    def block_selected(self, request, queryset):
        count = block_authors(list(queryset.values_list("pk", flat=True)))
        self.message_user(
            request,
            f"Blocked {count} author(s): they were removed from their sources, which are kept.",
            messages.SUCCESS,
        )

    @admin.action(description="Unblock selected authors")
    def unblock_selected(self, request, queryset):
        count = unblock_authors(list(queryset.values_list("pk", flat=True)))
        self.message_user(
            request,
            f"Unblocked {count} author(s). Their source links come back on re-import.",
            messages.SUCCESS,
        )

    @admin.action(description="Merge selected into the most-used author")
    def merge_into_most_used(self, request, queryset):
        authors = list(queryset.order_by("pk"))
        if len(authors) < 2:
            self.message_user(request, "Select at least two authors.", messages.WARNING)
            return
        target = authors[0]
        for other in authors[1:]:
            target = pick_target(target, other)
        merged = 0
        for source in authors:
            if source.pk == target.pk:
                continue
            try:
                merge_authors(source, target)
            except MergeError as exc:
                self.message_user(request, f"'{source.name}': {exc}", messages.ERROR)
            else:
                merged += 1
        self.message_user(
            request, f"Merged {merged} author(s) into '{target.name}'.", messages.SUCCESS
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
    search_fields = ("title", "novel__title", "external_source__source_name")
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
        return format_html('<a href="{}">{}</a>', url, obj.novel.title)

    link_to_novel.short_description = "Novel"

    def vote_score_display(self, obj):
        return obj.vote_score

    vote_score_display.short_description = "Vote Score"

    def delete_model(self, request, obj):
        self._delete_source(obj)

    def delete_queryset(self, request, queryset):
        """
        Override the default delete_queryset method to call delete() on each object
        This ensures the model's delete method runs for bulk deletions from the list page
        """
        for obj in queryset:
            self._delete_source(obj)

    def _delete_source(self, obj):
        """Delete one source, then re-derive its novel: the source may have been the majority's."""
        novel_id = obj.novel_id
        with transaction.atomic():
            obj.delete()
            refresh_novel_adult([novel_id])

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
            self._delete_with_sources(obj)

    def _delete_with_sources(self, obj):
        with transaction.atomic():
            novel_ids = list(obj.novels.values_list("novel_id", flat=True).distinct())
            obj.delete()
            refresh_novel_adult(novel_ids)