from django.core.management.base import BaseCommand
from lncrawler_api.models import Novel, WeeklyNovelView
from lncrawler_api.utils import chapter_utils
from pathlib import Path
from datetime import datetime
import time

# Process novels in small id-batches so a huge catalogue never loads at once.
CHUNK_SIZE = 200


class Command(BaseCommand):
    help = 'Compresses novels with less than 10 views this week to save disk space'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-views',
            type=int,
            default=10,
            help='Minimum weekly views threshold (novels below this will be compressed)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which novels would be compressed without actually compressing them',
        )
        parser.add_argument(
            '--nice',
            type=int,
            default=19,
            help='nice level for the 7z compressor (higher = lower priority, 0 disables)',
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=1.0,
            help='Seconds to sleep between sources so compression stays low-impact',
        )
        parser.add_argument(
            '--max-sources',
            type=int,
            default=0,
            help='Stop after compressing this many sources (0 = no limit)',
        )

    def handle(self, *args, **options):
        min_views = options['min_views']
        dry_run = options['dry_run']
        nice_level = options['nice']
        pause = max(options['sleep'], 0.0)
        max_sources = options['max_sources']

        # Get current ISO year and week number
        current_date = datetime.now()
        current_year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"

        self.stdout.write(
            self.style.SUCCESS(f'Finding novels with less than {min_views} views in week {current_year_week}')
        )

        # Novels with >= min_views this week are excluded; anything without a row
        # (or below the threshold) counts as low-traffic. Done as a subquery so we
        # never materialize a list of high-traffic ids.
        popular_ids = WeeklyNovelView.objects.filter(
            year_week=current_year_week, views__gte=min_views
        ).values('novel_id')

        base_qs = (
            Novel.objects.filter(sources__isnull=False)
            .exclude(id__in=popular_ids)
            .distinct()
            .order_by('id')
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No actual compression will be performed'))

        compressed_count = 0
        failed_count = 0
        seen_count = 0
        start_time = time.time()
        last_id = None
        stop = False

        # Page through the queryset by primary key, prefetching sources per batch.
        while not stop:
            qs = base_qs
            if last_id is not None:
                qs = qs.filter(id__gt=last_id)
            batch = list(qs.prefetch_related('sources__external_source')[:CHUNK_SIZE])
            if not batch:
                break

            for novel in batch:
                last_id = novel.id
                seen_count += 1

                if dry_run:
                    self.stdout.write(f'Would compress: {novel.title}')
                    continue

                self.stdout.write(f'Processing: {novel.title}')

                for source in novel.sources.all():
                    if max_sources and compressed_count >= max_sources:
                        stop = True
                        break

                    if not source.absolute_source_path:
                        continue

                    source_path = Path(source.absolute_source_path)
                    json_folder_path = source_path / "json"
                    compressed_file_path = source_path / "json.7z"

                    if not json_folder_path.exists():
                        # Already compressed or nothing to compress
                        continue
                    if compressed_file_path.exists():
                        continue

                    self.stdout.write(f'  Compressing source: {source.external_source.source_name}')

                    try:
                        success = chapter_utils.compress_folder_to_tar_7zip(
                            source_absolute_path=source_path,
                            json_folder="json",
                            tarfile_path=compressed_file_path,
                            nice_level=nice_level,
                        )
                        if success:
                            compressed_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(f'    Successfully compressed {source.external_source.source_name}')
                            )
                        else:
                            failed_count += 1
                            self.stdout.write(
                                self.style.ERROR(f'    Failed to compress {source.external_source.source_name}')
                            )
                    except Exception as e:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(f'    Error compressing {source.external_source.source_name}: {str(e)}')
                        )

                    # Deliberate pause: this task is for cold, rarely-read novels,
                    # so it should never compete with live traffic.
                    time.sleep(pause)

        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f'Compression completed in {elapsed:.1f} seconds.\n'
                f'Successfully compressed: {compressed_count} sources\n'
                f'Failed compressions: {failed_count} sources\n'
                f'Scanned {seen_count} low-traffic novels (< {min_views} views this week)'
            )
        )
