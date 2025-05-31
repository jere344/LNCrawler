import os
import shutil
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from lncrawler_api.models import Novel

logger = logging.getLogger('lncrawler_api')


class Command(BaseCommand):
    help = 'Merge two novels by moving all sources from source novel to target novel'

    def add_arguments(self, parser):
        parser.add_argument(
            'source_slug',
            type=str,
            help='Slug of the source novel (will be deleted after merge)'
        )
        parser.add_argument(
            'target_slug',
            type=str,
            help='Slug of the target novel (will receive all sources)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually performing the merge'
        )
        parser.add_argument(
            '--move-files',
            action='store_true',
            default=True,
            help='Also move the physical source folders to the target novel folder (default: True)'
        )
        parser.add_argument(
            '--no-move-files',
            action='store_false',
            dest='move_files',
            help='Do not move the physical source folders'
        )

    def handle(self, *args, **options):
        source_slug = options['source_slug']
        target_slug = options['target_slug']
        dry_run = options['dry_run']
        move_files = options['move_files']

        if source_slug == target_slug:
            raise CommandError("Source and target novels cannot be the same")

        try:
            # Get the novels
            try:
                source_novel = Novel.objects.get(slug=source_slug)
            except Novel.DoesNotExist:
                raise CommandError(f"Source novel with slug '{source_slug}' not found")

            try:
                target_novel = Novel.objects.get(slug=target_slug)
            except Novel.DoesNotExist:
                raise CommandError(f"Target novel with slug '{target_slug}' not found")

            # Get all sources from the source novel
            sources = list(source_novel.sources.all())
            
            if not sources:
                self.stdout.write(self.style.WARNING(f"Source novel '{source_novel.title}' has no sources to merge"))
                return

            # Check for conflicting source paths
            target_sources = list(target_novel.sources.all())
            target_source_paths = {source.source_path.split(os.sep)[1] for source in target_sources if source.source_path}
            
            conflicting_sources = []
            for source in sources:
                if source.source_path and source.source_path.split(os.sep)[1] in target_source_paths:
                    conflicting_sources.append(source)
            
            if conflicting_sources:
                self.stdout.write(self.style.ERROR("Cannot merge novels: conflicting source paths detected"))
                self.stdout.write("The following sources have paths that already exist in the target novel:")
                for source in conflicting_sources:
                    self.stdout.write(f"  - {source.source_name}: {source.source_path}")
                raise CommandError(
                    f"Merge aborted due to {len(conflicting_sources)} conflicting source paths. "
                    "Please resolve these conflicts before attempting to merge."
                )

            self.stdout.write(f"Found {len(sources)} sources to merge from '{source_novel.title}' to '{target_novel.title}'")

            if dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

            # List the sources that will be moved
            for source in sources:
                self.stdout.write(f"  - {source.source_name}: {source.title}")

            if move_files and source_novel.novel_path and target_novel.novel_path:
                source_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, source_novel.novel_path)
                target_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, target_novel.novel_path)
                
                if os.path.exists(source_path):
                    self.stdout.write(f"Will move files from: {source_path}")
                    self.stdout.write(f"                  to: {target_path}")
                else:
                    self.stdout.write(self.style.WARNING(f"Source path does not exist: {source_path}"))
                    move_files = False

            if dry_run:
                return

            # Perform the merge within a transaction
            with transaction.atomic():
                # Move all sources to the target novel
                for source in sources:
                    old_novel = source.novel
                    source.novel = target_novel
                    
                    # Update source path if moving files
                    if move_files and source.source_path:
                        # Update the source path to point to the target novel's directory
                        old_path_parts = source.source_path.split(os.sep)
                        if len(old_path_parts) >= 2:
                            # Replace the novel folder name with the target novel's folder name
                            new_path_parts = [target_novel.novel_path.split(os.sep)[-1]] + old_path_parts[1:]
                            source.source_path = os.sep.join(new_path_parts)
                            
                            # Update other paths that reference the novel folder
                            if source.cover_path:
                                cover_parts = source.cover_path.split(os.sep)
                                if len(cover_parts) >= 2:
                                    source.cover_path = os.sep.join([target_novel.novel_path.split(os.sep)[-1]] + cover_parts[1:])
                            
                            if source.cover_min_path:
                                cover_min_parts = source.cover_min_path.split(os.sep)
                                if len(cover_min_parts) >= 2:
                                    source.cover_min_path = os.sep.join([target_novel.novel_path.split(os.sep)[-1]] + cover_min_parts[1:])
                            
                            if source.overview_picture_path:
                                overview_parts = source.overview_picture_path.split(os.sep)
                                if len(overview_parts) >= 2:
                                    source.overview_picture_path = os.sep.join([target_novel.novel_path.split(os.sep)[-1]] + overview_parts[1:])
                            
                            # chapter paths
                            for chapter in source.chapters.all():
                                if chapter.chapter_path:
                                    chapter_parts = chapter.chapter_path.split(os.sep)
                                    if len(chapter_parts) >= 2:
                                        chapter.chapter_path = os.sep.join([target_novel.novel_path.split(os.sep)[-1]] + chapter_parts[1:])
                                        chapter.save()


                    source.save()
                    self.stdout.write(self.style.SUCCESS(f"Moved source '{source.source_name}' to target novel"))

                # Move physical files if requested
                if move_files and source_novel.novel_path and target_novel.novel_path:
                    source_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, source_novel.novel_path)
                    target_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, target_novel.novel_path)
                    
                    if os.path.exists(source_path):
                        # Ensure target directory exists
                        os.makedirs(target_path, exist_ok=True)
                        
                        # Move each source folder
                        for item in os.listdir(source_path):
                            item_path = os.path.join(source_path, item)
                            target_item_path = os.path.join(target_path, item)
                            
                            if os.path.isdir(item_path):
                                if os.path.exists(target_item_path):
                                    self.stdout.write(self.style.WARNING(f"Target directory already exists: {target_item_path}"))
                                else:
                                    shutil.move(item_path, target_item_path)
                                    self.stdout.write(f"Moved directory: {item} to target novel folder")
                            else:
                                # Move files (like cover images, etc.)
                                if os.path.exists(target_item_path):
                                    self.stdout.write(self.style.WARNING(f"Target file already exists: {target_item_path}"))
                                else:
                                    shutil.move(item_path, target_item_path)
                                    self.stdout.write(f"Moved file: {item} to target novel folder")
                        
                        # Remove the empty source directory
                        try:
                            os.rmdir(source_path)
                            self.stdout.write(f"Removed empty source directory: {source_path}")
                        except OSError:
                            self.stdout.write(self.style.WARNING(f"Could not remove source directory (not empty?): {source_path}"))

                # Delete the source novel (now that it has no sources)
                source_novel_title = source_novel.title
                source_novel.delete()

                self.stdout.write(self.style.SUCCESS(
                    f"Successfully merged novel '{source_novel_title}' into '{target_novel.title}'. "
                    f"Moved {len(sources)} sources."
                    f"You should now run `python manage.py update_chapter_content_status` to access the chapters of the merged novel."
                ))

        except Exception as e:
            logger.exception(f"Error during novel merge: {str(e)}")
            raise CommandError(f"Error during novel merge: {str(e)}")
