from ..models import (
    Novel,
    NovelAlias,
    NovelFromSource,
    NovelRating,
    WeeklySourceView,
    FeaturedNovel,
    NovelSimilarity,
    Comment,
    Review,
)
from ..services.merge_service import MergeError, build_merge_plan, merge_novels
from ..services.split_service import (
    SplitError,
    build_split_plan,
    move_sources as move_sources_into_novel,
    split_novel,
)
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils.text import slugify
from django.urls import path, reverse


# ``Novel`` has no self-referencing FK, so borrow the FK-to-Novel field from
# ``NovelSimilarity`` to build a working autocomplete widget anywhere we need to
# pick a Novel in a custom form.
NOVEL_AUTOCOMPLETE_FIELD = NovelSimilarity._meta.get_field("from_novel")


# Inline for showing sources in Novel admin
class NovelFromSourceInline(admin.TabularInline):
    model = NovelFromSource
    extra = 0
    fields = (
        "link_to_source",
        "source_name",
        "status",
        "chapters_count",
        "last_chapter_update",
    )
    readonly_fields = ("link_to_source", "source_name", "chapters_count", "last_chapter_update")
    show_change_link = True
    can_delete = False

    def link_to_source(self, obj):
        url = reverse("admin:lncrawler_api_novelfromsource_change", args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.title)

    link_to_source.short_description = "Title"

    def source_name(self, obj):
        return obj.external_source.source_name

    source_name.short_description = "Source"


# Inline for showing comments in Novel admin
class NovelCommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("author_name", "message_preview", "contains_spoiler", "created_at", "vote_score")
    readonly_fields = ("created_at", "vote_score", "message_preview")
    can_delete = True
    max_num = 50  # Limit displayed comments
    ordering = ("-created_at",)

    def message_preview(self, obj):
        preview = obj.message[:30] + "..." if len(obj.message) > 30 else obj.message
        return preview
    message_preview.short_description = "Message"

    def vote_score(self, obj):
        return obj.vote_score
    vote_score.short_description = "Vote Score"


# Inline for showing reviews in Novel admin
class NovelReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    fields = ("user", "content_preview", "created_at", "get_reaction_count")
    readonly_fields = ("content_preview","created_at", "get_reaction_count")
    can_delete = True
    max_num = 20  # Limit displayed reviews
    ordering = ("-created_at",)

    def content_preview(self, obj):
        preview = obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
        return preview
    content_preview.short_description = "Content"


class MergeNovelForm(forms.Form):
    """Pick the duplicate novel and the canonical one to merge it into."""

    source_novel = forms.ModelChoiceField(
        queryset=Novel.objects.all(),
        label="Duplicate novel (deleted after merge)",
        widget=AutocompleteSelect(NOVEL_AUTOCOMPLETE_FIELD, admin.site),
    )
    target_novel = forms.ModelChoiceField(
        queryset=Novel.objects.all(),
        label="Canonical novel (kept)",
        widget=AutocompleteSelect(NOVEL_AUTOCOMPLETE_FIELD, admin.site),
    )
    move_files = forms.BooleanField(
        required=False,
        initial=True,
        label="Move source folders and record a redirect",
        help_text=(
            "Relocate the duplicate's files under the canonical novel and remember "
            "the old name so future crawls attach to the canonical novel."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source_novel")
        target = cleaned.get("target_novel")
        if source and target and source.pk == target.pk:
            raise forms.ValidationError("A novel cannot be merged into itself.")
        return cleaned


class NovelChoiceForm(forms.Form):
    """Step 1 of the split page: pick which novel to split."""

    novel = forms.ModelChoiceField(
        queryset=Novel.objects.all(),
        label="Novel to split",
        widget=AutocompleteSelect(NOVEL_AUTOCOMPLETE_FIELD, admin.site),
    )


class SplitNovelForm(forms.Form):
    """Step 2: choose the sources to move and where they go."""

    MODE_NEW = "new"
    MODE_EXISTING = "existing"

    sources = forms.ModelMultipleChoiceField(
        queryset=NovelFromSource.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Sources to move",
    )
    mode = forms.ChoiceField(
        choices=(
            (MODE_NEW, "Move into a new novel"),
            (MODE_EXISTING, "Move into an existing novel"),
        ),
        initial=MODE_NEW,
        widget=forms.RadioSelect,
        label="Destination",
    )
    new_title = forms.CharField(
        max_length=255,
        required=False,
        label="New novel title",
    )
    new_slug = forms.SlugField(
        max_length=255,
        required=False,
        label="New novel slug",
        help_text=(
            "Defaults to the title. The slug becomes the permanent folder and "
            "identity of the new novel."
        ),
    )
    target_novel = forms.ModelChoiceField(
        queryset=Novel.objects.all(),
        required=False,
        label="Existing novel",
        widget=AutocompleteSelect(NOVEL_AUTOCOMPLETE_FIELD, admin.site),
    )
    rename_title = forms.CharField(
        max_length=255,
        required=False,
        label="Rename the original novel (optional)",
        help_text="For example append '[Web Novel]'.",
    )

    def __init__(self, *args, novel=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.novel = novel
        if novel is not None:
            self.fields["sources"].queryset = novel.sources.all()

    def clean(self):
        cleaned = super().clean()
        sources = cleaned.get("sources")
        mode = cleaned.get("mode")

        if source_error := self._clean_sources(sources):
            raise forms.ValidationError(source_error)

        if mode == self.MODE_NEW:
            error = self._clean_new_novel(cleaned)
        else:
            error = self._clean_existing_target(cleaned)
        if error:
            raise forms.ValidationError(error)

        return cleaned

    def _clean_sources(self, sources):
        if not sources:
            return "Select at least one source to move."
        if self.novel is not None and len(sources) >= self.novel.sources.count():
            return "Leave at least one source on the original novel."
        return None

    def _clean_new_novel(self, cleaned):
        title = (cleaned.get("new_title") or "").strip()
        slug = slugify((cleaned.get("new_slug") or "").strip() or title)
        if not slug:
            return "Give the new novel a title or a slug that can form one."
        if self.novel is not None and slug == self.novel.slug:
            return "The new slug must differ from the original novel's slug."
        if Novel.objects.filter(slug=slug).exists():
            return f"A novel with slug '{slug}' already exists."
        cleaned["new_slug"] = slug
        return None

    def _clean_existing_target(self, cleaned):
        target = cleaned.get("target_novel")
        if target is None:
            return "Choose the existing novel to move the sources into."
        if self.novel is not None and target.pk == self.novel.pk:
            return "Choose a different target novel."
        return None


@admin.register(Novel)
class NovelAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "sources_count",
        "comment_count",
        "view_count_display",
        "created_at",
        "updated_at",
    )
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "sources_count",
        "view_count_display",
        "comment_count",
    )
    inlines = [NovelFromSourceInline, NovelCommentInline, NovelReviewInline]
    change_list_template = "admin/lncrawler_api/novel/change_list.html"
    change_form_template = "admin/lncrawler_api/novel/change_form.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_change_permission(request):
            extra_context["merge_button"] = {
                "url": reverse("admin:lncrawler_api_novel_merge"),
                "label": "Merge novels",
            }
            extra_context["split_button"] = {
                "url": reverse("admin:lncrawler_api_novel_split"),
                "label": "Split novel",
            }
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Inserted before the defaults so the "merge/"/"split/" paths are not
        # swallowed by the "<path:object_id>/" change view.
        custom = [
            path(
                "merge/",
                self.admin_site.admin_view(self.merge_view),
                name="lncrawler_api_novel_merge",
            ),
            path(
                "split/",
                self.admin_site.admin_view(self.split_view),
                name="lncrawler_api_novel_split",
            ),
        ]
        return custom + super().get_urls()

    def merge_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Merge novels",
            "opts": self.model._meta,
        }

        if request.method == "POST":
            form = MergeNovelForm(request.POST)
            if form.is_valid():
                source = form.cleaned_data["source_novel"]
                target = form.cleaned_data["target_novel"]
                move_files = form.cleaned_data["move_files"]

                if "confirm" in request.POST:
                    try:
                        merge_novels(source, target, move_files=move_files)
                    except MergeError as e:
                        messages.error(request, str(e))
                    else:
                        messages.success(
                            request,
                            f"Merged '{source.title}' into '{target.title}'.",
                        )
                        return redirect(
                            reverse(
                                "admin:lncrawler_api_novel_change", args=[target.pk]
                            )
                        )
                else:
                    context["plan"] = build_merge_plan(source, target, move_files)
                    context["preview"] = True
        else:
            form = MergeNovelForm()

        context["form"] = form
        return render(request, "admin/lncrawler_api/novel/merge.html", context)

    def split_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Split novel",
            "opts": self.model._meta,
        }
        novel_id = request.POST.get("novel") or request.GET.get("novel")

        if request.method == "POST" and "choose" in request.POST:
            choose_form = NovelChoiceForm(request.POST)
            if choose_form.is_valid():
                url = reverse("admin:lncrawler_api_novel_split")
                return redirect(f"{url}?novel={choose_form.cleaned_data['novel'].pk}")
            context["choose_form"] = choose_form
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        if not novel_id:
            context["choose_form"] = NovelChoiceForm()
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        try:
            novel = Novel.objects.get(pk=novel_id)
        except (Novel.DoesNotExist, ValidationError, ValueError):
            messages.error(request, "That novel could not be found.")
            context["choose_form"] = NovelChoiceForm()
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        context["novel"] = novel

        if request.method != "POST":
            context["form"] = SplitNovelForm(novel=novel)
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        form = SplitNovelForm(request.POST, novel=novel)
        if not form.is_valid():
            context["form"] = form
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        sources = list(form.cleaned_data["sources"])
        mode = form.cleaned_data["mode"]
        rename_title = form.cleaned_data.get("rename_title") or ""
        target = (
            form.cleaned_data.get("target_novel")
            if mode == SplitNovelForm.MODE_EXISTING
            else None
        )

        if "confirm" not in request.POST:
            try:
                context["plan"] = build_split_plan(
                    novel,
                    sources,
                    new_title=form.cleaned_data.get("new_title", ""),
                    new_slug=form.cleaned_data.get("new_slug", ""),
                    rename_title=rename_title,
                    target_novel=target,
                )
            except SplitError as e:
                messages.error(request, str(e))
            else:
                context["preview"] = True
            context["form"] = form
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        try:
            if mode == SplitNovelForm.MODE_NEW:
                destination = split_novel(
                    novel,
                    sources,
                    new_title=form.cleaned_data.get("new_title", ""),
                    new_slug=form.cleaned_data.get("new_slug", ""),
                    rename_title=rename_title,
                )
                message = f"Split {len(sources)} source(s) into '{destination.title}'."
            else:
                destination = move_sources_into_novel(novel, sources, target)
                message = f"Moved {len(sources)} source(s) into '{destination.title}'."
        except SplitError as e:
            messages.error(request, str(e))
            context["form"] = form
            return render(request, "admin/lncrawler_api/novel/split.html", context)

        messages.success(request, message)
        return redirect(
            reverse("admin:lncrawler_api_novel_change", args=[destination.pk])
        )

    def view_count_display(self, obj):
        return obj.sources.aggregate(total=Sum('total_views'))['total'] or 0

    view_count_display.short_description = "Views"


@admin.register(NovelRating)
class NovelRatingAdmin(admin.ModelAdmin):
    list_display = ("novel", "ip_address", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("novel__title", "ip_address")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("novel",)


@admin.register(WeeklySourceView)
class WeeklySourceViewAdmin(admin.ModelAdmin):
    list_display = ("source", "granularity", "day", "views")
    list_filter = ("granularity", "day")
    search_fields = ("source__title", "source__novel__title", "day")
    raw_id_fields = ("source",)


@admin.register(FeaturedNovel)
class FeaturedNovelAdmin(admin.ModelAdmin):
    list_display = ("novel", "description_preview", "created_at", "updated_at")
    search_fields = ("novel__title", "description")
    raw_id_fields = ("novel",)

    def description_preview(self, obj):
        preview = obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return preview

    description_preview.short_description = "Description"


@admin.register(NovelSimilarity)
class NovelSimilarityAdmin(admin.ModelAdmin):
    list_display = ("from_novel", "to_novel", "similarity")
    search_fields = ("from_novel__title", "to_novel__title")
    raw_id_fields = ("from_novel", "to_novel")
    readonly_fields = ("similarity",)
    fieldsets = (
        (
            "Similarity Information",
            {"fields": ("from_novel", "to_novel", "similarity")},
        ),
    )


@admin.register(NovelAlias)
class NovelAliasAdmin(admin.ModelAdmin):
    list_display = ("slug", "novel", "created_at")
    search_fields = ("slug", "novel__title", "novel__slug")
    readonly_fields = ("created_at",)
    raw_id_fields = ("novel",)
