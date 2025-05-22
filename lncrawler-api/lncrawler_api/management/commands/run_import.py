import os
import glob
import shutil
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from lncrawler_api.models import NovelFromSource

logger = logging.getLogger('lncrawler_api')

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
                    
                    # Make sure we're at least 2 folders deep
                    parent_of_novel = os.path.dirname(os.path.dirname(source_folder))
                    if parent_of_novel == import_folder:
                        # This means the structure is import_folder/novel/source/meta.json which is correct
                        self.stdout.write(f"Processing: {novel_folder_name}/{source_folder_name}")
                        

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
                            'source': novel_from_source.source_name
                        })
                        
                        self.stdout.write(self.style.SUCCESS(
                            f"Successfully imported '{novel_from_source.title}' from {novel_from_source.source_name}"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Skipping {meta_file_path} - not at least 2 folders deep from import folder"
                        ))
                        
                except Exception as e:
                    logger.error(f"Error importing {meta_file_path}: {str(e)}")
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
