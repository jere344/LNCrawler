"""Admin for the LLM judged candidates: one list for every kind, and a review page per kind.

The decisions themselves are made by ``services/candidate_service``. The review pages
walk the candidates waiting in ``review`` for one kind, with the same layout for every
kind: the targets on the left, the LLM panel on the right.
"""
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, F, FloatField, IntegerField, Value, When
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from ..models import Author, Candidate, Novel, Tag
from ..services import candidate_service, llm_tasks
from ..services.merge_service import MergeError
from ..services.tag_merge_service import tag_usage
from ..utils.media_utils import build_media_url
from .merge_common import _pretty_json, undo_and_report

KIND_LABELS = dict(Candidate.KIND_CHOICES)

# What undoing a novel merge does not bring back (the merged data stays on the survivor).
NOVEL_UNDO_LOSSES = [
    "Ratings of the merged-away novel: they stay on the survivor.",
    "Reviews of the merged-away novel: they stay on the survivor.",
    "Novel-level comments: they stay on the survivor.",
    "Bookmarks: they stay on the survivor.",
    "Reading-list entries: they stay on the survivor.",
    "Sources folded into an existing copy of the survivor (duplicates): they are deleted and do not come back.",
]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
        "id", "kind", "names", "status", "decided_by", "confidence", "certainty",
        "short_reason", "created_at",
    )
    list_filter = ("kind", "status", "decided_by")
    search_fields = ("target_names", "signature")
    fields = (
        "kind",
        "status",
        "decided_by",
        "decided_at",
        "target_ids",
        "target_names",
        "signature",
        "signals",
        "certainty",
        "confidence",
        "reason",
        "verdict_pretty",
        "llm_call_link",
        "attempts",
        "not_before",
        "claimed_at",
        "undo_pretty",
        "undone_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields
    actions = (
        "apply_candidates",
        "reject_candidates",
        "undo_candidates",
        "rejudge_candidates",
        "redecide",
    )
    change_list_template = "admin/lncrawler_api/candidate/change_list.html"
    # Session key prefix holding the candidate ids deferred with "Skip for now", per kind.
    SESSION_SKIPPED = "candidate_review_skipped_{kind}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Rejected and undone rows are what keeps a refused pair from being proposed again,
        # and applied rows hold the undo data. Open rows are deleted by the code, not by hand.
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_change_permission(request):
            extra_context["review_links"] = [
                {
                    "url": reverse("admin:lncrawler_api_candidate_review", args=[kind]),
                    "label": label,
                    "count": Candidate.objects.filter(kind=kind, status=Candidate.STATUS_REVIEW).count(),
                }
                for kind, label in Candidate.KIND_CHOICES
            ]
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Inserted before the defaults so "review/<kind>/" is not swallowed by the
        # "<path:object_id>/" view.
        custom = [
            path(
                "review/<str:kind>/",
                self.admin_site.admin_view(self.review_view),
                name="lncrawler_api_candidate_review",
            ),
        ]
        return custom + super().get_urls()

    # List and detail columns

    @admin.display(description="Names")
    def names(self, obj):
        return ", ".join(obj.target_names)

    @admin.display(description="Reason")
    def short_reason(self, obj):
        return Truncator(obj.reason or "").chars(80)

    @admin.display(description="Verdict")
    def verdict_pretty(self, obj):
        return _pretty_json(obj.verdict)

    @admin.display(description="Undo")
    def undo_pretty(self, obj):
        return _pretty_json(obj.undo)

    @admin.display(description="LLM call")
    def llm_call_link(self, obj):
        if obj.llm_call_id is None:
            return "-"
        url = reverse("admin:lncrawler_api_llmcall_change", args=[obj.llm_call_id])
        return format_html('<a href="{}">{}</a>', url, obj.llm_call_id)

    # Actions

    def _actionable(self, request, queryset, statuses):
        """The selected candidates that may take an action: not in flight, and in one of ``statuses``.

        A candidate in flight is reported and left alone; so is one whose status the
        action does not take.
        """
        chosen, left_alone = [], 0
        for candidate in queryset:
            if candidate.claimed_at is not None:
                self.message_user(
                    request,
                    f"{candidate}: the LLM is judging it right now; try again later.",
                    messages.WARNING,
                )
            elif candidate.status in statuses:
                chosen.append(candidate)
            else:
                left_alone += 1
        if left_alone:
            self.message_user(
                request,
                f"Left {left_alone} candidate(s) alone: this action does not apply to their status.",
                messages.WARNING,
            )
        return chosen

    def _run_each(self, request, candidates, operation, verb):
        """Run ``operation`` on each candidate, reporting every refusal and how many succeeded."""
        done = 0
        for candidate in candidates:
            try:
                operation(candidate)
            except MergeError as exc:
                self.message_user(request, f"{candidate}: {exc}", messages.ERROR)
            else:
                done += 1
        self.message_user(request, f"{verb} {done} candidate(s).", messages.SUCCESS)

    @admin.action(description="Apply (forced: ignores the safeguards)", permissions=["change"])
    def apply_candidates(self, request, queryset):
        candidates = self._actionable(request, queryset, [Candidate.STATUS_REVIEW])
        self._run_each(request, candidates, candidate_service.apply_candidate, "Applied")

    @admin.action(description="Reject", permissions=["change"])
    def reject_candidates(self, request, queryset):
        candidates = self._actionable(request, queryset, [Candidate.STATUS_REVIEW])
        self._run_each(request, candidates, candidate_service.reject_candidate, "Rejected")

    @admin.action(description="Undo applied changes", permissions=["change"])
    def undo_candidates(self, request, queryset):
        candidates = self._actionable(request, queryset, [Candidate.STATUS_APPLIED])
        if not candidates:
            return None
        if any(candidate.kind == Candidate.KIND_NOVEL_MERGE for candidate in candidates) and (
            request.POST.get("confirmed") != "yes"
        ):
            context = {
                **self.admin_site.each_context(request),
                "title": "Undo applied changes",
                "opts": self.model._meta,
                "candidates": candidates,
                "losses": NOVEL_UNDO_LOSSES,
                "selected": [str(candidate.pk) for candidate in candidates],
            }
            return render(request, "admin/lncrawler_api/candidate/undo_confirm.html", context)
        undo_and_report(
            self, request, candidates, candidate_service.undo_candidate,
            label=str, noun="candidate",
        )
        return None

    @admin.action(description="Re-judge (send back to the LLM)", permissions=["change"])
    def rejudge_candidates(self, request, queryset):
        candidates = self._actionable(
            request, queryset,
            [
                Candidate.STATUS_PENDING, Candidate.STATUS_REVIEW, Candidate.STATUS_REJECTED,
                Candidate.STATUS_ERROR, Candidate.STATUS_UNDONE,
            ],
        )
        self._run_each(request, candidates, candidate_service.rejudge_candidate, "Sent")

    @admin.action(description="Re-decide (LLM decisions in review or rejected)", permissions=["change"])
    def redecide(self, request, queryset):
        candidates = self._actionable(
            request, queryset, [Candidate.STATUS_REVIEW, Candidate.STATUS_REJECTED],
        )
        self._run_each(request, candidates, candidate_service.redecide_candidate, "Re-decided")

    # Review pages

    def _review_queue(self, kind):
        """Candidates of ``kind`` waiting in review, in the order the reviewer works through them.

        LLM "yes" answers come first (most confident first, then certainty), then the
        "unsure" ones, and the "no" answers last.
        """
        return Candidate.objects.filter(kind=kind, status=Candidate.STATUS_REVIEW).annotate(
            queue_bucket=Case(
                When(verdict__answer="yes", then=Value(0)),
                When(verdict__answer="no", then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            # Only the "yes" bucket orders by confidence; elsewhere it is a constant.
            yes_confidence=Case(
                When(verdict__answer="yes", then=Coalesce(F("confidence"), Value(0.0))),
                default=Value(0.0),
                output_field=FloatField(),
            ),
        ).order_by("queue_bucket", "-yes_confidence", "-certainty", "pk")

    def review_view(self, request, kind):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if kind not in KIND_LABELS:
            raise Http404

        skip_key = self.SESSION_SKIPPED.format(kind=kind)
        skipped = request.session.get(skip_key, [])
        review_url = reverse("admin:lncrawler_api_candidate_review", args=[kind])

        if request.method == "POST":
            action = request.POST.get("action")
            if action == "reset":
                request.session[skip_key] = []
                return redirect(review_url)

            try:
                candidate_pk = int(request.POST.get("candidate", ""))
            except ValueError:
                return redirect(review_url)
            candidate = Candidate.objects.filter(pk=candidate_pk, kind=kind).first()
            if candidate is not None:
                self._review_action(request, candidate, action, skipped, skip_key)
            return redirect(review_url)

        remaining = self._review_queue(kind).exclude(pk__in=skipped)
        candidate = remaining.select_related("llm_call").first()
        context = {
            **self.admin_site.each_context(request),
            "title": f"Review: {KIND_LABELS[kind]}",
            "opts": self.model._meta,
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "list_url": reverse("admin:lncrawler_api_candidate_changelist"),
            "review_url": review_url,
            "candidate": candidate,
            "remaining": remaining.count(),
            "can_reset": candidate is None and bool(skipped),
        }
        if candidate is not None:
            context.update(self._review_context(candidate))
            context["targets_template"] = f"admin/lncrawler_api/candidate/_{kind}.html"
        return render(request, "admin/lncrawler_api/candidate/review.html", context)

    def _review_action(self, request, candidate, action, skipped, skip_key):
        """Apply one reviewer button to ``candidate`` and keep the skip list in step."""
        if candidate.claimed_at is not None:
            self.message_user(
                request, f"{candidate}: the LLM is judging it right now; try again later.",
                messages.WARNING,
            )
            return
        if candidate.status != Candidate.STATUS_REVIEW:
            self.message_user(
                request, f"{candidate}: no longer waiting in review.", messages.INFO,
            )
            return

        if action not in ("skip", "apply", "reject", "rejudge"):
            return
        # A decided candidate leaves the skip list; a skipped one joins it.
        skipped[:] = [pk for pk in skipped if pk != candidate.pk]
        if action == "skip":
            skipped.append(candidate.pk)
            self.message_user(request, f"Skipped {candidate} for now.", messages.INFO)
        elif action == "apply":
            self._review_run(
                request, candidate, candidate_service.apply_candidate,
                f"Applied {candidate}.",
            )
        elif action == "reject":
            self._review_run(
                request, candidate, candidate_service.reject_candidate,
                f"Rejected {candidate}.",
            )
        elif action == "rejudge":
            self._review_run(
                request, candidate, candidate_service.rejudge_candidate,
                f"Sent {candidate} back to the LLM judge.",
            )
        request.session[skip_key] = skipped

    def _review_run(self, request, candidate, operation, success):
        try:
            operation(candidate)
        except MergeError as exc:
            self.message_user(request, f"{candidate}: {exc}", messages.ERROR)
        else:
            self.message_user(request, success, messages.SUCCESS)

    def _review_context(self, candidate):
        """What the review page shows about one candidate: the targets and the LLM panel."""
        task = llm_tasks.REGISTRY[candidate.kind]
        # A verdict copied from a broken old answer can be a plain string.
        verdict = candidate.verdict if isinstance(candidate.verdict, dict) else {}
        threshold = task.threshold()
        llm_call = candidate.llm_call
        llm = {
            "answer": verdict.get("answer", ""),
            "rating": verdict.get("rating", ""),
            "relation": verdict.get("relation", ""),
            "llm_reason": verdict.get("reason", ""),
            "confidence": candidate.confidence,
            "threshold": threshold,
            "below_threshold": candidate.confidence is not None and candidate.confidence < threshold,
            "model": llm_call.model if llm_call else "",
            "provider": llm_call.provider if llm_call else "",
            "prompt_version": llm_call.prompt_version if llm_call else "",
            "url": (
                reverse("admin:lncrawler_api_llmcall_change", args=[llm_call.pk]) if llm_call else ""
            ),
        }
        builder = {
            Candidate.KIND_NOVEL_MERGE: self._novel_targets,
            Candidate.KIND_TAG_R18: self._tag_r18_targets,
            Candidate.KIND_AUTHOR_MERGE: self._author_targets,
            Candidate.KIND_TAG_MERGE: self._tag_targets,
        }[candidate.kind]
        return {"llm": llm, "certainty_pct": round(candidate.certainty * 100, 1), **builder(candidate)}

    # Targets, one builder per kind (each returns the context the _<kind>.html include reads)

    def _novel_targets(self, candidate):
        found = {str(novel.pk): novel for novel in Novel.objects.filter(pk__in=candidate.target_ids)}
        novels = [found.get(str(pk)) for pk in candidate.target_ids]
        return {"sides": [self._novel_side(novel) for novel in novels]}

    def _novel_side(self, novel):
        """Everything the reviewer needs about one side of a novel_merge candidate."""
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

    def _tag_r18_targets(self, candidate):
        tag = Tag.objects.filter(pk__in=candidate.target_ids).first()
        if tag is None:
            return {"tag": None}
        novels = Novel.objects.filter(sources__tags=tag).distinct()
        return {
            "tag": tag,
            "tag_admin_url": reverse("admin:lncrawler_api_tag_change", args=[tag.pk]),
            "novel_count": novels.count(),
            "novels": [
                {
                    "title": novel.title,
                    "admin_url": reverse("admin:lncrawler_api_novel_change", args=[novel.pk]),
                    "cover": next(
                        (
                            build_media_url(s.cover_min_path or s.cover_path)
                            for s in novel.sources.all()
                            if s.cover_min_path or s.cover_path
                        ),
                        None,
                    ),
                }
                for novel in novels.prefetch_related("sources")[:6]
            ],
        }

    def _author_targets(self, candidate):
        authors = []
        for author in Author.objects.filter(pk__in=candidate.target_ids).order_by("pk"):
            novels = Novel.objects.filter(sources__authors=author).distinct()
            authors.append({
                "name": author.name,
                "admin_url": reverse("admin:lncrawler_api_author_change", args=[author.pk]),
                "aliases": [alias.name for alias in author.aliases.all()],
                "novel_count": novels.count(),
                "titles": list(novels.values_list("title", flat=True)[:5]),
            })
        return {"authors": authors}

    def _tag_targets(self, candidate):
        tags = {tag.pk: tag for tag in Tag.objects.filter(pk__in=candidate.target_ids)}
        usage = tag_usage(candidate.target_ids)
        # A set's members are tag pks (the judge's labels are mapped back when it is stored).
        verdict = candidate.verdict if isinstance(candidate.verdict, dict) else {}
        sets = [proposed for proposed in verdict.get("sets") or [] if isinstance(proposed, dict)]
        member_pks = {pk for proposed in sets for pk in proposed.get("members", [])}
        names = {pk: tag.name for pk, tag in Tag.objects.in_bulk(list(member_pks)).items()}
        return {
            "tags": [
                {
                    "name": tags[pk].name if pk in tags else name,
                    "usage": usage.get(pk, 0),
                    "admin_url": (
                        reverse("admin:lncrawler_api_tag_change", args=[pk]) if pk in tags else ""
                    ),
                }
                for pk, name in zip(candidate.target_ids, candidate.target_names)
            ],
            "sets": [
                {
                    "canonical": proposed.get("canonical", ""),
                    "confidence": proposed.get("confidence"),
                    "members": [names.get(pk, str(pk)) for pk in proposed.get("members", [])],
                }
                for proposed in sets
            ],
        }
