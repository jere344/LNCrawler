import json
from urllib.parse import quote

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from ..models import (
    Audiobook,
    AudiobookChapter,
    AudiobookDailyStat,
    AudiobookPart,
    AudiobookWorker,
    ListeningProgress,
)
from ..services import audiobook_cover
from ..services.audiobook_worker_auth import WORKER_GROUP, ensure_worker_token

MB = 1024 * 1024

# New worker tokens travel from the request that makes them to the page that shows them, in the session:
# never in a message (the messages cookie is not encrypted) nor in a URL. The token page pops them on its
# first GET, so a reload shows nothing and rotates nothing.
WORKER_TOKENS_SESSION_KEY = "audiobook_worker_tokens_once"


def _store_worker_tokens(request, tokens):
    """Queue {username: token} for the next GET of the token page."""
    pending = request.session.get(WORKER_TOKENS_SESSION_KEY, {})
    pending.update(tokens)
    request.session[WORKER_TOKENS_SESSION_KEY] = pending


def _json_text(value):
    """JSON of an unexpected QA value, escaped so it shows as text."""
    return format_html('<pre>{}</pre>', json.dumps(value, indent=2, ensure_ascii=False, default=str))


class AudiobookPartInline(admin.TabularInline):
    model = AudiobookPart
    extra = 0
    can_delete = False
    fields = ('index', 'chapter_start', 'chapter_end', 'word_count', 'status', 'engine', 'duration', 'part_link')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def duration(self, obj):
        return f"{obj.duration_s / 60:.1f} min"
    duration.short_description = 'Duration'

    def part_link(self, obj):
        return format_html('<a href="{}">Open</a>', reverse('admin:lncrawler_api_audiobookpart_change', args=[obj.pk]))
    part_link.short_description = 'Part'


@admin.register(Audiobook)
class AudiobookAdmin(admin.ModelAdmin):
    list_display = (
        'cover_thumb',
        'novel',
        'source',
        'status',
        'hours',
        'size_mb',
        'worker_id',
        'last_part_at',
    )
    list_filter = ('status',)
    search_fields = ('novel__canonical_source__title', 'source__title')
    raw_id_fields = ('novel', 'source')
    readonly_fields = (
        'cover_thumb',
        'credits',
        'total_duration_s',
        'total_size_bytes',
        'parts_done',
        'first_published_at',
        'last_part_at',
        'created_at',
        'updated_at',
    )
    inlines = [AudiobookPartInline]
    actions = ['unpin_worker']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('novel', 'source__external_source', 'source__novel')

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None:
            fields = (*fields, 'novel', 'source')
        return fields

    def hours(self, obj):
        return f"{obj.total_duration_s / 3600:.1f}"
    hours.short_description = 'Hours'

    def size_mb(self, obj):
        return f"{obj.total_size_bytes / MB:.1f}"
    size_mb.short_description = 'Size (MB)'

    def cover_thumb(self, obj):
        if not obj.cover_path:
            return "-"
        path = quote(audiobook_cover.thumb_path(obj), safe='/')
        return format_html('<img src="/lightnovels/{}" width="80" height="80" alt="">', path)
    cover_thumb.short_description = 'Cover'

    @admin.action(description="Unpin worker (its claimed parts go back to the queue, any worker may claim them)")
    def unpin_worker(self, request, queryset):
        # The recovery path for a dead worker: its claimed parts are queued again, and the next claim of any worker takes them
        with transaction.atomic():
            audiobook_ids = list(queryset.values_list('pk', flat=True))
            requeued = AudiobookPart.objects.filter(audiobook_id__in=audiobook_ids, status='claimed').update(
                status='queued', worker_id='', claimed_at=None, progress=0, stage='',
            )
            unpinned = queryset.update(worker_id='')
        self.message_user(request, f"{unpinned} audiobook(s) unpinned, {requeued} claimed part(s) queued again.")


class AudiobookChapterInline(admin.TabularInline):
    model = AudiobookChapter
    extra = 0
    can_delete = False
    fields = ('chapter_number', 'chapter_title', 'duration', 'size', 'preview')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('chapter', 'part__audiobook__source__novel')

    def chapter_number(self, obj):
        return obj.chapter.chapter_id
    chapter_number.short_description = 'Chapter'

    def chapter_title(self, obj):
        return obj.chapter.display_title
    chapter_title.short_description = 'Title'

    def duration(self, obj):
        return f"{obj.duration_s / 60:.1f} min"
    duration.short_description = 'Duration'

    def size(self, obj):
        return f"{obj.size_bytes / MB:.1f} MB"
    size.short_description = 'Size'

    def preview(self, obj):
        return format_html('<audio controls preload="none" src="/lightnovels/{}"></audio>', obj.file_path)
    preview.short_description = 'Preview'


@admin.register(AudiobookPart)
class AudiobookPartAdmin(admin.ModelAdmin):
    list_display = (
        'audiobook',
        'index',
        'chapter_range',
        'word_count',
        'status',
        'priority',
        'engine',
        'qa_passed',
        'attempts',
        'worker_id',
        'progress_percent',
        'completed_at',
    )
    list_filter = ('status', 'engine', 'qa_passed')
    search_fields = ('audiobook__novel__canonical_source__title', 'audiobook__source__title', 'engine_version')
    list_select_related = ('audiobook__novel', 'audiobook__source')
    readonly_fields = (
        'audiobook',
        'index',
        'chapter_start',
        'chapter_end',
        'word_count',
        'estimated_duration_s',
        'status',
        'engine',
        'engine_version',
        'worker_id',
        'claimed_at',
        'progress',
        'stage',
        'attempts',
        'error_message',
        'content_hash',
        'qa',
        'qa_passed',
        'qa_table',
        'duration_s',
        'size_bytes',
        'created_at',
        'completed_at',
    )
    inlines = [AudiobookChapterInline]

    def chapter_range(self, obj):
        return f"{obj.chapter_start} - {obj.chapter_end}"
    chapter_range.short_description = 'Chapters'

    def progress_percent(self, obj):
        return f"{obj.progress * 100:.0f}%"
    progress_percent.short_description = 'Progress'

    def qa_table(self, obj):
        qa = obj.qa if isinstance(obj.qa, dict) else {}
        checks = qa.get('checks', {})
        if not checks:
            return "-"
        if not isinstance(checks, dict):
            return _json_text(checks)
        rows = format_html_join(
            '',
            '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>',
            (
                (name, check.get('value'), check.get('threshold'), 'yes' if check.get('passed') else 'no')
                if isinstance(check, dict)
                else (name, _json_text(check), '', '')
                for name, check in checks.items()
            ),
        )
        return format_html(
            '<table><tr><th>Check</th><th>Value</th><th>Threshold</th><th>Passed</th></tr>{}</table>',
            rows,
        )
    qa_table.short_description = 'QA checks'


class WorkerTokenForm(forms.Form):
    username = forms.CharField(max_length=150, label="Username")
    rotate = forms.BooleanField(
        required=False, label="Rotate the token if the worker already exists",
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        # This page must not take over a human's account: an existing user must already be a worker.
        existing = get_user_model().objects.filter(username=username).first()
        if existing is not None and not existing.groups.filter(name=WORKER_GROUP).exists():
            raise ValidationError("This username belongs to an account that is not a worker. Choose another name.")
        return username


@admin.register(AudiobookWorker)
class AudiobookWorkerAdmin(admin.ModelAdmin):
    list_display = ('worker_id', 'user', 'online', 'last_seen_at', 'version', 'available')
    list_select_related = ('user',)
    readonly_fields = ('worker_id', 'user', 'last_seen_at', 'version', 'available', 'message')
    actions = ['rotate_token']
    change_list_template = "admin/lncrawler_api/audiobookworker/change_list.html"

    def online(self, obj):
        return obj.is_online
    online.boolean = True

    def get_urls(self):
        # Inserted before the defaults so "token/" is not swallowed by the "<path:object_id>/" change view.
        custom = [
            path(
                "token/",
                self.admin_site.admin_view(self.token_view),
                name="lncrawler_api_audiobookworker_token",
            ),
        ]
        return custom + super().get_urls()

    def token_view(self, request):
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "New worker token",
            "opts": self.model._meta,
        }
        if request.method == "POST":
            form = WorkerTokenForm(request.POST)
            if form.is_valid():
                username = form.cleaned_data["username"]
                rotate = form.cleaned_data["rotate"]
                exists = get_user_model().objects.filter(username=username).exists()
                if exists and not self.has_change_permission(request):
                    raise PermissionDenied
                if not exists and not self.has_add_permission(request):
                    raise PermissionDenied
                key, created = ensure_worker_token(username, rotate=rotate)
                # Post/redirect/get: a reload of the result must not post again, so it does not rotate twice.
                if created:
                    _store_worker_tokens(request, {username: key})
                else:
                    messages.info(
                        request,
                        f"Worker {username} already exists, token unchanged (tick rotate to get a new one).",
                    )
                return redirect(reverse("admin:lncrawler_api_audiobookworker_token"))
        else:
            form = WorkerTokenForm()
            # Shown once: popped here, so the next GET has nothing to show.
            context["tokens"] = request.session.pop(WORKER_TOKENS_SESSION_KEY, {})
        context["form"] = form
        return render(request, "admin/lncrawler_api/audiobookworker/token.html", context)

    @admin.action(description="Rotate token of the selected workers' accounts")
    def rotate_token(self, request, queryset):
        if not self.has_change_permission(request):
            raise PermissionDenied
        # The tokens go to the session, not to a message: the token page shows them once.
        tokens = {}
        for worker in queryset.select_related('user'):
            if worker.user is None:
                continue
            key, _ = ensure_worker_token(worker.user.username, rotate=True)
            tokens[worker.user.username] = key
        if not tokens:
            self.message_user(request, "No selected worker has an account to rotate.", messages.WARNING)
            return None
        _store_worker_tokens(request, tokens)
        self.message_user(request, f"Rotated {len(tokens)} token(s).")
        return redirect(reverse("admin:lncrawler_api_audiobookworker_token"))


@admin.register(ListeningProgress)
class ListeningProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'audiobook', 'chapter', 'position_s', 'speed', 'finished', 'updated_at')
    list_filter = ('finished',)
    list_select_related = ('user', 'audiobook__novel', 'audiobook__source', 'chapter__novel_from_source')
    search_fields = ('user__username', 'audiobook__novel__canonical_source__title', 'audiobook__source__title')
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False


@admin.register(AudiobookDailyStat)
class AudiobookDailyStatAdmin(admin.ModelAdmin):
    list_display = ('audiobook', 'date', 'plays', 'downloads', 'listen_seconds')
    list_filter = ('date',)
    list_select_related = ('audiobook__novel', 'audiobook__source')
    search_fields = ('audiobook__novel__canonical_source__title', 'audiobook__source__title')
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False
