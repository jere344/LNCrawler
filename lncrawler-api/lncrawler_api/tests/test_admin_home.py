"""Tests for the admin home page (To review, Tools, Needs attention), the regrouped sidebar
and the reply count on the comment changelist."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from ..admin.home import TOOLS
from ..models import (
    Candidate,
    Comment,
    HarvestCandidate,
    LLMProviderCooldown,
    ScheduledTask,
)
from .helpers import bare_novel


class AdminHomeTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser("home-admin", "home@example.com", "pw")
        self.client.force_login(self.superuser)
        ScheduledTask.objects.all().delete()
        LLMProviderCooldown.objects.all().delete()

    def make_candidate(self, kind=Candidate.KIND_TAG_R18, status=Candidate.STATUS_REVIEW):
        n = Candidate.objects.count()
        return Candidate.objects.create(
            kind=kind,
            target_ids=[n + 1],
            target_names=[f"Target {n}"],
            signature=f"home-sig-{n}",
            status=status,
            verdict={"answer": "yes"},
            confidence=0.9,
        )

    def make_task(self, name, **fields):
        values = {
            "interval_seconds": 3600,
            "next_run_at": timezone.now(),
            "status": "pending",
        }
        values.update(fields)
        return ScheduledTask.objects.create(name=name, **values)

    def get_home(self):
        return self.client.get(reverse("admin:index"))

    def test_superuser_sees_home_sections_and_regrouped_sidebar(self):
        response = self.get_home()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "To review")
        self.assertContains(response, "Tools")
        self.assertContains(response, reverse("admin:lncrawler_api_novel_merge"))
        self.assertContains(response, reverse("admin:lncrawler_api_novel_split"))
        self.assertContains(response, reverse("admin:lncrawler_api_tag_merge"))
        self.assertContains(response, reverse("admin:lncrawler_api_placeholdercover_duplicates"))
        self.assertContains(response, reverse("admin:lncrawler_api_scheduledtask_management"))
        for group in ["Operations", "Review", "Library", "People &amp; Tags", "Community", "Audiobooks", "Stats"]:
            self.assertContains(response, f">{group}<")
        self.assertContains(response, "<h2>Harvest</h2>", html=False)
        self.assertContains(response, "<h2>Scheduled tasks</h2>", html=False)

    def test_every_tool_url_reverses(self):
        for label, url_name, _model, _action in TOOLS:
            with self.subTest(tool=label):
                # reverse() raises NoReverseMatch for a tool whose URL is gone.
                self.assertTrue(reverse(url_name))

    def test_sidebar_regroups_models_from_any_app(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superuser
        groups = {app["app_label"]: app for app in admin.site.get_app_list(request)}

        community = [model["object_name"] for model in groups["community"]["models"]]
        self.assertIn("CustomUser", community)
        self.assertEqual(
            [m["name"] for m in groups["community"]["models"] if m["object_name"] == "CustomUser"],
            ["Users"],
        )
        operations = [model["object_name"] for model in groups["operations"]["models"]]
        self.assertEqual(operations, ["HarvestConfig", "HarvestCandidate", "Job"])
        self.assertNotIn("lncrawler_api", groups)

    def test_review_counts_per_kind_and_failed_harvest(self):
        self.make_candidate(Candidate.KIND_TAG_R18)
        self.make_candidate(Candidate.KIND_TAG_R18)
        self.make_candidate(Candidate.KIND_TAG_R18, status=Candidate.STATUS_APPLIED)
        HarvestCandidate.objects.create(source_name="src", novel_url="https://example.test/a", status=HarvestCandidate.STATUS_FAILED)
        HarvestCandidate.objects.create(source_name="src", novel_url="https://example.test/b", status=HarvestCandidate.STATUS_DONE)

        response = self.get_home()
        kinds = {item["url"]: item["count"] for item in response.context["home"]["review"]["kinds"]}
        self.assertEqual(kinds[reverse("admin:lncrawler_api_candidate_review", args=[Candidate.KIND_TAG_R18])], 2)
        self.assertEqual(len(kinds), len(Candidate.KIND_CHOICES))
        self.assertContains(response, reverse("admin:lncrawler_api_candidate_review", args=[Candidate.KIND_TAG_R18]))

        failed = response.context["home"]["review"]["failed_harvest"]
        self.assertEqual(failed["count"], 1)
        self.assertIn("status__exact=failed", failed["url"])
        self.assertContains(response, "Failed harvest candidates")

    def test_failed_task_appears_under_needs_attention(self):
        task = self.make_task("crawl-broken", status="failed", error_message="connection refused by upstream")
        response = self.get_home()
        self.assertContains(response, "Needs attention")
        self.assertContains(response, "connection refused by upstream")
        self.assertContains(response, reverse("admin:lncrawler_api_scheduledtask_change", args=[task.pk]))

    def test_error_message_is_truncated(self):
        self.make_task("crawl-long", status="failed", error_message="x" * 400)
        response = self.get_home()
        self.assertContains(response, "x" * 159 + "…")
        self.assertNotContains(response, "x" * 160)

    def test_expired_lock_and_cooldown_are_listed(self):
        self.make_task(
            "stuck-task",
            status="running",
            locked_until=timezone.now() - timedelta(minutes=5),
            worker_id="worker-1",
        )
        self.make_task("fresh-lock", status="running", locked_until=timezone.now() + timedelta(minutes=5))
        LLMProviderCooldown.objects.create(
            name="openai", until=timezone.now() + timedelta(hours=1), reason="429 rate limited"
        )
        LLMProviderCooldown.objects.create(name="old", until=timezone.now() - timedelta(hours=1))

        response = self.get_home()
        self.assertContains(response, "Running with an expired lock")
        self.assertContains(response, "stuck-task")
        self.assertNotContains(response, "fresh-lock")
        self.assertContains(response, "LLM providers in cooldown")
        self.assertContains(response, "429 rate limited")
        self.assertNotContains(response, "All good")

    def test_needs_attention_says_all_good_when_empty(self):
        response = self.get_home()
        self.assertNotContains(response, "Needs attention")
        self.assertContains(response, "All good")

    def test_staff_without_permissions_sees_no_sections(self):
        staff = get_user_model().objects.create_user("plain-staff", "plain@example.com", "pw", is_staff=True)
        self.make_candidate()
        self.make_task("crawl-broken", status="failed", error_message="boom")
        self.client.force_login(staff)

        response = self.get_home()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "To review")
        self.assertNotContains(response, "Needs attention")
        self.assertNotContains(response, "boom")
        self.assertNotContains(response, reverse("admin:lncrawler_api_novel_merge"))

    def test_staff_with_candidate_change_permission_sees_review_counts(self):
        staff = get_user_model().objects.create_user("reviewer", "rev@example.com", "pw", is_staff=True)
        staff.user_permissions.add(
            Permission.objects.get(codename="change_candidate", content_type__app_label="lncrawler_api")
        )
        self.make_candidate()
        self.client.force_login(staff)

        response = self.get_home()
        self.assertContains(response, "To review")
        self.assertNotContains(response, "Needs attention")
        self.assertNotContains(response, reverse("admin:lncrawler_api_novel_merge"))


class CommentChangelistReplyCountTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("comment-admin", "comment@example.com", "pw")
        self.client.force_login(user)
        self.novel = bare_novel("reply-counts")

    def make_comment(self, message, parent=None):
        return Comment.objects.create(
            novel=self.novel,
            author_name="reader",
            message=message,
            parent=parent,
        )

    def test_changelist_renders_reply_counts(self):
        busy = self.make_comment("busy thread")
        self.make_comment("reply one", parent=busy)
        self.make_comment("reply two", parent=busy)
        self.make_comment("quiet thread")

        response = self.client.get(reverse("admin:lncrawler_api_comment_changelist"))
        self.assertEqual(response.status_code, 200)
        counts = {c.message: c.reply_total for c in response.context["cl"].result_list}
        self.assertEqual(counts["busy thread"], 2)
        self.assertEqual(counts["quiet thread"], 0)

    def test_reply_count_column_is_sortable(self):
        busy = self.make_comment("busy thread")
        self.make_comment("reply one", parent=busy)
        self.make_comment("reply two", parent=busy)
        self.make_comment("quiet thread")

        # Column 7 is reply_count (column 0 is the action checkbox); "-7" sorts it descending.
        response = self.client.get(reverse("admin:lncrawler_api_comment_changelist"), {"o": "-7"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_list[0].message, "busy thread")
