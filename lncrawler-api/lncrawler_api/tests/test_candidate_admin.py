"""Tests for the candidate admin: the list, the per-kind review pages and the actions."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Candidate, Tag


class CandidateAdminTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("cand-admin", "cand@example.com", "pw")
        self.client.force_login(user)
        self.tag = Tag.objects.create(name="Isekai")

    def make_candidate(self, status=Candidate.STATUS_REVIEW, **extra):
        return Candidate.objects.create(
            kind=Candidate.KIND_TAG_R18,
            target_ids=[self.tag.pk],
            target_names=[self.tag.name],
            signature=f"sig-{Candidate.objects.count()}",
            status=status,
            verdict={"answer": "yes"},
            confidence=0.9,
            **extra,
        )

    def test_changelist_loads_with_review_links(self):
        self.make_candidate()
        response = self.client.get(reverse("admin:lncrawler_api_candidate_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"]))

    def test_review_page_shows_the_waiting_candidate(self):
        candidate = self.make_candidate()
        response = self.client.get(reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["candidate"], candidate)
        self.assertEqual(response.context["remaining"], 1)

    def test_review_page_with_nothing_waiting(self):
        response = self.client.get(reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["candidate"])

    def test_unknown_kind_is_not_found(self):
        response = self.client.get(reverse("admin:lncrawler_api_candidate_review", args=["nope"]))
        self.assertEqual(response.status_code, 404)

    def test_review_reject_button_moves_candidate_out_of_review(self):
        candidate = self.make_candidate()
        url = reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"])
        self.client.post(url, {"candidate": candidate.pk, "action": "reject"})
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)

    def test_skip_keeps_candidate_out_of_the_queue_until_reset(self):
        candidate = self.make_candidate()
        url = reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"])
        self.client.post(url, {"candidate": candidate.pk, "action": "skip"})
        response = self.client.get(url)
        self.assertIsNone(response.context["candidate"])
        self.assertTrue(response.context["can_reset"])

        self.client.post(url, {"action": "reset"})
        response = self.client.get(url)
        self.assertEqual(response.context["candidate"], candidate)

    def test_in_flight_candidate_is_refused_by_the_action(self):
        from django.utils import timezone

        candidate = self.make_candidate(claimed_at=timezone.now())
        self.client.post(
            reverse("admin:lncrawler_api_candidate_changelist"),
            {"action": "reject_candidates", "_selected_action": [candidate.pk]},
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)


class CandidateAdminGuardTests(TestCase):
    """Permissions, the review queue order, the novel undo confirmation and the budget panel."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("guard-admin", "guard@example.com", "pw")
        self.client.force_login(self.user)

    def candidate(self, kind, target_ids, **extra):
        return Candidate.objects.create(
            kind=kind,
            target_ids=target_ids,
            target_names=[str(pk) for pk in target_ids],
            signature=f"guard-{Candidate.objects.count()}",
            **extra,
        )

    def test_review_page_needs_staff(self):
        self.client.logout()
        url = reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_candidates_and_llm_calls_cannot_be_deleted_from_the_admin(self):
        from django.contrib import admin as django_admin
        from django.test import RequestFactory

        from ..models import LLMCall

        request = RequestFactory().get("/")
        request.user = self.user
        for model in (Candidate, LLMCall):
            model_admin = django_admin.site._registry[model]
            self.assertFalse(model_admin.has_delete_permission(request))
            self.assertNotIn("delete_selected", model_admin.get_actions(request))

    def test_review_queue_puts_confident_yes_first_and_no_last(self):
        review = Candidate.STATUS_REVIEW
        no = self.candidate("tag_r18", [1], status=review, verdict={"answer": "no"}, confidence=0.99)
        unsure = self.candidate("tag_r18", [2], status=review, verdict={"answer": "unsure"})
        weak_yes = self.candidate("tag_r18", [3], status=review, verdict={"answer": "yes"}, confidence=0.6)
        strong_yes = self.candidate("tag_r18", [4], status=review, verdict={"answer": "yes"}, confidence=0.9)
        from django.contrib import admin as django_admin

        model_admin = django_admin.site._registry[Candidate]

        queue = list(model_admin._review_queue("tag_r18"))

        self.assertEqual(queue, [strong_yes, weak_yes, unsure, no])

    def test_review_post_with_a_bad_candidate_id_is_ignored(self):
        url = reverse("admin:lncrawler_api_candidate_review", args=["tag_r18"])
        candidate = self.candidate("tag_r18", [1], status=Candidate.STATUS_REVIEW, verdict={"answer": "yes"})
        response = self.client.post(url, {"candidate": "not-a-number", "action": "reject"})
        self.assertEqual(response.status_code, 302)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)

    def test_novel_undo_asks_for_confirmation_first(self):
        candidate = self.candidate(
            Candidate.KIND_NOVEL_MERGE, ["a", "b"], status=Candidate.STATUS_APPLIED,
            undo=[{"type": "novel_merge", "source_id": "a", "target_id": "b", "moved_source_ids": []}],
        )
        response = self.client.post(
            reverse("admin:lncrawler_api_candidate_changelist"),
            {"action": "undo_candidates", "_selected_action": [candidate.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/lncrawler_api/candidate/undo_confirm.html")
        self.assertContains(response, "stay on the survivor")
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

    def test_budget_panel_leaves_out_the_copied_request_log(self):
        from ..models import LLMCall
        from ..services import llm_service

        LLMCall.objects.create(kind="tag_r18", provider="p", tokens=10)
        LLMCall.objects.create(kind="tag_r18", provider=llm_service.REQUEST_LOG_PROVIDER, tokens=0)

        response = self.client.get(reverse("admin:lncrawler_api_llmcall_changelist"))

        usage = response.context["llm_usage"]
        self.assertEqual((usage["requests"], usage["tokens"]), (1, 10))


class BrokenVerdictReviewTests(TestCase):
    def test_review_page_renders_a_verdict_that_is_not_a_dict(self):
        user = get_user_model().objects.create_superuser("broken-admin", "broken@example.com", "pw")
        self.client.force_login(user)
        tag = Tag.objects.create(name="Broken")
        for kind in (Candidate.KIND_TAG_R18, Candidate.KIND_TAG_MERGE):
            Candidate.objects.create(
                kind=kind, target_ids=[tag.pk], target_names=[tag.name], signature=f"broken-{kind}",
                status=Candidate.STATUS_REVIEW, verdict="garbage",
            )
            response = self.client.get(reverse("admin:lncrawler_api_candidate_review", args=[kind]))
            self.assertEqual(response.status_code, 200, kind)
            self.assertEqual(response.context["candidate"].kind, kind)


class CandidateAdminActionTests(TestCase):
    """The bulk actions: who may run them, and what each one does."""

    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser("act-admin", "act@example.com", "pw")
        self.client.force_login(self.admin_user)
        self.changelist = reverse("admin:lncrawler_api_candidate_changelist")

    def candidate(self, status, **extra):
        tag = Tag.objects.create(name=f"Tag {Candidate.objects.count()}")
        return Candidate.objects.create(
            kind=Candidate.KIND_TAG_R18, target_ids=[tag.pk], target_names=[tag.name],
            signature=f"act-{tag.pk}", status=status, verdict={"answer": "yes"}, confidence=0.5, **extra,
        )

    def run_action(self, action, candidate, **extra):
        return self.client.post(self.changelist, {"action": action, "_selected_action": [candidate.pk], **extra})

    def test_view_only_staff_cannot_run_an_action(self):
        from django.contrib.auth.models import Permission

        viewer = get_user_model().objects.create_user("viewer", "viewer@example.com", "pw", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_candidate"))
        self.client.force_login(viewer)
        candidate = self.candidate(Candidate.STATUS_REVIEW)

        self.run_action("apply_candidates", candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)

    def test_apply_action_applies_a_review_candidate(self):
        candidate = self.candidate(Candidate.STATUS_REVIEW)
        self.run_action("apply_candidates", candidate)
        candidate.refresh_from_db()
        self.assertEqual((candidate.status, candidate.decided_by), (Candidate.STATUS_APPLIED, Candidate.DECIDED_HUMAN))
        self.assertTrue(Tag.objects.get(pk=candidate.target_ids[0]).is_adult)

    def test_rejudge_action_sends_a_candidate_back_to_the_llm(self):
        candidate = self.candidate(Candidate.STATUS_REJECTED, decided_by=Candidate.DECIDED_LLM, attempts=2)
        self.run_action("rejudge_candidates", candidate)
        candidate.refresh_from_db()
        self.assertEqual((candidate.status, candidate.attempts), (Candidate.STATUS_PENDING, 0))

    def test_redecide_action_runs_the_stored_verdict_again(self):
        # Below the R18 threshold (0.85): an LLM "yes" at 0.5 stays in review.
        candidate = self.candidate(Candidate.STATUS_REJECTED, decided_by=Candidate.DECIDED_LLM)
        self.run_action("redecide", candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)

    def test_confirmed_novel_undo_runs_the_undo(self):
        from unittest import mock

        from ..services import candidate_service

        candidate = Candidate.objects.create(
            kind=Candidate.KIND_NOVEL_MERGE, target_ids=["a", "b"], target_names=["A", "B"],
            signature="act-novel", status=Candidate.STATUS_APPLIED,
            undo=[{"type": "novel_merge", "source_id": "a", "target_id": "b", "moved_source_ids": []}],
        )
        with mock.patch.object(candidate_service, "undo_candidate") as undo:
            self.run_action("undo_candidates", candidate, confirmed="yes")
        undo.assert_called_once()
        self.assertEqual(undo.call_args.args[0].pk, candidate.pk)
