from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from ..models import MergeCandidate, Novel
from ..services.merge_service import MergeError, merge_novels
from ..utils.media_utils import build_media_url


def _pick_survivor(a, b):
    """Keep the novel carrying more sources; ties broken by id for stability."""
    if a is None:
        return b
    if b is None:
        return a
    count_a = a.sources.count()
    count_b = b.sources.count()
    if count_a != count_b:
        return a if count_a > count_b else b
    return a if str(a.pk) <= str(b.pk) else b


@admin.register(MergeCandidate)
class MergeCandidateAdmin(admin.ModelAdmin):
    list_display = ("certainty_badge", "title_a", "title_b", "decision", "status", "created_at")
    list_filter = ("status", "decision")
    search_fields = ("title_a", "title_b")
    readonly_fields = (
        "novel_a_link",
        "novel_b_link",
        "title_a",
        "title_b",
        "certainty",
        "signals",
        "decision",
        "llm_verdict",
        "llm_reason",
        "llm_model",
        "llm_checked_at",
        "novel_a_id_snapshot",
        "novel_b_id_snapshot",
        "created_at",
        "updated_at",
    )
    actions = ("approve_and_merge", "reject_candidates")
    change_list_template = "admin/lncrawler_api/mergecandidate/change_list.html"

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_change_permission(request):
            pending = MergeCandidate.objects.filter(
                status=MergeCandidate.STATUS_PENDING
            ).count()
            extra_context["review_button"] = {
                "url": reverse("admin:lncrawler_api_mergecandidate_review"),
                "label": f"Review candidates ({pending})",
            }
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Inserted before the defaults so "review/" is not swallowed by the
        # "<path:object_id>/" history view.
        custom = [
            path(
                "review/",
                self.admin_site.admin_view(self.review_view),
                name="lncrawler_api_mergecandidate_review",
            ),
        ]
        return custom + super().get_urls()

    def review_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        if request.method == "POST":
            candidate = MergeCandidate.objects.filter(
                pk=request.POST.get("candidate")
            ).first()
            action = request.POST.get("action")
            if candidate is not None and candidate.status == MergeCandidate.STATUS_PENDING:
                if action == "merge":
                    status, message = self._apply_merge(candidate)
                    level = {
                        "merged": messages.SUCCESS,
                        "skipped": messages.WARNING,
                    }.get(status, messages.ERROR)
                    self.message_user(request, message, level=level)
                elif action == "reject":
                    candidate.mark_rejected()
                    self.message_user(
                        request,
                        f"Rejected '{candidate.title_a}' / '{candidate.title_b}'.",
                        level=messages.SUCCESS,
                    )
            return redirect("admin:lncrawler_api_mergecandidate_review")

        pending = MergeCandidate.objects.filter(
            status=MergeCandidate.STATUS_PENDING
        ).order_by("-certainty")
        candidate = pending.select_related("novel_a", "novel_b").first()
        context = {
            **self.admin_site.each_context(request),
            "title": "Review merge candidates",
            "opts": self.model._meta,
            "candidate": candidate,
            "remaining": pending.count(),
            "certainty_pct": round(candidate.certainty * 100, 1) if candidate else 0,
        }
        if candidate is not None:
            context["side_a"] = self._candidate_side(candidate.novel_a)
            context["side_b"] = self._candidate_side(candidate.novel_b)
        return render(request, "admin/lncrawler_api/mergecandidate/review.html", context)

    def _candidate_side(self, novel):
        """Everything the reviewer needs about one side of a candidate."""
        if novel is None:
            return None
        sources = novel.sources.select_related("external_source").prefetch_related(
            "authors", "alternative_titles", "tags"
        )
        return {
            "id": novel.pk,
            "title": novel.title,
            "slug": novel.slug,
            "admin_url": reverse("admin:lncrawler_api_novel_change", args=[novel.pk]),
            "source_count": novel.sources.count(),
            "sources": [
                {
                    "name": s.external_source.source_name if s.external_source else "-",
                    "language": s.language,
                    "title": s.title,
                    "url": s.source_url,
                    "novelupdates_url": s.novelupdates_url,
                    "cover": build_media_url(s.cover_min_path or s.cover_path),
                    "synopsis": (s.synopsis or "")[:400],
                    "authors": [a.name for a in s.authors.all()],
                    "alternative_titles": [a.name for a in s.alternative_titles.all()],
                    "tags": [t.name for t in s.tags.all()],
                }
                for s in sources
            ],
        }

    @admin.display(description="Certainty", ordering="certainty")
    def certainty_badge(self, obj):
        pct = f"{obj.certainty * 100:.0f}%"
        color = "#2e7d32" if obj.certainty >= 0.85 else "#ef6c00" if obj.certainty >= 0.5 else "#c62828"
        return format_html('<b style="color:{}">{}</b>', color, pct)

    def _novel_link(self, novel):
        if novel is None:
            return "-"
        url = reverse("admin:lncrawler_api_novel_change", args=[novel.pk])
        return format_html('<a href="{}">{}</a>', url, novel.title)

    @admin.display(description="Novel A")
    def novel_a_link(self, obj):
        return self._novel_link(obj.novel_a)

    @admin.display(description="Novel B")
    def novel_b_link(self, obj):
        return self._novel_link(obj.novel_b)

    def _apply_merge(self, candidate):
        """Merge a candidate's duplicate into the survivor.

        Returns ``(status, message)`` where status is merged/skipped/failed.
        """
        a, b = candidate.novel_a, candidate.novel_b
        if a is None or b is None:
            candidate.mark_skipped()
            return "skipped", "Candidate is no longer actionable (a novel was deleted)."
        target = _pick_survivor(a, b)
        source = b if target.pk == a.pk else a
        try:
            merge_novels(source, target)
        except MergeError as exc:
            return "failed", f"Could not merge: {exc}"
        candidate.refresh_from_db()
        candidate.mark_merged()
        self._clear_stale_for(source, keep=candidate.pk)
        return "merged", f"Merged '{source.title}' into '{target.title}'."

    @admin.action(description="Approve and merge the selected pairs")
    def approve_and_merge(self, request, queryset):
        merged = skipped = failed = 0
        candidate_ids = list(
            queryset.filter(status=MergeCandidate.STATUS_PENDING).values_list("pk", flat=True)
        )
        for candidate_id in candidate_ids:
            # Re-fetch each iteration: a previous merge may have deleted a novel
            # shared by a later candidate.
            candidate = MergeCandidate.objects.filter(pk=candidate_id).first()
            if candidate is None or candidate.status != MergeCandidate.STATUS_PENDING:
                continue
            status, message = self._apply_merge(candidate)
            if status == "merged":
                merged += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
                self.message_user(request, message, level=messages.ERROR)
        self.message_user(
            request,
            f"Merged {merged} pair(s); skipped {skipped}; failed {failed}.",
        )

    @admin.action(description="Reject the selected pairs")
    def reject_candidates(self, request, queryset):
        updated = queryset.filter(status=MergeCandidate.STATUS_PENDING).update(
            status=MergeCandidate.STATUS_REJECTED
        )
        self.message_user(request, f"Rejected {updated} candidate(s).")

    def _clear_stale_for(self, novel, keep):
        # Candidates other than the just-merged one that referenced the deleted
        # novel are no longer actionable.
        MergeCandidate.objects.filter(
            status=MergeCandidate.STATUS_PENDING
        ).exclude(pk=keep).filter(
            novel_a__isnull=True
        ).update(status=MergeCandidate.STATUS_SKIPPED)
        MergeCandidate.objects.filter(
            status=MergeCandidate.STATUS_PENDING
        ).exclude(pk=keep).filter(
            novel_b__isnull=True
        ).update(status=MergeCandidate.STATUS_SKIPPED)
