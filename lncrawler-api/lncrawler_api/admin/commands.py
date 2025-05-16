from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.conf import settings
import os
import glob
import shutil
import logging
from ..models import NovelFromSource

def handle_meta_json_import(modeladmin, request, form):
    if form.is_valid():
        meta_json_path = form.cleaned_data['meta_json_path']
        
        try:
            if not os.path.isfile(meta_json_path):
                raise ValueError(f"File not found: {meta_json_path}")
            
            novel_from_source = NovelFromSource.from_meta_json(meta_json_path)
            
            modeladmin.message_user(
                request,
                f"Successfully imported '{novel_from_source.title}' from {novel_from_source.source_name}"
            )
            
        except Exception as e:
            modeladmin.message_user(
                request,
                f"Error importing meta.json file: {str(e)}",
                level='ERROR'
            )
            
        return HttpResponseRedirect(reverse('admin:lncrawler_api_novel_changelist'))

def handle_mass_import(modeladmin, request, form):
    import_results = {
        'successful': [],
        'failed': [],
        'file_operations': []
    }
    
    logger = logging.getLogger('lncrawler_api')
    
    if form.is_valid():
        root_directory = form.cleaned_data['root_directory']
        import_action = form.cleaned_data['import_action']
        
        try:
            if not os.path.isdir(root_directory):
                raise ValueError(f"Directory not found: {root_directory}")
            
            meta_files = glob.glob(os.path.join(root_directory, '**/meta.json'), recursive=True)
            
            for meta_file_path in meta_files:
                try:
                    source_folder = os.path.dirname(meta_file_path)
                    source_folder_name = os.path.basename(source_folder)
                    novel_folder_name = os.path.basename(os.path.dirname(source_folder))
                    
                    if import_action in ('copy', 'move'):
                        library_novel_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, novel_folder_name)
                        os.makedirs(library_novel_path, exist_ok=True)
                        target_source_path = os.path.join(library_novel_path, source_folder_name)
                        
                        if os.path.exists(target_source_path):
                            logger.warning(f"Target directory already exists: {target_source_path}")
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
                                logger.info(f"Copied {source_folder} to {target_source_path}")
                            else:
                                shutil.move(source_folder, target_source_path)
                                logger.info(f"Moved {source_folder} to {target_source_path}")
                            
                            import_results['file_operations'].append({
                                'source': source_folder,
                                'target': target_source_path,
                                'action': import_action,
                                'status': 'success'
                            })
                            
                            meta_file_path = os.path.join(target_source_path, 'meta.json')
                    
                    novel_from_source = NovelFromSource.from_meta_json(meta_file_path)
                    
                    import_results['successful'].append({
                        'path': meta_file_path,
                        'title': novel_from_source.title,
                        'source': novel_from_source.source_name
                    })
                except Exception as e:
                    logger.error(f"Error importing {meta_file_path}: {str(e)}")
                    import_results['failed'].append({
                        'path': meta_file_path,
                        'error': str(e)
                    })
            
            modeladmin.message_user(
                request,
                f"Import completed: {len(import_results['successful'])} successful, {len(import_results['failed'])} failed"
            )
            
            context = {
                'form': form,
                'opts': modeladmin.model._meta,
                'title': 'Mass Import Results',
                'results': import_results,
                'total_found': len(meta_files),
                'import_action': import_action
            }
            return render(request, 'admin/mass_import_results.html', context)
            
        except Exception as e:
            logger.exception(f"Error during mass import: {str(e)}")
            modeladmin.message_user(
                request,
                f"Error during mass import: {str(e)}",
                level='ERROR'
            )
            return HttpResponseRedirect(reverse('admin:lncrawler_api_novel_changelist'))
