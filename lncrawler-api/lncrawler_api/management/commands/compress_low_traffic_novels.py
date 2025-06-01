from django.core.management.base import BaseCommand
from lncrawler_api.models import Novel, WeeklyNovelView
from lncrawler_api.utils import chapter_utils
from pathlib import Path
from datetime import datetime
import time

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

    def handle(self, *args, **options):
        min_views = options['min_views']
        dry_run = options['dry_run']
        
        # Get current ISO year and week number
        current_date = datetime.now()
        current_year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
        
        self.stdout.write(
            self.style.SUCCESS(f'Finding novels with less than {min_views} views in week {current_year_week}')
        )
        
        # Get all novels and their weekly view counts
        novels_to_compress = []
        
        # Get all novels that have sources
        novels_with_sources = Novel.objects.filter(sources__isnull=False).distinct()
        
        for novel in novels_with_sources:
            # Get weekly views for current week
            try:
                weekly_view = WeeklyNovelView.objects.get(
                    novel=novel,
                    year_week=current_year_week
                )
                weekly_views = weekly_view.views
            except WeeklyNovelView.DoesNotExist:
                weekly_views = 0
            
            # If views are below threshold, add to compression list
            if weekly_views < min_views:
                novels_to_compress.append(novel)
        
        self.stdout.write(
            self.style.SUCCESS(f'Found {len(novels_to_compress)} novels to compress')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No actual compression will be performed'))
            for novel in novels_to_compress:
                self.stdout.write(f'Would compress: {novel.title}')
            return
        
        # Initialize counters
        compressed_count = 0
        failed_count = 0
        start_time = time.time()
        
        for novel in novels_to_compress:
            self.stdout.write(f'Processing: {novel.title}')
            
            # Process each source of the novel
            for source in novel.sources.all():
                if source.absolute_source_path:
                    source_path = Path(source.absolute_source_path)
                    json_folder_path = source_path / "json"
                    compressed_file_path = source_path / "json.7z"
                    
                    # Only compress if json folder exists and compressed file doesn't exist
                    if json_folder_path.exists() and not compressed_file_path.exists():
                        self.stdout.write(f'  Compressing source: {source.external_source.source_name}')
                        
                        try:
                            success = chapter_utils.compress_folder_to_tar_7zip(
                                source_absolute_path=source_path,
                                json_folder="json",
                                tarfile_path=compressed_file_path
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
                    elif compressed_file_path.exists():
                        self.stdout.write(f'    Source {source.external_source.source_name} already compressed')
                    else:
                        self.stdout.write(f'    No json folder found for {source.external_source.source_name}')
        
        # Final summary
        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f'Compression completed in {elapsed:.1f} seconds.\n'
                f'Successfully compressed: {compressed_count} sources\n'
                f'Failed compressions: {failed_count} sources\n'
                f'Processed {len(novels_to_compress)} novels with less than {min_views} views this week'
            )
        )
