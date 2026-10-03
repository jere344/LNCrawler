import logging
import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from lncrawler_api.models import Chapter


class Command(BaseCommand):
    help = (
        'Time the hot read endpoints and count their DB queries. Run before/after '
        'a performance change to prove the win. No new dependencies.'
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
            help='Log in as this user to measure the authenticated path',
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

        endpoints = [
            ('home', '/novels/home/'),
            ('home?languages=en', '/novels/home/?languages=en'),
            ('list novels', '/novels/'),
            ('search', '/novels/search/?query=a'),
            ('novel detail', f'/novels/{novel.slug}/'),
            ('source detail', f'/novels/{novel.slug}/{source.source_slug}/'),
            ('chapters list', f'/novels/{novel.slug}/{source.source_slug}/chapters/'),
            (
                'chapter content',
                f'/novels/{novel.slug}/{source.source_slug}/chapter/{chapter.chapter_id}/',
            ),
        ]

        client = Client(SERVER_NAME='localhost')
        if options['username']:
            ok = client.login(
                username=options['username'], password=options['password']
            )
            if not ok:
                self.stderr.write(
                    f"Login failed for {options['username']}; measuring anonymously."
                )

        self.stdout.write(
            f"{'endpoint':<20} {'status':>6} {'best ms':>8} {'queries':>8}  sql ms"
        )
        self.stdout.write('-' * 60)

        # DEBUG=True makes Django log every query; that would drown the report.
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            self._run(endpoints, client, options)
        finally:
            logging.disable(previous_disable)

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
                f'{label:<20} {status:>6} {best:>8.1f} {queries:>8}  {sql_ms:>6.1f}'
            )
