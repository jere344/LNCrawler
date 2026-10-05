import logging
import time
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from lncrawler_api.models import (
    Chapter,
    LibraryFolder,
    NovelBookmark,
    NovelRating,
    ProfilePinnedNovel,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    Review,
)


class Command(BaseCommand):
    help = (
        'Time the hot read endpoints and count their DB queries. Run before/after '
        'a performance change to prove the win. No new dependencies. The '
        'authenticated endpoints are always measured: without --username a '
        'temporary user (deleted on exit) is seeded with a bookmark, history, '
        'reading list, rating and review so those pages return real data.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--repeat',
            type=int,
            default=3,
            help='Requests per endpoint; the best (fastest) run is reported',
        )
        parser.add_argument(
            '--username',
            default=None,
            help='Measure the authenticated path as this user instead of the '
                 'temporary seeded one',
        )
        parser.add_argument(
            '--password',
            default=None,
            help='Password for --username',
        )

    def handle(self, *args, **options):
        chapter = (
            Chapter.objects.filter(has_content=True)
            .select_related('novel_from_source__novel', 'novel_from_source')
            .order_by('id')
            .first()
        )
        if chapter is None:
            self.stderr.write('No chapter with content found; nothing to measure.')
            return

        source = chapter.novel_from_source
        novel = source.novel

        # The full read surface: home/rankings, list+search variants, the novel
        # and source pages, and the social reads. The more endpoints, the more
        # useful this is as a before/after profiling tool.
        endpoints = [
            ('home', '/novels/home/'),
            ('home?languages=en', '/novels/home/?languages=en'),
            ('featured random', '/novels/featured/random/'),
            ('list novels', '/novels/'),
            ('list novels p2', '/novels/?page=2'),
            ('list novels?langs', '/novels/?languages=en'),
            ('search', '/novels/search/?query=a'),
            ('search popularity', '/novels/search/?query=a&sort_by=popularity'),
            ('search trending', '/novels/search/?sort_by=trending'),
            ('search rating', '/novels/search/?sort_by=rating&sort_order=desc'),
            ('autocomplete tag', '/novels/autocomplete/?type=tag&query=a'),
            ('autocomplete author', '/novels/autocomplete/?type=author&query=a'),
            ('novel detail', f'/novels/{novel.slug}/'),
            ('novel reviews', f'/novels/{novel.slug}/reviews/'),
            ('novel comments', f'/novels/{novel.slug}/comments/'),
            ('source detail', f'/novels/{novel.slug}/{source.source_slug}/'),
            ('chapters list', f'/novels/{novel.slug}/{source.source_slug}/chapters/'),
            (
                'chapter content',
                f'/novels/{novel.slug}/{source.source_slug}/chapter/{chapter.chapter_id}/',
            ),
            ('source gallery', f'/novels/{novel.slug}/{source.source_slug}/gallery/'),
            ('reading lists', '/reading-lists/'),
            ('reading lists search', '/reading-lists/?search=a'),
        ]

        # Pass 1 runs the public surface anonymously. Pass 2 logs in the seeded
        # throwaway user (or --username) and re-runs the same pages prefixed
        # "auth" plus the user-only ones, so both paths are always profiled.
        anonymous_client = Client(SERVER_NAME='localhost')
        temp_user = None
        authed_client = Client(SERVER_NAME='localhost')
        if options['username']:
            logged_in = authed_client.login(
                username=options['username'], password=options['password']
            )
            if logged_in:
                username = options['username']
            else:
                self.stderr.write(
                    f"Login failed for {options['username']}; skipping the "
                    "authenticated pass."
                )
        else:
            temp_user = self._seed_user(chapter)
            authed_client.force_login(temp_user)
            username = temp_user.username
            logged_in = True

        auth_endpoints = []
        if logged_in:
            auth_endpoints = [
                (f'auth {label}', url) for label, url in endpoints
            ] + [
                ('my bookmarks', '/users/bookmarks/novels/'),
                ('my library folders', '/users/library/folders/'),
                ('my reading history', '/users/reading-history/'),
                ('my reading lists', '/users/reading-lists/'),
                ('my reviews', '/users/reviews/'),
                ('my friends', '/friends/'),
                ('my friend requests', '/friends/requests/'),
                ('my profile', f'/users/profile/{username}/'),
                ('my library', f'/users/profile/{username}/library/'),
                ('profile reviews', f'/users/profile/{username}/reviews/'),
                ('profile lists', f'/users/profile/{username}/reading-lists/'),
            ]

        self.stdout.write(
            f"{'endpoint':<24} {'status':>6} {'best ms':>8} {'queries':>8}  sql ms"
        )
        self.stdout.write('-' * 64)

        # DEBUG=True makes Django log every query; that would drown the report.
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            self._run(endpoints, anonymous_client, options)
            if auth_endpoints:
                self.stdout.write('-' * 64)
                self._run(auth_endpoints, authed_client, options)
        finally:
            logging.disable(previous_disable)
            if temp_user is not None:
                temp_user.delete()

    def _seed_user(self, chapter):
        """Create a throwaway user with just enough rows for the authenticated
        pages to return data. Caller deletes it when done."""
        user_model = get_user_model()
        suffix = uuid.uuid4().hex[:8]
        user = user_model.objects.create(
            username=f'perfcheck_{suffix}',
            email=f'perfcheck_{suffix}@example.invalid',
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])

        source = chapter.novel_from_source
        novel = source.novel
        folder = LibraryFolder.objects.create(user=user, name='Perf folder')
        NovelBookmark.objects.create(user=user, novel=novel, folder=folder)
        ReadingHistory.objects.create(
            user=user, novel=novel, source=source, last_read_chapter=chapter
        )
        reading_list = ReadingList.objects.create(
            user=user, title='Perf list', is_public=True
        )
        ReadingListItem.objects.create(reading_list=reading_list, novel=novel)
        ProfilePinnedNovel.objects.create(user=user, novel=novel)
        NovelRating.objects.create(user=user, novel=novel, rating=5)
        Review.objects.create(
            user=user, novel=novel, title='Perf review', content='perf', rating=5
        )
        return user

    def _run(self, endpoints, client, options):
        for label, url in endpoints:
            best = None
            queries = None
            sql_ms = None
            status = None

            for _ in range(max(1, options['repeat'])):
                with CaptureQueriesContext(connection) as captured:
                    start = time.perf_counter()
                    response = client.get(url)
                    elapsed_ms = (time.perf_counter() - start) * 1000

                if best is None or elapsed_ms < best:
                    best = elapsed_ms
                    queries = len(captured)
                    sql_ms = sum(
                        float(q.get('time', 0) or 0) for q in captured.captured_queries
                    ) * 1000
                    status = response.status_code

            self.stdout.write(
                f'{label:<24} {status:>6} {best:>8.1f} {queries:>8}  {sql_ms:>6.1f}'
            )
