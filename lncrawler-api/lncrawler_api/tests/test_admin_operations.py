"""Tests for the admin Operations page, the worker token page and the author soft delete actions."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import formats, timezone
from rest_framework.authtoken.models import Token

from ..models import Author, AudiobookWorker, HarvestConfig, ScheduledTask
from ..services.audiobook_worker_auth import WORKER_GROUP


def make_staff(username, *codenames):
    """A staff user holding the given lncrawler_api permissions (no superuser bypass)."""
    user = get_user_model().objects.create_user(username, f"{username}@example.com", "pw", is_staff=True)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type__app_label="lncrawler_api", codename=codename))
    return user


class OperationsPageTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("ops-admin", "ops@example.com", "pw")
        self.client.force_login(user)
        self.url = reverse("admin:lncrawler_api_scheduledtask_management")
        self.home = reverse("admin:index")

    def test_page_renders_and_lists_the_last_run(self):
        last_run = timezone.now() - timedelta(hours=2)
        ScheduledTask.objects.create(
            name="prune_jobs", interval_seconds=86400, last_run_at=last_run,
            next_run_at=timezone.now() + timedelta(hours=22),
        )
        ScheduledTask.objects.create(
            name="prune_epub_cache", interval_seconds=86400, next_run_at=timezone.now(),
        )

        response = self.client.get(self.home)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scheduled tasks")
        self.assertContains(response, "Last run")
        self.assertContains(response, formats.localize(timezone.localtime(last_run)))
        self.assertContains(response, "never")
        self.assertNotContains(response, "Library import")
        self.assertNotContains(response, "Test a source")

    def test_only_registered_tasks_are_listed(self):
        ScheduledTask.objects.create(
            name="update_popular_sources", interval_seconds=3600, next_run_at=timezone.now(),
        )

        response = self.client.get(self.home)

        self.assertNotContains(response, "update_popular_sources")

    def test_failed_task_links_to_its_change_page(self):
        task = ScheduledTask.objects.create(
            name="prune_jobs", interval_seconds=86400, next_run_at=timezone.now(),
            status="failed", error_message="boom",
        )

        response = self.client.get(self.home)

        change_url = reverse("admin:lncrawler_api_scheduledtask_change", args=[task.pk])
        self.assertContains(response, f'href="{change_url}"')
        self.assertContains(response, ">failed</a>")

    def test_run_task_pulls_next_run_at_forward(self):
        task = ScheduledTask.objects.create(
            name="prune_jobs", interval_seconds=86400, next_run_at=timezone.now() + timedelta(days=1),
            status="failed", error_message="boom",
        )

        response = self.client.post(self.url, {"action": "run_task", "name": task.name})

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertLessEqual(task.next_run_at, timezone.now())
        # Only next_run_at moves; the status and the error are left for the scheduler to write.
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.error_message, "boom")

    def test_run_task_leaves_a_running_task_with_a_live_lock_alone(self):
        lock_until = timezone.now() + timedelta(minutes=10)
        later = timezone.now() + timedelta(days=1)
        task = ScheduledTask.objects.create(
            name="prune_jobs", interval_seconds=86400, next_run_at=later,
            status="running", locked_until=lock_until, worker_id="worker-1",
        )

        response = self.client.post(
            self.url, {"action": "run_task", "name": task.name}, follow=True,
        )

        self.assertContains(response, "&#x27;prune_jobs&#x27; is already running.")
        task.refresh_from_db()
        self.assertEqual(task.status, "running")
        self.assertEqual(task.locked_until, lock_until)
        self.assertEqual(task.worker_id, "worker-1")
        self.assertEqual(task.next_run_at, later)

    def test_run_task_pulls_next_run_at_forward_for_a_running_task_with_an_expired_lock(self):
        lock_until = timezone.now() - timedelta(minutes=5)
        task = ScheduledTask.objects.create(
            name="prune_jobs", interval_seconds=86400, next_run_at=timezone.now() + timedelta(days=1),
            status="running", locked_until=lock_until, worker_id="worker-1",
        )

        self.client.post(self.url, {"action": "run_task", "name": task.name})

        task.refresh_from_db()
        self.assertLessEqual(task.next_run_at, timezone.now())
        # The expired lock is left for acquire_lock to take over, so the status is not rewritten here.
        self.assertEqual(task.status, "running")
        self.assertEqual(task.locked_until, lock_until)

    def test_run_task_refuses_a_name_the_scheduler_does_not_run(self):
        later = timezone.now() + timedelta(days=1)
        task = ScheduledTask.objects.create(
            name="update_popular_sources", interval_seconds=3600, next_run_at=later,
        )

        response = self.client.post(
            self.url, {"action": "run_task", "name": task.name}, follow=True,
        )

        self.assertContains(response, "No task named &#x27;update_popular_sources&#x27;.")
        task.refresh_from_db()
        self.assertEqual(task.next_run_at, later)

    def test_harvest_actions_are_refused_without_change_harvestconfig(self):
        config = HarvestConfig.get_solo()
        enabled, concurrency = config.enabled, config.max_concurrent
        self.client.force_login(make_staff("ops-viewer", "change_scheduledtask"))

        for data in (
            {"action": "toggle_harvest"},
            {"action": "set_concurrency", "max_concurrent": "9"},
            {"action": "run_scan"},
        ):
            with self.subTest(action=data["action"]):
                response = self.client.post(self.url, data, follow=True)
                self.assertContains(response, "You need permission to change the harvest settings.")
                self.assertNotContains(response, "Harvest scan started")

        config.refresh_from_db()
        self.assertEqual((config.enabled, config.max_concurrent), (enabled, concurrency))

    def test_harvest_toggle_works_with_change_harvestconfig(self):
        self.client.force_login(make_staff("harvest-ops", "change_scheduledtask", "change_harvestconfig"))
        enabled = HarvestConfig.get_solo().enabled

        self.client.post(self.url, {"action": "toggle_harvest"})

        self.assertNotEqual(HarvestConfig.get_solo().enabled, enabled)

    def test_run_scan_button_is_hidden_without_change_harvestconfig(self):
        self.assertContains(self.client.get(self.home), "Run scan now")
        self.client.force_login(make_staff("task-ops", "change_scheduledtask"))

        response = self.client.get(self.home)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scheduled tasks")
        self.assertNotContains(response, "Run scan now")
        self.assertNotContains(response, 'name="max_concurrent"')
        self.assertNotContains(response, 'value="toggle_harvest"')

    def test_scheduled_task_changelist_redirects_to_the_home(self):
        response = self.client.get(reverse("admin:lncrawler_api_scheduledtask_changelist"))

        self.assertRedirects(response, self.home, fetch_redirect_response=False)

    def test_scheduled_task_change_page_still_works(self):
        task = ScheduledTask.objects.create(
            name="prune_jobs", interval_seconds=86400, next_run_at=timezone.now(),
        )

        response = self.client.get(reverse("admin:lncrawler_api_scheduledtask_change", args=[task.pk]))

        self.assertEqual(response.status_code, 200)


class _SyncThread:
    """Stands in for threading.Thread: start() runs the target in the calling thread."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


@patch("lncrawler_api.admin.scheduler_admin.threading.Thread", _SyncThread)
@patch("lncrawler_api.admin.scheduler_admin.connection")
class RunScanAdvisoryLockTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("scan-admin", "scan@example.com", "pw")
        self.client.force_login(user)
        self.url = reverse("admin:lncrawler_api_scheduledtask_management")

    @patch("lncrawler_api.services.harvest_service.release_scan_lock")
    @patch("lncrawler_api.services.harvest_service.run_scan_subprocess")
    @patch("lncrawler_api.services.harvest_service.acquire_scan_lock", return_value=False)
    def test_scan_is_skipped_when_the_advisory_lock_is_held(self, acquire, run_scan, release, _connection):
        with self.assertLogs("lncrawler_api.harvest", "INFO") as logs:
            response = self.client.post(self.url, {"action": "run_scan"}, follow=True)

        self.assertContains(response, "Harvest scan started in the background.")
        run_scan.assert_not_called()
        release.assert_not_called()
        self.assertTrue(any("skipped" in line for line in logs.output))

    @patch("lncrawler_api.services.harvest_service.release_scan_lock")
    @patch("lncrawler_api.services.harvest_service.run_scan_subprocess")
    @patch("lncrawler_api.services.harvest_service.acquire_scan_lock", return_value=True)
    def test_scan_runs_and_releases_the_advisory_lock(self, acquire, run_scan, release, _connection):
        self.client.post(self.url, {"action": "run_scan"})

        run_scan.assert_called_once_with()
        release.assert_called_once_with()


class WorkerTokenAdminTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("token-admin", "token@example.com", "pw")
        self.client.force_login(user)
        self.url = reverse("admin:lncrawler_api_audiobookworker_token")
        self.changelist = reverse("admin:lncrawler_api_audiobookworker_changelist")

    def test_page_creates_the_worker_and_shows_the_token_once(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(self.url, {"username": "bot"})

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        key = Token.objects.get(user__username="bot").key
        shown = self.client.get(self.url)
        self.assertContains(shown, "<code")
        self.assertContains(shown, key)
        self.assertContains(shown, "cannot be read again")
        self.assertNotContains(self.client.get(self.url), key)
        user = get_user_model().objects.get(username="bot")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.groups.filter(name=WORKER_GROUP).exists())

    def test_existing_worker_keeps_its_token_without_rotate(self):
        self.client.post(self.url, {"username": "bot"})
        key = Token.objects.get(user__username="bot").key
        self.client.get(self.url)  # the first GET shows the token, once

        response = self.client.post(self.url, {"username": "bot"}, follow=True)

        self.assertContains(response, "already exists, token unchanged (tick rotate to get a new one)")
        self.assertNotContains(response, key)
        self.assertEqual(Token.objects.get(user__username="bot").key, key)

    def test_rotate_checkbox_replaces_the_token_and_shows_the_new_one(self):
        self.client.post(self.url, {"username": "bot"})
        old = Token.objects.get(user__username="bot").key
        self.client.get(self.url)

        response = self.client.post(self.url, {"username": "bot", "rotate": "on"})

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        new = Token.objects.get(user__username="bot").key
        self.assertNotEqual(old, new)
        page = self.client.get(self.url)
        self.assertContains(page, new)
        self.assertNotContains(page, old)

    def test_reloading_the_token_page_after_a_post_does_not_rotate(self):
        self.client.post(self.url, {"username": "bot"})
        self.client.post(self.url, {"username": "bot", "rotate": "on"})
        new = Token.objects.get(user__username="bot").key
        self.assertContains(self.client.get(self.url), new)

        reloaded = self.client.get(self.url)

        self.assertEqual(Token.objects.get(user__username="bot").key, new)
        self.assertNotContains(reloaded, new)

    def test_token_page_refuses_an_existing_account_that_is_not_a_worker(self):
        human = get_user_model().objects.create_user("human", "human@example.com", "pw")
        Token.objects.create(user=human)
        key = Token.objects.get(user=human).key

        response = self.client.post(self.url, {"username": "human", "rotate": "on"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "belongs to an account that is not a worker")
        self.assertEqual(Token.objects.get(user=human).key, key)
        self.assertFalse(human.groups.filter(name=WORKER_GROUP).exists())

    def test_staff_without_add_permission_is_refused(self):
        staff = get_user_model().objects.create_user("viewer", "viewer@example.com", "pw", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="view_audiobookworker"))
        self.client.force_login(staff)

        response = self.client.post(self.url, {"username": "bot"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Token.objects.filter(user__username="bot").exists())

    def test_rotating_an_existing_worker_needs_change_permission(self):
        self.client.post(self.url, {"username": "bot"})
        self.client.get(self.url)
        old = Token.objects.get(user__username="bot").key
        self.client.force_login(make_staff("adder", "add_audiobookworker"))

        response = self.client.post(self.url, {"username": "bot", "rotate": "on"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Token.objects.get(user__username="bot").key, old)

    def test_creating_a_worker_needs_add_permission(self):
        self.client.force_login(make_staff("changer", "change_audiobookworker"))

        response = self.client.post(self.url, {"username": "newbot"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="newbot").exists())

    def test_add_permission_creates_a_worker(self):
        self.client.force_login(make_staff("adder-only", "add_audiobookworker"))

        response = self.client.post(self.url, {"username": "bot"})

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertTrue(Token.objects.filter(user__username="bot").exists())

    def test_home_offers_the_token_tool_only_with_add_permission(self):
        self.client.force_login(make_staff("changer-home", "change_audiobookworker"))
        self.assertNotContains(self.client.get(reverse("admin:index")), "Audiobook workers: new token")

        self.client.force_login(make_staff("adder-home", "add_audiobookworker"))
        self.assertContains(self.client.get(reverse("admin:index")), "Audiobook workers: new token")

    def test_changelist_has_the_new_token_button(self):
        response = self.client.get(self.changelist)

        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, "New worker token")

    def test_rotate_action_hands_the_token_to_the_page_not_to_a_message(self):
        self.client.post(self.url, {"username": "bot"})
        self.client.get(self.url)
        old = Token.objects.get(user__username="bot").key
        worker = AudiobookWorker.objects.create(worker_id="gpu-1", user=get_user_model().objects.get(username="bot"))

        response = self.client.post(
            self.changelist, {"action": "rotate_token", "_selected_action": [worker.pk]},
        )

        new = Token.objects.get(user__username="bot").key
        self.assertNotEqual(old, new)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        queued = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(queued, ["Rotated 1 token(s)."])
        page = self.client.get(self.url)
        self.assertContains(page, new)
        self.assertNotContains(page, old)
        self.assertNotContains(self.client.get(self.url), new)

    def test_rotate_action_shows_every_selected_token_on_the_page(self):
        workers = []
        for name in ("bot", "bot2"):
            self.client.post(self.url, {"username": name})
            self.client.get(self.url)
            workers.append(AudiobookWorker.objects.create(
                worker_id=name, user=get_user_model().objects.get(username=name),
            ))
        old = set(Token.objects.filter(user__username__in=["bot", "bot2"]).values_list("key", flat=True))

        response = self.client.post(
            self.changelist,
            {"action": "rotate_token", "_selected_action": [worker.pk for worker in workers]},
        )

        new = set(Token.objects.filter(user__username__in=["bot", "bot2"]).values_list("key", flat=True))
        self.assertEqual(len(new & old), 0)
        self.assertEqual([str(m) for m in get_messages(response.wsgi_request)], ["Rotated 2 token(s)."])
        page = self.client.get(self.url)
        for key in new:
            self.assertContains(page, key)
        for key in old:
            self.assertNotContains(page, key)

    def test_rotate_action_needs_change_permission(self):
        self.client.post(self.url, {"username": "bot"})
        self.client.get(self.url)
        old = Token.objects.get(user__username="bot").key
        worker = AudiobookWorker.objects.create(worker_id="gpu-2", user=get_user_model().objects.get(username="bot"))
        self.client.force_login(make_staff("viewer-rotate", "view_audiobookworker"))

        response = self.client.post(
            self.changelist, {"action": "rotate_token", "_selected_action": [worker.pk]},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Token.objects.get(user__username="bot").key, old)

    def test_rotate_action_skips_workers_without_an_account(self):
        orphan = AudiobookWorker.objects.create(worker_id="orphan", user=None)

        response = self.client.post(
            self.changelist,
            {"action": "rotate_token", "_selected_action": [orphan.pk]},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No selected worker has an account to rotate.")


class AuthorSoftDeleteAdminTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("author-admin", "author@example.com", "pw")
        self.client.force_login(user)
        self.url = reverse("admin:lncrawler_api_author_changelist")
        self.author = Author.objects.create(name="Kiyoshi")

    def test_soft_delete_then_restore(self):
        response = self.client.post(
            self.url, {"action": "soft_delete_selected", "_selected_action": [self.author.pk]}, follow=True,
        )

        self.assertContains(response, "Soft-deleted 1 author(s)")
        self.assertTrue(Author.all_objects.get(pk=self.author.pk).is_blocked)
        self.assertFalse(Author.objects.filter(pk=self.author.pk).exists())

        response = self.client.post(
            self.url, {"action": "restore_selected", "_selected_action": [self.author.pk]}, follow=True,
        )

        self.assertContains(response, "Restored 1 author(s).")
        self.assertFalse(Author.all_objects.get(pk=self.author.pk).is_blocked)
        self.assertTrue(Author.objects.filter(pk=self.author.pk).exists())

    def test_autocomplete_offers_only_visible_authors_but_the_list_keeps_deleted_ones(self):
        autocomplete = reverse("admin:autocomplete")
        params = {
            "app_label": "lncrawler_api", "model_name": "novelfromsource",
            "field_name": "authors", "term": "Kiyoshi",
        }
        self.assertEqual(len(self.client.get(autocomplete, params).json()["results"]), 1)

        self.client.post(self.url, {"action": "soft_delete_selected", "_selected_action": [self.author.pk]})

        self.assertEqual(self.client.get(autocomplete, params).json()["results"], [])
        self.assertContains(self.client.get(self.url), "Kiyoshi")

    def test_changelist_shows_the_deleted_filter(self):
        response = self.client.get(self.url)

        self.assertContains(response, "By Deleted")
