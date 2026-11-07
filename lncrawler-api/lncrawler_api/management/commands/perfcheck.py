import logging
import re
import time
import uuid
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, Exists, OuterRef, Subquery
from django.test import Client
from django.test.utils import CaptureQueriesContext

from lncrawler_api.models import (
    Audiobook,
    Chapter,
    LibraryFolder,
    Novel,
    NovelBookmark,
    NovelFromSource,
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
        'authenticated endpoints are always measured: without --username, --as-user '
        'or --heaviest-user a temporary user (deleted on exit) is seeded with a '
        'bookmark, history, reading list, rating and review so those pages return '
        'real data.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--repeat',
            type=int,
            default=3,
            help='Requests per endpoint; the best (fastest) warm run is reported. '
                 'The first run is the cold one and is excluded when repeat > 1',
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
        parser.add_argument(
            '--as-user',
            default=None,
            help='Force-login this existing user (no password) for the authenticated path',
        )
        parser.add_argument(
            '--heaviest-user',
            action='store_true',
            help='Force-login the user with the most bookmarks for the authenticated path',
        )
        parser.add_argument(
            '--novel',
            default=None,
            help='Slug of the novel to measure; its source with the most chapters is used. '
                 'Without it the biggest source of the whole DB is used',
        )
        parser.add_argument(
            '--no-cold',
            action='store_true',
            help='Do not clear the cache before the first request of each endpoint',
        )
        parser.add_argument(
            '--only',
            default=None,
            help='Run only endpoints whose label matches this regex (case-insensitive)',
        )
        parser.add_argument(
            '--sql',
            type=int,
            default=0,
            help='Print the N slowest queries of the best run under each endpoint',
        )
        parser.add_argument(
            '--sql-threshold',
            type=float,
            default=50,
            help='Only endpoints whose best ms reaches this get --sql output',
        )

    def handle(self, *args, **options):
        chosen = [flag for flag in ('username', 'as_user', 'heaviest_user') if options[flag]]
        if len(chosen) > 1:
            raise CommandError('Use only one of --username, --as-user, --heaviest-user.')

        if options['novel']:
            novel = Novel.objects.filter(slug=options['novel']).first()
            if novel is None:
                raise CommandError(f"No novel with slug {options['novel']!r}.")
            source = self._largest_source_of(novel)
        else:
            source = self._largest_source()
        if source is None:
            self.stderr.write('No chapter with content found; nothing to measure.')
            return

        novel = source.novel
        content_chapters = source.chapters.filter(has_content=True).order_by('chapter_id')
        chapter = content_chapters.select_related(
            'novel_from_source__novel', 'novel_from_source'
        ).first()
        last_chapter_id = (
            content_chapters.order_by('-chapter_id')
            .values_list('chapter_id', flat=True)
            .first()
        )
        chapter_total = source.chapters.count()
        mid_chapter_id = (
            source.chapters.order_by('chapter_id')
            .values_list('chapter_id', flat=True)[chapter_total // 2]
        )
        first_chapter_id = chapter.chapter_id

        self.stdout.write(
            f'novel={novel.slug} source={source.source_slug} chapters={chapter_total} '
            f"db={connection.settings_dict['NAME']}"
        )

        # Search a real 3+ character term: pg_trgm indexes only apply at >=3
        # chars, so the old query=a forced a seq scan and made search look far
        # slower than a real query. Falls back to a literal if the title has no
        # long enough word.
        search_term = quote(
            next((w for w in novel.title.split() if len(w) >= 4), 'novel')
        )
        chapters_url = f'/novels/{novel.slug}/{source.source_slug}/chapters/'
        tag = source.tags.order_by('name').values_list('name', flat=True).first()
        # Unpublished or retired audiobooks 404 and would time nothing.
        audiobook = (
            Audiobook.objects.select_related('novel')
            .filter(language='en', published=True)
            .exclude(status='retired')
            .first()
        )

        # The full read surface: home/rankings, list+search variants, the novel
        # and source pages, and the social reads. The more endpoints, the more
        # useful this is as a before/after profiling tool.
        endpoints = [
            ('home', '/novels/home/'),
            ('home?languages=en', '/novels/home/?languages=en'),
            ('list novels', '/novels/'),
            ('list novels p2', '/novels/?page=2'),
            ('list novels p200', '/novels/?page=200'),
            ('list novels?langs', '/novels/?languages=en'),
            ('search', f'/novels/search/?query={search_term}'),
            ('search popularity', f'/novels/search/?query={search_term}&sort_by=popularity'),
            ('search trending', f'/novels/search/?query={search_term}&sort_by=trending'),
            ('search rating', f'/novels/search/?query={search_term}&sort_by=rating&sort_order=desc'),
            # The sorts search_novels accepts that the lines above do not cover yet.
            ('search sort title', f'/novels/search/?query={search_term}&sort_by=title'),
            ('search sort date_added', f'/novels/search/?query={search_term}&sort_by=date_added'),
            ('search sort last_updated', f'/novels/search/?query={search_term}&sort_by=last_updated'),
            ('autocomplete tag', '/novels/autocomplete/?type=tag&query=a'),
            ('autocomplete author', '/novels/autocomplete/?type=author&query=a'),
            ('novel detail', f'/novels/{novel.slug}/'),
            ('novel reviews', f'/novels/{novel.slug}/reviews/'),
            ('novel comments', f'/novels/{novel.slug}/comments/'),
            ('source detail', f'/novels/{novel.slug}/{source.source_slug}/'),
            ('chapters list', chapters_url),
            ('chapters list last', f'{chapters_url}?page={(chapter_total + 99) // 100}'),
            ('chapters list 500', f'{chapters_url}?page_size=500'),
            ('chapters around', f'{chapters_url}?around={mid_chapter_id}'),
            ('chapters search', f'{chapters_url}?search=Chapter'),
            (
                'chapter content',
                f'/novels/{novel.slug}/{source.source_slug}/chapter/{first_chapter_id}/',
            ),
            (
                'chapter content last',
                f'/novels/{novel.slug}/{source.source_slug}/chapter/{last_chapter_id}/',
            ),
            (
                'chapter comments',
                f'/novels/{novel.slug}/{source.source_slug}/chapter/{first_chapter_id}/comments/',
            ),
            ('source gallery', f'/novels/{novel.slug}/{source.source_slug}/gallery/'),
            ('reading lists', '/reading-lists/'),
            ('reading lists search', '/reading-lists/?search=a'),
            ('chat', '/chat/'),
            ('audiobooks', '/audiobooks/'),
            ('seo home', '/seo/'),
            ('seo novel', f'/seo/novels/{novel.slug}/'),
            ('seo source', f'/seo/novels/{novel.slug}/{source.source_slug}/'),
            ('seo chapterlist', f'/seo/novels/{novel.slug}/{source.source_slug}/chapterlist/'),
            (
                'seo chapter',
                f'/seo/novels/{novel.slug}/{source.source_slug}/chapter/{first_chapter_id}/',
            ),
            ('sitemap index', '/sitemap.xml'),
            ('sitemap chapterlists', '/sitemap-chapterlists.xml'),
            ('sitemap sources', '/sitemap-sources.xml'),
        ]
        if tag is not None:
            endpoints.append(('search tag filter', f'/novels/search/?tag={quote(tag)}'))
        if audiobook is not None:
            endpoints.append(('audiobook detail', f'/audiobooks/{audiobook.novel.slug}/'))

        # Pass 1 runs the public surface anonymously. Pass 2 logs in the seeded
        # throwaway user (or the chosen one) and re-runs the same pages prefixed
        # "auth" plus the user-only ones, so both paths are always profiled.
        anonymous_client = Client(SERVER_NAME='localhost', raise_request_exception=False)
        temp_user = None
        auth_user = None
        authed_client = Client(SERVER_NAME='localhost', raise_request_exception=False)
        if options['username']:
            if authed_client.login(username=options['username'], password=options['password']):
                auth_user = get_user_model().objects.get(username=options['username'])
            else:
                self.stderr.write(
                    f"Login failed for {options['username']}; skipping the "
                    "authenticated pass."
                )
        elif options['as_user']:
            auth_user = get_user_model().objects.filter(username=options['as_user']).first()
            if auth_user is None:
                raise CommandError(f"No user named {options['as_user']!r}.")
            authed_client.force_login(auth_user)
        elif options['heaviest_user']:
            heaviest = (
                NovelBookmark.objects.values('user_id')
                .annotate(bookmarks=Count('id'))
                .order_by('-bookmarks')
                .first()
            )
            if heaviest is None:
                self.stderr.write('No user has bookmarks; skipping the authenticated pass.')
            else:
                auth_user = get_user_model().objects.get(pk=heaviest['user_id'])
                authed_client.force_login(auth_user)
        else:
            temp_user = self._seed_user(chapter)
            authed_client.force_login(temp_user)
            auth_user = temp_user

        # Looked up after the user is seeded, so the seeded list counts too.
        busiest_list_id = (
            ReadingList.objects.filter(is_public=True)
            .annotate(item_count=Count('items'))
            .order_by('-item_count')
            .values_list('id', flat=True)
            .first()
        )
        if busiest_list_id is not None:
            endpoints.append(('reading list detail', f'/reading-lists/{busiest_list_id}/'))

        auth_endpoints = []
        if auth_user is not None:
            username = auth_user.username
            user_endpoints = [
                ('my bookmarks', '/users/bookmarks/novels/'),
                ('my library folders', '/users/library/folders/'),
                ('my reading history', '/users/reading-history/'),
                ('my reading lists', '/users/reading-lists/'),
                ('my reader settings', '/users/reader-settings/'),
                ('my friends', '/friends/'),
                ('my friend requests', '/friends/requests/'),
                ('my profile', f'/users/profile/{username}/'),
                ('my library', f'/users/profile/{username}/library/'),
                ('profile reviews', f'/users/profile/{username}/reviews/'),
                ('profile lists', f'/users/profile/{username}/reading-lists/'),
                ('profile comments', f'/users/profile/{username}/comments/'),
                ('profile friends', f'/users/profile/{username}/friends/'),
                ('my jobs', '/downloader/jobs/'),
            ]
            auth_endpoints = [
                (f'auth {label}', url) for label, url in endpoints
            ] + user_endpoints

        # --only filters both passes on the label as it is printed ("auth ..." too).
        if options['only']:
            pattern = re.compile(options['only'], re.IGNORECASE)
            endpoints = [item for item in endpoints if pattern.search(item[0])]
            auth_endpoints = [item for item in auth_endpoints if pattern.search(item[0])]

        width = max(
            [len('endpoint')] + [len(label) for label, _ in endpoints + auth_endpoints]
        )
        rule = '-' * (width + 42)
        self.stdout.write(
            f"{'endpoint':<{width}} {'status':>6} {'cold ms':>8} {'best ms':>8} "
            f"{'queries':>8}  sql ms"
        )
        self.stdout.write(rule)

        # DEBUG=True makes Django log every query; that would drown the report.
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        anonymous_rows = []
        auth_rows = []
        try:
            anonymous_rows = self._run(endpoints, anonymous_client, options, width)
            if auth_endpoints:
                self.stdout.write(rule)
                auth_rows = self._run(auth_endpoints, authed_client, options, width)
        finally:
            logging.disable(previous_disable)
            if temp_user is not None:
                temp_user.delete()

        self._summary(anonymous_rows, auth_rows, width)

    def _largest_source(self):
        """The source with the most chapters that has content, found without
        counting the 20M-row chapter table.

        Per-source COUNTs would scan the whole table, so the candidates are the
        200 most viewed sources with content, and each one's highest content
        chapter_id is read with one probe of the unique (novel_from_source,
        chapter_id) index. That max chapter_id stands in for the chapter count.
        """
        has_content = Chapter.objects.filter(
            novel_from_source=OuterRef('pk'), has_content=True
        )
        candidate_ids = list(
            # DMCA novels answer 451 on chapter content.
            NovelFromSource.objects.filter(Exists(has_content), novel__is_dmca=False)
            .order_by('-total_views')
            .values_list('pk', flat=True)[:200]
        )
        last_content = (
            Chapter.objects.filter(novel_from_source=OuterRef('pk'), has_content=True)
            .order_by('-chapter_id')
            .values('chapter_id')[:1]
        )
        return (
            NovelFromSource.objects.filter(pk__in=candidate_ids)
            .select_related('novel')
            .annotate(last_chapter_id=Subquery(last_content))
            .order_by('-last_chapter_id')
            .first()
        )

    def _largest_source_of(self, novel):
        """The source of ``novel`` with the most chapters that has content."""
        return (
            novel.sources.filter(
                Exists(Chapter.objects.filter(novel_from_source=OuterRef('pk'), has_content=True))
            )
            .annotate(chapter_total=Count('chapters'))
            .order_by('-chapter_total')
            .select_related('novel')
            .first()
        )

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
        # Pad history to five distinct novels so the home page's "recommended
        # for you" path is exercised by the authenticated profile. Distinct
        # novels matter: ReadingHistory is unique per (user, novel).
        extra_novels = list(Novel.objects.exclude(id=novel.id).order_by('id')[:4])
        sources_by_novel = {
            src.novel_id: src
            for src in NovelFromSource.objects.filter(novel__in=extra_novels).order_by('id')
        }
        for extra_novel in extra_novels:
            extra_source = sources_by_novel.get(extra_novel.id)
            if extra_source is None:
                continue
            ReadingHistory.objects.create(
                user=user,
                novel=extra_novel,
                source=extra_source,
                last_read_chapter=None,
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

    def _run(self, endpoints, client, options, width):
        """Time each endpoint and print its row. Returns (label, best ms) pairs."""
        rows = []
        runs = max(1, options['repeat'])
        for label, url in endpoints:
            # Clearing the cache before the first request makes that request a
            # true cold one; warm runs then show what a cache hit costs.
            if not options['no_cold']:
                cache.clear()

            best = None
            cold_ms = None
            for index in range(runs):
                # The query log is a 9000-entry deque: once full, the capture
                # counts 0 queries, so start every request from an empty log.
                connection.queries_log.clear()
                with CaptureQueriesContext(connection) as captured:
                    start = time.perf_counter()
                    response = client.get(url)
                    elapsed_ms = (time.perf_counter() - start) * 1000

                if index == 0:
                    cold_ms = elapsed_ms
                    # The cold run only counts when there is no warm run to compare with.
                    if runs > 1:
                        continue

                if best is None or elapsed_ms < best['ms']:
                    best = {
                        'ms': elapsed_ms,
                        'status': response.status_code,
                        'queries': len(captured),
                        'sql_ms': sum(
                            float(q.get('time', 0) or 0) for q in captured.captured_queries
                        ) * 1000,
                        'captured': list(captured.captured_queries),
                    }

            self.stdout.write(
                f"{label:<{width}} {best['status']:>6} {cold_ms:>8.1f} {best['ms']:>8.1f} "
                f"{best['queries']:>8}  {best['sql_ms']:>6.1f}"
            )
            if options['sql'] and best['ms'] >= options['sql_threshold']:
                slowest = sorted(
                    best['captured'],
                    key=lambda q: float(q.get('time', 0) or 0),
                    reverse=True,
                )[:options['sql']]
                for query in slowest:
                    sql = ' '.join(query['sql'].split())[:300]
                    self.stdout.write(
                        f"    {float(query.get('time', 0) or 0) * 1000:>8.1f} ms  {sql}"
                    )
            rows.append((label, best['ms']))
        return rows

    def _summary(self, anonymous_rows, auth_rows, width):
        self.stdout.write('')
        self.stdout.write(
            f'total best ms, anonymous: {sum(ms for _, ms in anonymous_rows):.1f}'
        )
        if auth_rows:
            self.stdout.write(
                f'total best ms, auth: {sum(ms for _, ms in auth_rows):.1f}'
            )
        self.stdout.write('5 slowest endpoints:')
        for label, ms in sorted(anonymous_rows + auth_rows, key=lambda r: r[1], reverse=True)[:5]:
            self.stdout.write(f'  {label:<{width}} {ms:>8.1f} ms')
