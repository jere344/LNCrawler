# filepath: c:\Users\Jeremy\Desktop\lncrawler-reborn\lncrawler-api\lncrawler_api\services\downloader_service.py
import os
import sys
import threading
import time
import logging
import importlib.util
import multiprocessing
from pathlib import Path
import django
from ..utils import lncrawler_paths

from django.conf import settings

# Configure logger
logger = logging.getLogger('lncrawler_api')

class DownloaderService:
    """
    Service that interfaces with the PythonApiBot to handle novel search and download.
    Uses Django's Job model to persist state across requests.
    """

    @staticmethod
    def _setup_django():
        """Set up Django environment in a subprocess"""
        try:
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lncrawler_api.settings')
            django.setup()
        except Exception as e:
            logger.error(f"Failed to setup Django in subprocess: {str(e)}")
            raise
    
    @staticmethod
    def _configure_apibot_logger():
        """Configure a separate logger for the PythonApiBot"""
        apibot_logger = logging.getLogger('apibot')
        
        # Remove any existing handlers to avoid duplicate logs
        if apibot_logger.handlers:
            for handler in apibot_logger.handlers:
                apibot_logger.removeHandler(handler)
        
        return apibot_logger
    
    @staticmethod
    def _import_python_api_bot():
        """Import the PythonApiBot class from the lightnovel crawler package"""
        try:
            # Configure apibot logger
            apibot_logger = DownloaderService._configure_apibot_logger()
            
            # Find the parent directory path
            base_dir = Path(settings.BASE_DIR).parent
            lncrawl_dir = base_dir / "dipudb-lightnovel-crawler"
            bot_path = lncrawl_dir / "lncrawl" / "bots" / "python_api" / "__init__.py"
            
            if not bot_path.exists():
                apibot_logger.error(f"Could not find PythonApiBot module at {bot_path}")
                raise ImportError(f"Could not find PythonApiBot module at {bot_path}")
            
            # Add the directory to Python path so imports work properly
            lncrawl_parent = str(lncrawl_dir.parent)
            if lncrawl_parent not in sys.path:
                sys.path.insert(0, lncrawl_parent)
        
            # Also add the actual package directory
            crawler_pkg_dir = str(lncrawl_dir)
            if crawler_pkg_dir not in sys.path:
                sys.path.insert(0, crawler_pkg_dir)
                
            # Set the working directory to the crawler package directory
            os.chdir(crawler_pkg_dir)
            
            # Dynamically import the module
            spec = importlib.util.spec_from_file_location("python_api", bot_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            
            # Get the PythonApiBot class
            PythonApiBot = module.PythonApiBot
            
            # Inject the logger into the PythonApiBot class
            original_init = PythonApiBot.__init__
            
            def new_init(self, *args, **kwargs):
                original_init(self, *args, **kwargs)
                self.logger = apibot_logger
            
            PythonApiBot.__init__ = new_init
            
            return PythonApiBot
        except Exception as e:
            apibot_logger.error(f"Failed to import PythonApiBot: {str(e)}")
            raise ImportError(f"Could not import PythonApiBot: {str(e)}")
    
    @staticmethod
    def _run_search_process(job_id, query):
        """
        Run novel search in a separate process
        This is executed in a new process to avoid blocking the main thread
        """
        try:
            # Get the base directory for the crawler package
            base_dir = Path(settings.BASE_DIR).parent
            lncrawl_dir = base_dir / "dipudb-lightnovel-crawler"
            
            # Set the working directory to the crawler package directory
            os.chdir(str(lncrawl_dir))
            
            # Add to Python path
            sys.path.insert(0, str(lncrawl_dir.parent))
            sys.path.insert(0, str(lncrawl_dir))
            
            # Setup Django in the subprocess
            DownloaderService._setup_django()
            
            # Import the Job model here to avoid circular imports
            from ..models import Job
            
            # Get the job
            job = Job.objects.get(id=job_id)
            job.update_status(Job.STATUS_SEARCHING)
            # Import bot class
            PythonApiBot = DownloaderService._import_python_api_bot()
            # Create bot instance
            bot = PythonApiBot()
            bot.logger = DownloaderService._configure_apibot_logger()
            response = bot.start()
            
            if response["status"] != "ready":
                job.update_status(Job.STATUS_FAILED, f"Failed to start bot: {response.get('message', 'Unknown error')}")
                return
            
            # Initialize app session
            response = bot.init_app()
            if response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to initialize app: {response.get('message', 'Unknown error')}")
                return
            
            # Start a background thread to periodically update progress
            stop_monitoring = threading.Event()
            
            def monitor_search_progress():
                while not stop_monitoring.is_set():
                    try:
                        status = bot.get_search_status()
                        if status["status"] == "success":
                            progress = status.get("progress", 0)
                            total = status.get("total_items", job.total_items or 1)
                            job.update_progress(progress, total)
                            
                            # Check if search completed
                            if status.get("search_completed", False) and not status.get("search_in_progress", False):
                                break
                    except Exception as e:
                        logger.error(f"Error monitoring search progress: {str(e)}")
                    time.sleep(2)

            # Start monitoring thread before starting search
            monitor_thread = threading.Thread(target=monitor_search_progress)
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Start search - now non-blocking
            response = bot.start_search(query)
            if response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Search failed: {response.get('message', 'Unknown error')}")
                stop_monitoring.set()
                return
            
            try:
                # Wait for search to complete (monitoring thread will detect completion)
                monitor_thread.join(timeout=300)  # 5 minute timeout
                
                if not stop_monitoring.is_set():
                    stop_monitoring.set()
                
                # Get search results
                results = bot.get_search_results()
                if results["status"] != "success":
                    job.update_status(Job.STATUS_FAILED, f"Failed to get search results: {results.get('message', 'Unknown error')}")
                    return
                
                # Update job with search results
                job.update_search_results(results)
                job.update_status(Job.STATUS_SEARCH_COMPLETED)
                
            finally:
                # Ensure monitoring thread is stopped
                if not stop_monitoring.is_set():
                    stop_monitoring.set()
                    monitor_thread.join(timeout=5.0)
                
                # Clean up
                try:
                    bot.destroy_app()
                except Exception as e:
                    logger.error(f"Error destroying bot: {str(e)}")
        
        except Exception as e:
            logger.exception(f"Error in search process: {str(e)}")
            try:
                # Setup Django again to ensure we can access the models
                DownloaderService._setup_django()
                from ..models import Job
                job = Job.objects.get(id=job_id)
                job.update_status(Job.STATUS_FAILED, f"Search process error: {str(e)}")
            except Exception:
                pass
    
    @staticmethod
    def _run_download_process(job_id, novel_url):
        """
        Run novel download in a separate process
        This is executed in a new process to avoid blocking the main thread
        """
        logger.debug(f"Running download process for job ID: {job_id}")
        try:
            # Get the base directory for the crawler package
            base_dir = Path(settings.BASE_DIR).parent
            lncrawl_dir = base_dir / "dipudb-lightnovel-crawler"
            
            # Set the working directory to the crawler package directory
            os.chdir(str(lncrawl_dir))
            
            # Add to Python path
            sys.path.insert(0, str(lncrawl_dir.parent))
            sys.path.insert(0, str(lncrawl_dir))
            
            # Setup Django in the subprocess
            logger.debug("Setting up Django in subprocess")
            DownloaderService._setup_django()
            logger.debug("Django setup complete")
            
            # Import the Job model here to avoid circular imports
            from ..models import Job
            
            # Get the job
            job = Job.objects.get(id=job_id)
            logger.debug(f"Job found: {job}")
            job.update_status(Job.STATUS_DOWNLOADING)
            
            # Import bot class
            PythonApiBot = DownloaderService._import_python_api_bot()
            
            # Create bot instance
            bot = PythonApiBot()
            bot.logger = DownloaderService._configure_apibot_logger()
            logger.debug("PythonApiBot instance created")
            response = bot.start()
            logger.debug(f"Bot started: {response}")
            
            if response["status"] != "ready":
                job.update_status(Job.STATUS_FAILED, f"Failed to start bot: {response.get('message', 'Unknown error')}")
                return
            
            # Initialize app session
            response = bot.init_app()
            if response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to initialize app: {response.get('message', 'Unknown error')}")
                return
            
            # Set the novel URL directly
            logger.debug(f"Setting novel URL: {novel_url}")
            response = bot.set_novel_url(novel_url)
            if response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to set novel URL: {response.get('message', 'Unknown error')}")
                return
        
            # Store selected novel info
            job.selected_novel = {
                "title": response.get("novel_title", "Unknown title"),
                "volumes": response.get("volumes", 0),
                "chapters": response.get("chapters", 0),
                "url": response.get("novel_url", "")
            }
            job.save(update_fields=['selected_novel', 'updated_at'])
            
            # Set custom output path
            custom_output_path = lncrawler_paths.get_novel_output_path(
                source=job.selected_novel["url"].split("/")[2],
                novel=job.selected_novel["title"]
            )
            
            output_path_response = bot.set_output_path(custom_output_path)
            if output_path_response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to set output path: {output_path_response.get('message', 'Unknown error')}")
                return
            
            # Select all chapters
            logger.debug("Selecting all chapters")
            response = bot.select_chapters("first", 10) #toremove : use all
                
            if response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to select chapters: {response.get('message', 'Unknown error')}")
                return
            
            # Set total chapters
            total_chapters = response.get("chapters_selected", 0)
            job.update_progress(0, total_chapters)
            logger.debug(f"Selected {total_chapters} chapters")
            
            # Start a background thread to periodically update progress
            stop_monitoring = threading.Event()
            
            def monitor_progress():
                while not stop_monitoring.is_set():
                    try:
                        status = bot.get_download_status()
                        logger.debug(f"Download status: {status}")
                        if status["status"] == "success":
                            progress = status.get("progress", 0)
                            total = status.get("total_chapters", job.total_items or 1)
                            job.update_progress(progress, total)
                            
                            # Check if download completed
                            if status.get("download_completed", False):
                                logger.debug("Download completed")
                                break
                        
                    except Exception as e:
                        logger.error(f"Error monitoring download progress: {str(e)}")
                    time.sleep(2)
            
            # Start monitoring thread before starting download
            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.daemon = True
            monitor_thread.start()
            
            try:
                # Start download - always use JSON format
                logger.debug("Starting download in apibot")
                response = bot.start_download(["json"], pack_by_volume=False)
                logger.debug(f"Download response: {response}")

                if response["status"] != "success":
                    job.update_status(Job.STATUS_FAILED, f"Download failed: {response.get('message', 'Unknown error')}")
                    stop_monitoring.set()
                    return
                
                logger.debug("Download initiated successfully")
                
                # Wait for download to complete (monitoring thread will detect completion)
                monitor_thread.join(timeout=1800)  # 30 minute timeout
                
                if monitor_thread.is_alive():
                    logger.warning("Download monitor thread timed out")
                    stop_monitoring.set()
                
                # Check final status
                status = bot.get_download_status()
                logger.debug(f"Final download status: {status}")
                
                if not status.get("download_completed", False):
                    job.update_status(Job.STATUS_FAILED, "Download did not complete within the timeout period")
                    return
                
                # Get download results
                results = bot.get_download_results()
                logger.debug(f"Download results: {results}")
                if results["status"] != "success":
                    job.update_status(Job.STATUS_FAILED, f"Failed to get download results: {results.get('message', 'Unknown error')}")
                    return
                
                # Update job with download results
                job.update_download_results(
                    output_path=results.get("output_path", ""),
                    output_files=results.get("archived_outputs", [])
                )
                job.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
                logger.debug(f"Download process completed successfully for job {job_id}")
                
            finally:
                # Ensure monitoring thread is stopped
                if not stop_monitoring.is_set():
                    stop_monitoring.set()
                    monitor_thread.join(timeout=5.0)
                
                # Clean up
                try:
                    bot.destroy_app()
                except Exception as e:
                    logger.error(f"Error destroying bot: {str(e)}")
                
        except Exception as e:
            logger.exception(f"Error in download process: {str(e)}")
            try:
                # Setup Django again to ensure we can access the models
                DownloaderService._setup_django()
                from ..models import Job
                job = Job.objects.get(id=job_id)
                job.update_status(Job.STATUS_FAILED, f"Download process error: {str(e)}")
            except Exception:
                pass
    
    @classmethod
    def start_search(cls, query):
        """
        Start a search for novels with the given query
        Returns a job object that can be used to track progress
        """
        # Create a new job
        from ..models import Job
        job = Job.objects.create(
            status=Job.STATUS_CREATED,
            query=query
        )
        
        # Start search process
        process = multiprocessing.Process(
            target=cls._run_search_process,
            args=(job.id, query)
        )
        process.daemon = True
        process.start()
        
        # Store the process ID
        job.job_pid = process.pid
        job.save(update_fields=['job_pid'])
        
        return job
    
    @classmethod
    def get_search_status(cls, job_id):
        """Get the current status of the search"""
        from ..models import Job

        try:
            job = Job.objects.get(id=job_id)
            return {
                'status': job.status,
                'status_display': job.get_status_display(),
                'search_completed': job.status == Job.STATUS_SEARCH_COMPLETED,
                'progress': job.progress,
                'total_items': job.total_items,
                'progress_percentage': job.get_progress_percentage(),
                'has_results': job.search_results is not None and len(job.search_results) > 0,
                'error': job.error_message,
            }
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }
    
    @classmethod
    def get_search_results(cls, job_id):
        """Get the results of the search"""
        from ..models import Job

        try:
            job = Job.objects.get(id=job_id)
            
            if job.status == Job.STATUS_FAILED:
                return {
                    'status': 'error',
                    'message': job.error_message or 'Search failed',
                }
            
            if job.status != Job.STATUS_SEARCH_COMPLETED:
                return {
                    'status': 'error',
                    'message': 'Search not completed',
                    'current_status': job.get_status_display(),
                }
            
            # Return the search results
            return job.search_results
            
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }
    
    @classmethod
    def start_download(cls, job_id, novel_index=0, source_index=0):
        """
        Start downloading a novel
        
        Args:
            job_id: The ID of the job with search results
            novel_index: Index of the novel from search results to download
            source_index: Index of the source for the selected novel
            
        Returns:
            Updated job object
        """
        from ..models import Job
            
        try:
            job = Job.objects.get(id=job_id)
            
            if job.status != Job.STATUS_SEARCH_COMPLETED:
                return {
                    'status': 'error',
                    'message': 'Cannot start download: search not completed',
                    'current_status': job.get_status_display(),
                }
            
            # Get the novel URL from search results
            search_results = job.search_results
            novel_url = ""
            
            # Check if this is a direct novel URL
            if "direct_novel" in search_results and search_results["direct_novel"]:
                novel_url = search_results["novel_url"]
            else:
                # Extract URL from search results using indices
                try:
                    novel_url = search_results["results"][novel_index]["sources"][source_index]["url"]
                except (KeyError, IndexError):
                    return {
                        'status': 'error',
                        'message': 'Invalid novel or source index',
                    }
            
            if not novel_url:
                return {
                    'status': 'error',
                    'message': 'Could not determine novel URL',
                }
            
            # Start download process with the direct URL
            process = multiprocessing.Process(
                target=cls._run_download_process,
                args=(job.id, novel_url)
            )
            process.daemon = True
            logger.debug(f"Using novel URL: {novel_url}")
            process.start()
            logger.debug(f"Started download process with PID: {process.pid}")
            
            # Store the process ID
            job.job_pid = process.pid
            job.save(update_fields=['job_pid'])
            
            return {
                'status': 'success',
                'message': 'Download started',
                'job_id': str(job.id)
            }
            
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }
    
    @classmethod
    def get_download_status(cls, job_id):
        """Get the current status of the download"""
        from ..models import Job

        try:
            job = Job.objects.get(id=job_id)
            
            if job.status == Job.STATUS_FAILED:
                return {
                    'status': 'error',
                    'message': job.error_message or 'Download failed',
                }
            
            return {
                'status': 'success',
                'job_status': job.status,
                'status_display': job.get_status_display(),
                'download_completed': job.status == Job.STATUS_DOWNLOAD_COMPLETED,
                'progress': job.progress,
                'total_chapters': job.total_items,
                'progress_percentage': job.get_progress_percentage(),
                'selected_novel': job.selected_novel,
            }
            
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }
    
    @classmethod
    def get_download_results(cls, job_id):
        """Get the results of the download"""
        from ..models import Job

        try:
            job = Job.objects.get(id=job_id)
            
            if job.status == Job.STATUS_FAILED:
                return {
                    'status': 'error',
                    'message': job.error_message or 'Download failed',
                }
            
            if job.status != Job.STATUS_DOWNLOAD_COMPLETED:
                return {
                    'status': 'error',
                    'message': 'Download not completed',
                    'current_status': job.get_status_display(),
                }
            
            return {
                'status': 'success',
                'output_path': job.output_path,
                'output_files': job.output_files,
                'selected_novel': job.selected_novel,
            }
            
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }
    
    @classmethod
    def cancel_job(cls, job_id):
        """Cancel a running job"""
        from ..models import Job

        try:
            job = Job.objects.get(id=job_id)
            
            # Try to terminate the process if it exists
            if job.job_pid:
                try:
                    os.kill(job.job_pid, 9)  # SIGKILL
                except OSError:
                    # Process might not exist anymore
                    pass
            
            job.update_status(Job.STATUS_FAILED, "Job cancelled by user")
            
            return {
                'status': 'success',
                'message': 'Job cancelled',
            }
            
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }