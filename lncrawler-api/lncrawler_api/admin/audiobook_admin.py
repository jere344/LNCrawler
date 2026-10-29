import json
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from ..models import (
    Audiobook,
    AudiobookChapter,
    AudiobookDailyStat,
    AudiobookPart,
    AudiobookWorker,
    Job,
    ListeningProgress,
    ScheduledTask,
)
from ..services import audiobook_cover, audiobook_m4b, audiobook_media, audiobook_service

MB = 1024 * 1024
GB = 1024 * MB


def _dashboard_context(request):
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    done_week = AudiobookPart.objects.filter(status='done', completed_at__gte=week_ago)

    queue_counts = {
        row['status']: row['n']
        for row in AudiobookPart.objects.values('status').annotate(n=Count('id'))
    }
    queued_words = AudiobookPart.objects.filter(status='queued').aggregate(words=Sum('word_count'))['words'] or 0
    budget_queued_words = AudiobookPart.objects.filter(
        status__in=['queued', 'claimed'],
    ).aggregate(words=Sum('word_count'))['words'] or 0
    words_week = done_week.aggregate(words=Sum('word_count'))['words'] or 0
    est_nights = round(queued_words / (words_week / 7), 1) if words_week else None

    per_day = [
        {
            'day': row['day'],
            'parts': row['parts'],
            'hours': (row['hours'] or 0) / 3600,
            'words': row['words'] or 0,
        }
        for row in done_week
        .annotate(day=TruncDate('completed_at'))
        .values('day')
        .annotate(parts=Count('id'), hours=Sum('duration_s'), words=Sum('word_count'))
        .order_by('day')
    ]

    used = audiobook_service.audio_disk_usage_bytes()
    budget = settings.AUDIOBOOK_DISK_BUDGET_GB * GB
    stats = AudiobookDailyStat.objects.filter(date__gte=(now - timedelta(days=30)).date()).aggregate(
        plays=Sum('plays'),
        downloads=Sum('downloads'),
    )

    return {
        **admin.site.each_context(request),
        'title': 'Audiobooks dashboard',
        'enabled': settings.AUDIOBOOK_ENABLED,
        'workers': AudiobookWorker.objects.order_by('-last_seen_at'),
        'queue': [(status, label, queue_counts.get(status, 0)) for status, label in AudiobookPart.STATUS_CHOICES],
        'queued_words': queued_words,
        'budget_queued_words': budget_queued_words,
        'queue_target_words': settings.AUDIOBOOK_QUEUE_WORDS,
        'started_books': Audiobook.objects.filter(status='active', parts__isnull=False).distinct().count(),
        'scheduled_tasks': ScheduledTask.objects.filter(
            name__in=['enqueue_audiobooks', 'reap_audiobook_leases', 'audiobook_housekeeping'],
        ).order_by('name'),
        'est_nights': est_nights,
        'per_day': per_day,
        'failed_parts': AudiobookPart.objects.filter(status='failed').select_related('audiobook__novel').order_by(
            F('claimed_at').desc(nulls_last=True), '-created_at'
        )[:10],
        'disk_used_gb': used / GB,
        'disk_budget_gb': settings.AUDIOBOOK_DISK_BUDGET_GB,
        'disk_percent': used / budget * 100 if budget else 0,
        'plays_30d': stats['plays'] or 0,
        'downloads_30d': stats['downloads'] or 0,
        'm4b_cache_gb': audiobook_m4b.m4b_cache_bytes() / GB,
        'm4b_cap_gb': settings.AUDIOBOOK_M4B_CACHE_GB,
    }


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
        'published',
        'featured',
        'parts_summary',
        'hours',
        'size_mb',
        'worker_id',
        'last_part_at',
    )
    list_filter = ('status', 'published', 'featured')
    search_fields = ('novel__title',)
    raw_id_fields = ('novel', 'source')
    readonly_fields = (
        'cover_thumb',
        'cast',
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
    change_list_template = "admin/lncrawler_api/audiobook/change_list.html"
    actions = [
        'publish',
        'unpublish',
        'feature',
        'unfeature',
        'pause',
        'resume',
        'enqueue_next',
        'enqueue_tail',
        'delete_audio_files',
        'unpin_worker',
        'rebuild_cover',
        'retag_files',
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('novel', 'source__external_source').annotate(
            done_count=Count('parts', filter=Q(parts__status='done')),
            queued_count=Count('parts', filter=Q(parts__status='queued')),
            failed_count=Count('parts', filter=Q(parts__status='failed')),
        )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None:
            fields = (*fields, 'novel', 'source')
        return fields

    def parts_summary(self, obj):
        return f"{obj.done_count} / {obj.queued_count} / {obj.failed_count}"
    parts_summary.short_description = 'Parts done / queued / failed'

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

    @admin.action(description="Rebuild the cover of selected audiobooks")
    def rebuild_cover(self, request, queryset):
        built = 0
        for audiobook in queryset.select_related('novel', 'source'):
            try:
                audiobook_cover.build_cover(audiobook)
                built += 1
            except Exception as exc:
                self.message_user(request, f"{audiobook}: cover not built ({exc}).", level=messages.ERROR)
        self.message_user(request, f"{built} cover(s) rebuilt.")

    @admin.action(description="Retag the files of selected audiobooks")
    def retag_files(self, request, queryset):
        files = 0
        for audiobook in queryset.select_related('novel', 'source'):
            try:
                files += audiobook_media.retag_audiobook(audiobook)
            except Exception as exc:
                self.message_user(request, f"{audiobook}: files not retagged ({exc}).", level=messages.ERROR)
        self.message_user(request, f"{files} file(s) retagged.")

    @admin.action(description="Publish selected audiobooks")
    def publish(self, request, queryset):
        now = timezone.now()
        queryset.filter(first_published_at__isnull=True).update(first_published_at=now)
        updated = queryset.update(published=True)
        self.message_user(request, f"{updated} audiobook(s) published.")

    @admin.action(description="Unpublish selected audiobooks")
    def unpublish(self, request, queryset):
        updated = queryset.update(published=False)
        self.message_user(request, f"{updated} audiobook(s) unpublished.")

    @admin.action(description="Feature selected audiobooks")
    def feature(self, request, queryset):
        updated = queryset.update(featured=True)
        self.message_user(request, f"{updated} audiobook(s) featured.")

    @admin.action(description="Unfeature selected audiobooks")
    def unfeature(self, request, queryset):
        updated = queryset.update(featured=False)
        self.message_user(request, f"{updated} audiobook(s) unfeatured.")

    @admin.action(description="Pause selected audiobooks")
    def pause(self, request, queryset):
        updated = queryset.update(status='paused')
        self.message_user(request, f"{updated} audiobook(s) paused.")

    @admin.action(description="Resume selected audiobooks")
    def resume(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f"{updated} audiobook(s) resumed.")

    @admin.action(description="Enqueue next part")
    def enqueue_next(self, request, queryset):
        self._enqueue(request, queryset, allow_tail=False)

    @admin.action(description="Enqueue tail now (even if the source is not finished)")
    def enqueue_tail(self, request, queryset):
        self._enqueue(request, queryset, allow_tail=True)

    def _enqueue(self, request, queryset, allow_tail):
        created = 0
        skipped = []
        for audiobook in queryset:
            if audiobook.novel.is_dmca:
                skipped.append(f"{audiobook} (DMCA takedown)")
                continue
            if audiobook.status != 'active':
                skipped.append(f"{audiobook} (status: {audiobook.status})")
                continue
            if audiobook_service.enqueue_next_part(audiobook, allow_tail=allow_tail) is not None:
                created += 1
        if skipped:
            self.message_user(request, "Skipped: " + ", ".join(skipped), level=messages.WARNING)
        if created:
            self.message_user(request, f"{created} part(s) queued.")
        elif not skipped:
            self.message_user(request, "Nothing to cut: no part is ready.", level=messages.WARNING)

    @admin.action(description="Delete audio files of selected audiobooks")
    def delete_audio_files(self, request, queryset):
        if "apply" not in request.POST:
            context = {
                **self.admin_site.each_context(request),
                'title': 'Delete audio files',
                'opts': self.model._meta,
                'queryset': queryset,
                'rows': [(audiobook, audiobook.total_size_bytes / MB) for audiobook in queryset],
            }
            return render(request, "admin/lncrawler_api/audiobook/confirm_delete_audio.html", context)

        freed = 0
        for audiobook in queryset:
            try:
                freed += audiobook_service.delete_audio_files(audiobook)
            except Exception as exc:
                self.message_user(request, f"{audiobook}: audio files not deleted ({exc}).", level=messages.ERROR)
        self.message_user(request, f"Audio files deleted, {freed / MB:.1f} MB freed.")
        return None

    @admin.action(description="Unpin worker (any worker may claim the next part)")
    def unpin_worker(self, request, queryset):
        updated = queryset.update(worker_id='')
        self.message_user(request, f"{updated} audiobook(s) unpinned.")

    # -- Dashboard page --------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["dashboard_url"] = reverse("admin:lncrawler_api_audiobook_dashboard")
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        custom = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name="lncrawler_api_audiobook_dashboard",
            ),
        ]
        return custom + super().get_urls()

    def dashboard_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        return render(request, "admin/lncrawler_api/audiobook/dashboard.html", _dashboard_context(request))


class AudiobookChapterInline(admin.TabularInline):
    model = AudiobookChapter
    extra = 0
    can_delete = False
    fields = ('chapter_number', 'chapter_title', 'duration', 'size', 'preview')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('chapter')

    def chapter_number(self, obj):
        return obj.chapter.chapter_id
    chapter_number.short_description = 'Chapter'

    def chapter_title(self, obj):
        return obj.chapter.title
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
        'approved',
        'attempts',
        'worker_id',
        'progress_percent',
        'completed_at',
    )
    list_filter = ('status', 'engine', 'qa_passed')
    search_fields = ('audiobook__novel__title', 'engine_version')
    list_select_related = ('audiobook__novel',)
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
        'lease_until',
        'progress',
        'stage',
        'attempts',
        'error_message',
        'content_hash',
        'cast',
        'qa',
        'qa_passed',
        'qa_table',
        'duration_s',
        'size_bytes',
        'created_at',
        'completed_at',
        'm4b_links',
    )
    inlines = [AudiobookChapterInline]
    actions = ['retry', 'regenerate', 'approve']

    def get_urls(self):
        custom = [
            path(
                "<uuid:part_id>/m4b/<str:fmt>/",
                self.admin_site.admin_view(self.m4b_view),
                name="lncrawler_api_audiobookpart_m4b",
            ),
        ]
        return custom + super().get_urls()

    def m4b_view(self, request, part_id, fmt):
        """Serve the cached .m4b of a part, or start its build and come back to the part page."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        if fmt not in audiobook_m4b.FORMATS:
            raise Http404
        part = get_object_or_404(AudiobookPart.objects.select_related('audiobook__novel', 'audiobook__source'), pk=part_id)
        back = redirect('admin:lncrawler_api_audiobookpart_change', part.pk)
        if not part.is_listenable():
            self.message_user(request, "This part is not listenable yet.", level=messages.ERROR)
            return back

        cached = audiobook_m4b.cached_m4b(part, fmt)
        if cached is not None:
            return FileResponse(
                open(cached, 'rb'), as_attachment=True, filename=audiobook_m4b.download_filename(part),
            )

        key = audiobook_m4b.m4b_job_key(part.pk, fmt)
        latest = Job.objects.filter(job_type=Job.JOB_TYPE_M4B, query=key).order_by('-created_at').first()
        audiobook_m4b.enqueue_m4b_job(part, fmt, user=request.user)
        if latest is not None and latest.status == Job.STATUS_FAILED:
            self.message_user(
                request, f"Build failed: {latest.error_message or 'unknown error'}. Building again, refresh in a minute.",
                level=messages.ERROR,
            )
        else:
            self.message_user(request, "Building, refresh in a minute.")
        return back

    def m4b_links(self, obj):
        if obj.pk is None or not obj.is_listenable():
            return "Available once the part is done and has passed QA or been approved."
        return format_html(
            '<a href="{}">Download .m4b (Opus)</a> &middot; <a href="{}">Download .m4b (AAC)</a>',
            reverse('admin:lncrawler_api_audiobookpart_m4b', args=[obj.pk, 'opus']),
            reverse('admin:lncrawler_api_audiobookpart_m4b', args=[obj.pk, 'aac']),
        )
    m4b_links.short_description = '.m4b files'

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

    @admin.action(description="Retry selected failed parts")
    def retry(self, request, queryset):
        count = 0
        for part in queryset.filter(status='failed'):
            audiobook_service.retry_part(part)
            count += 1
        self.message_user(request, f"{count} part(s) queued again.")

    @admin.action(description="Regenerate selected parts (high priority)")
    def regenerate(self, request, queryset):
        count = 0
        for part in queryset.filter(status__in=['done', 'stale', 'failed']):
            audiobook_service.regenerate_part(part)
            count += 1
        self.message_user(request, f"{count} part(s) queued for regeneration.")

    @admin.action(description="Approve selected parts despite QA")
    def approve(self, request, queryset):
        updated = queryset.update(approved=True)
        self.message_user(request, f"{updated} part(s) approved.")


@admin.register(AudiobookWorker)
class AudiobookWorkerAdmin(admin.ModelAdmin):
    list_display = ('worker_id', 'user', 'online', 'last_seen_at', 'version', 'available')
    list_select_related = ('user',)
    readonly_fields = ('worker_id', 'last_seen_at', 'version', 'available', 'message')

    def online(self, obj):
        return obj.is_online
    online.boolean = True


@admin.register(ListeningProgress)
class ListeningProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'audiobook', 'chapter', 'position_s', 'speed', 'finished', 'updated_at')
    list_filter = ('finished',)
    list_select_related = ('user', 'audiobook__novel', 'chapter__novel_from_source')
    search_fields = ('user__username', 'audiobook__novel__title')
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False


@admin.register(AudiobookDailyStat)
class AudiobookDailyStatAdmin(admin.ModelAdmin):
    list_display = ('audiobook', 'date', 'plays', 'downloads', 'listen_seconds')
    list_filter = ('date',)
    list_select_related = ('audiobook__novel',)
    search_fields = ('audiobook__novel__title',)
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False
