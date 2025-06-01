import os
import glob
import shutil
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from lncrawler_api.models import NovelFromSource

logger = logging.getLogger('lncrawler_api')


def legacy_source_cleanup(source_folder):
    """
    Clean up legacy files in the source folder.
    This function removes any files that are now unused or redundant
    """
    if not os.path.isdir(source_folder):
        logger.warning(f"Source folder does not exist: {source_folder}")
        return
    legacy_files = [
        os.path.join(source_folder, 'cover.min.jpg'),
        os.path.join(source_folder, 'cover.sm.jpg'),
    ]
    for legacy_file in legacy_files:
        if os.path.exists(legacy_file):
            try:
                os.remove(legacy_file)
                logger.info(f"Removed legacy file: {legacy_file}")
            except Exception as e:
                logger.error(f"Failed to remove legacy file {legacy_file}: {str(e)}")
    
    # if we have both a source_folder/json folder and a source_folder/json.7z, we can remove json.7z
    json_folder = os.path.join(source_folder, 'json')
    json_7z_file = os.path.join(source_folder, 'json.7z')
    if os.path.isdir(json_folder) and os.path.exists(json_7z_file):
        try:
            os.remove(json_7z_file)
            logger.info(f"Removed legacy json.7z file: {json_7z_file}")
        except Exception as e:
            logger.error(f"Failed to remove legacy json.7z file {json_7z_file}: {str(e)}")

def legacy_novel_cleanup(novel_folder):
    """
    Clean up legacy files in the novel folder.
    This function removes any files that are now unused or redundant
    """
    if not os.path.isdir(novel_folder):
        logger.warning(f"novel folder does not exist: {novel_folder}")
        return
    legacy_files = [
        os.path.join(novel_folder, 'stats.json'),
    ]
    for legacy_file in legacy_files:
        if os.path.exists(legacy_file):
            try:
                os.remove(legacy_file)
                logger.info(f"Removed legacy file: {legacy_file}")
            except Exception as e:
                logger.error(f"Failed to remove legacy file {legacy_file}: {str(e)}")


class Command(BaseCommand):
    help = 'Import novels from the import folder specified in settings.IMPORT_FOLDER_PATH'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['copy', 'move'],
            default='move',
            help='Action to perform with source files: copy (copy to library), or move (move to library)'
        )
        parser.add_argument(
            '--path',
            type=str,
            help='Override the import folder path defined in settings'
        )

    def handle(self, *args, **options):
        import_results = {
            'successful': [],
            'failed': [],
            'file_operations': []
        }

        # Get import folder path (from settings or override)
        import_folder = options.get('path') or settings.IMPORT_FOLDER_PATH
        if not import_folder:
            raise CommandError("IMPORT_FOLDER_PATH is not defined in settings and no path was provided")

        import_action = options['action']
        
        self.stdout.write(self.style.SUCCESS(f"Starting import from: {import_folder}"))
        self.stdout.write(f"Import action: {import_action}")
        
        try:
            if not os.path.isdir(import_folder):
                raise CommandError(f"Directory not found: {import_folder}")
            
            # Find meta.json files that are at least 2 folders deep
            meta_files = glob.glob(os.path.join(import_folder, '**/*/meta.json'), recursive=True)
            
            if not meta_files:
                self.stdout.write(self.style.WARNING("No meta.json files found at least 2 folders deep"))
                return
                
            self.stdout.write(f"Found {len(meta_files)} meta.json files to process")
            
            for meta_file_path in meta_files:
                try:
                    # Get paths
                    source_folder = os.path.dirname(meta_file_path)
                    source_folder_name = os.path.basename(source_folder)
                    novel_folder_name = os.path.basename(os.path.dirname(source_folder))
                    
                    # Make sure we're 2 folders deep
                    if os.path.dirname(os.path.dirname(source_folder)) == import_folder:
                        # This means the structure is import_folder/novel/source/meta.json which is correct
                        self.stdout.write(f"Processing: {novel_folder_name}/{source_folder_name}")

                        # Clean up legacy files if necessary
                        legacy_novel_cleanup(novel_folder=os.path.dirname(source_folder))
                        legacy_source_cleanup(source_folder=source_folder)

                        library_path = settings.LNCRAWL_OUTPUT_PATH
                        library_novel_path = os.path.join(library_path, novel_folder_name)
                        os.makedirs(library_novel_path, exist_ok=True)
                        target_source_path = os.path.join(library_novel_path, source_folder_name)
                        
                        if os.path.exists(target_source_path):
                            self.stdout.write(self.style.WARNING(f"Target directory already exists: {target_source_path}"))
                            import_results['file_operations'].append({
                                'source': source_folder,
                                'target': target_source_path,
                                'action': import_action,
                                'status': 'skipped',
                                'reason': 'Target already exists'
                            })
                        else:
                            if import_action == 'copy':
                                shutil.copytree(source_folder, target_source_path)
                                self.stdout.write(f"Copied {source_folder} to {target_source_path}")
                            else:  # move
                                shutil.move(source_folder, target_source_path)
                                self.stdout.write(f"Moved {source_folder} to {target_source_path}")
                                # delete the parent folder if it's empty mow
                                if not os.listdir(os.path.dirname(source_folder)):
                                    os.rmdir(os.path.dirname(source_folder))
                                    self.stdout.write(f"Removed empty directory: {os.path.dirname(source_folder)}")
                            
                            import_results['file_operations'].append({
                                'source': source_folder,
                                'target': target_source_path,
                                'action': import_action,
                                'status': 'success'
                            })
                            
                            # Update meta_file_path to the new location
                            meta_file_path = os.path.join(target_source_path, 'meta.json')
                        
                        # Import the novel
                        novel_from_source = NovelFromSource.from_meta_json(meta_file_path)
                        
                        import_results['successful'].append({
                            'path': meta_file_path,
                            'title': novel_from_source.title,
                            'source': novel_from_source.external_source.source_name
                        })
                        
                        self.stdout.write(self.style.SUCCESS(
                            f"Successfully imported '{novel_from_source.title}' from {novel_from_source.external_source.source_name}"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Skipping {meta_file_path} - not at least 2 folders deep from import folder"
                        ))
                        
                except Exception as e:
                    logger.error(f"Error importing {meta_file_path}")
                    logger.exception(e)
                    import_results['failed'].append({
                        'path': meta_file_path,
                        'error': str(e)
                    })
                    self.stdout.write(self.style.ERROR(f"Error importing {meta_file_path}: {str(e)}"))
            
            # Summary
            self.stdout.write(self.style.SUCCESS(
                f"Import completed: {len(import_results['successful'])} successful, {len(import_results['failed'])} failed"
            ))
            
        except Exception as e:
            logger.exception(f"Error during import: {str(e)}")
            raise CommandError(f"Error during import: {str(e)}")
