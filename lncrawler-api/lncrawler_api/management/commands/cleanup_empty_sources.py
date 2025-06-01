from django.core.management.base import BaseCommand
from lncrawler_api.models import NovelFromSource
from django.db import transaction
import time

class Command(BaseCommand):
    help = 'Deletes NovelFromSource instances that have insufficient chapters with content based on percentage threshold'

    def add_arguments(self, parser):
        parser.add_argument(
            '--percentage',
            type=float,
            default=0.0,
            help='Delete sources with less than this percentage of chapters with content (default: 0.0 for sources with no content)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting anything',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Do not prompt for confirmation before deleting',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of sources to delete in each batch',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        no_input = options['no_input']
        batch_size = options['batch_size']
        percentage_threshold = options['percentage']
        
        # Validate percentage
        if percentage_threshold < 0 or percentage_threshold > 100:
            self.stdout.write(self.style.ERROR('Percentage must be between 0 and 100'))
            return
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Finding NovelFromSource instances with less than {percentage_threshold}% chapters with content...'
            )
        )
        
        # Find all NovelFromSource instances that meet the criteria
        sources_to_delete = []
        
        for source in NovelFromSource.objects.all():
            total_chapters = source.chapters.count()
            
            # Skip sources with no chapters at all
            if total_chapters == 0:
                continue
            
            content_chapters = source.chapters.filter(has_content=True).count()
            content_percentage = (content_chapters / total_chapters) * 100
            
            if content_percentage < percentage_threshold:
                sources_to_delete.append({
                    'source': source,
                    'total_chapters': total_chapters,
                    'content_chapters': content_chapters,
                    'content_percentage': content_percentage
                })
        
        if not sources_to_delete:
            self.stdout.write(
                self.style.SUCCESS(
                    f'No sources found with less than {percentage_threshold}% chapters with content. Nothing to delete.'
                )
            )
            return
        
        self.stdout.write(
            self.style.WARNING(
                f'Found {len(sources_to_delete)} sources with less than {percentage_threshold}% chapters with content:'
            )
        )
        
        # Display what will be deleted
        for item in sources_to_delete:
            source = item['source']
            total = item['total_chapters']
            content = item['content_chapters']
            percentage = item['content_percentage']
            
            self.stdout.write(
                f'  - {source.title} ({source.external_source.source_name}) - '
                f'{content}/{total} chapters with content ({percentage:.1f}%)'
            )
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'DRY RUN: Would delete {len(sources_to_delete)} sources with less than {percentage_threshold}% content'
                )
            )
            return
        
        # Confirmation prompt
        if not no_input:
            confirm = input(
                f'\nAre you sure you want to delete {len(sources_to_delete)} sources with less than {percentage_threshold}% content chapters? '
                f'This will also delete their source folders. (yes/no): '
            )
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Deletion cancelled.'))
                return
        
        # Delete sources in batches
        start_time = time.time()
        deleted_count = 0
        
        for i in range(0, len(sources_to_delete), batch_size):
            batch = sources_to_delete[i:i+batch_size]
            
            with transaction.atomic():
                for item in batch:
                    source = item['source']
                    try:
                        source_title = source.title
                        source_name = source.external_source.source_name
                        content_percentage = item['content_percentage']
                        source.delete()  # This will also delete the source folder
                        deleted_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Deleted: {source_title} ({source_name}) - {content_percentage:.1f}% content'
                            )
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error deleting {source.title}: {e}')
                        )
            
            # Progress update
            progress = min(i + batch_size, len(sources_to_delete))
            self.stdout.write(
                self.style.SUCCESS(f'Progress: {progress}/{len(sources_to_delete)} sources processed')
            )
        
        # Final summary
        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f'Cleanup completed in {elapsed:.1f} seconds.\n'
                f'Successfully deleted {deleted_count} sources with less than {percentage_threshold}% content chapters.'
            )
        )
