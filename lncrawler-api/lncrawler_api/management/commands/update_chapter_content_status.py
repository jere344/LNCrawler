from django.core.management.base import BaseCommand
from lncrawler_api.models import Chapter
from django.db import transaction
import time

class Command(BaseCommand):
    help = 'Updates the has_content field for all existing chapters'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of chapters to process in each batch',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        # Get total count for progress tracking
        total_chapters = Chapter.objects.count()
        self.stdout.write(self.style.SUCCESS(f'Found {total_chapters} chapters to process'))
        
        # Initialize counters
        processed = 0
        has_content_count = 0
        no_content_count = 0
        
        # Process chapters in batches to avoid memory issues
        start_time = time.time()
        
        # Get all chapter IDs for batching
        chapter_ids = list(Chapter.objects.values_list('id', flat=True))
        
        for i in range(0, len(chapter_ids), batch_size):
            batch_ids = chapter_ids[i:i+batch_size]
            
            # Use a transaction for each batch
            with transaction.atomic():
                chapters = Chapter.objects.filter(id__in=batch_ids)
                
                for chapter in chapters:
                    # Check and update the has_content status
                    has_content = chapter.check_has_content()
                    
                    if has_content:
                        has_content_count += 1
                    else:
                        no_content_count += 1
                    
                    processed += 1
                    
                    # Print progress every 100 chapters
                    if processed % 100 == 0 or processed == total_chapters:
                        elapsed = time.time() - start_time
                        progress = (processed / total_chapters) * 100
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Progress: {processed}/{total_chapters} ({progress:.1f}%) - '
                                f'With content: {has_content_count}, Without content: {no_content_count} - '
                                f'Elapsed: {elapsed:.1f}s'
                            )
                        )
        
        # Final summary
        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed updating {processed} chapters in {elapsed:.1f} seconds.\n'
                f'Chapters with content: {has_content_count}\n'
                f'Chapters without content: {no_content_count}'
            )
        )
