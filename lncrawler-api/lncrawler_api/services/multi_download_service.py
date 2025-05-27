# This is unused code, but it is kept here for reference in case the startup time of the crawler is getting too long
# It's an attempt to use a process pool to handle search and download tasks instead of a new process for each task.
# Especially useful if you intend to run the crawler from a very slow disk and with a limited number of processes/ram
import os
import sys
import threading
import time
import logging
import importlib.util
import multiprocessing
import queue
from pathlib import Path
import traceback
import django
from ..utils import lncrawler_paths

from django.conf import settings

# Configure logger
logger = logging.getLogger('lncrawler_api')

# Functions moved outside of the class for pickling compatibility
def _import_python_api_bot():
    """Import the PythonApiBot class from the lightnovel crawler package"""
    try:
        # Configure apibot logger
        apibot_logger = logging.getLogger('apibot')
        
        # Find the parent directory path
        base_dir = Path(settings.BASE_DIR).parent
        lncrawl_dir = base_dir / "dipudb-lncrawler-jere344-patches"
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
        logger.error(f"Failed to import PythonApiBot: {str(e)}")
        raise ImportError(f"Could not import PythonApiBot: {str(e)}")

def _refresh_connection():
    """
    Refresh the database connection
    This is useful in a subprocess to ensure the connection is valid
    """
    from django.db import connection
    try:
        connection.close()
        connection.connect()
        connection.ensure_connection()
        logger.debug("Database connection refreshed successfully")
    except Exception as e:
        logger.error(f"Failed to refresh database connection: {str(e)}")
        raise

def _import_novel_to_database(output_path, job):
    """
    Import the downloaded novel into the database using the meta.json file
    """
    try:
        # Find meta.json file in the output directory
        meta_json_path = os.path.join(output_path, 'meta.json')
        if not os.path.exists(meta_json_path):
            logger.error(f"meta.json file not found at {meta_json_path}")
            return False, "meta.json file not found in the output directory"
        
        # Import the model
        from ..models import NovelFromSource
        
        # Use the NovelFromSource's method to import from meta.json
        novel = NovelFromSource.from_meta_json(meta_json_path)
        
        if novel:
            job.output_slug = novel.novel.slug + "/" + novel.source_slug
            job.save(update_fields=['output_slug', 'updated_at'])
            
            logger.info(f"Successfully imported novel: {novel.title} from {novel.source_name}")
            return True, f"Successfully imported novel: {novel.title} from {novel.source_name}"
        else:
            return False, "Failed to import novel from meta.json"
    
    except Exception as e:
        logger.exception(f"Error importing novel to database: {str(e)}")
        return False, f"Error importing novel to database: {str(e)}"

# Standalone worker function that can be passed to multiprocessing.Process
def worker_process_func(task_queue):
    """Worker process function that handles search and download tasks"""
    logger = logging.getLogger('apibot')
    bot = None
    
    try:
        # Setup the environment
        # Get the base directory for the crawler package
        base_dir = Path(settings.BASE_DIR).parent
        lncrawl_dir = base_dir / "dipudb-lncrawler-jere344-patches"
        
        # Set the working directory to the crawler package directory
        os.chdir(str(lncrawl_dir))
        
        # Add to Python path
        sys.path.insert(0, str(lncrawl_dir.parent))
        sys.path.insert(0, str(lncrawl_dir))
        
        # Setup Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_project.settings')
        django.setup()
        _refresh_connection()
        
        # Import and initialize PythonApiBot
        PythonApiBot = _import_python_api_bot()
        bot = PythonApiBot()
        bot.logger = logger
        
        # Start the bot
        response = bot.start()
        if response["status"] != "ready":
            raise Exception(f"Failed to start bot: {response.get('message', 'Unknown error')}")
    
        logger.info("Worker process ready and waiting for tasks")
        
        # Handle only one task then exit to prevent memory leaks
        try:
            # Wait for a task
            task = task_queue.get(timeout=300)  # 5 minute timeout
            
            if task is None:  # Shutdown signal
                return
                
            task_type = task.get('type')
            
            if task_type == 'search':
                _handle_search_task(bot, task)
            elif task_type == 'download':
                _handle_download_task(bot, task)
            else:
                logger.error(f"Unknown task type: {task_type}")
            
            # Exit after completing the task to prevent memory leaks
            logger.info("Task completed, worker process exiting to prevent memory leaks")
            
        except queue.Empty:
            # Timeout - exit
            logger.info("Worker process timeout, exiting")
        except Exception as e:
            logger.error(f"Error in worker loop: {str(e)}")
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Worker process initialization error: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        # Cleanup
        try:
            if bot:
                bot.destroy_app()
        except Exception as e:
            logger.error(f"Error cleaning up worker: {str(e)}")

def _handle_search_task(bot, task):
    """Handle a search task"""
    job_id = task['job_id']
    query = task['query']
    
    try:
        from ..models import Job
        job = Job.objects.get(id=job_id)
        job.update_status(Job.STATUS_SEARCHING)
        
        # Initialize app session
        response = bot.init_app()
        if response["status"] != "success":
            job.update_status(Job.STATUS_FAILED, f"Failed to initialize app: {response.get('message', 'Unknown error')}")
            return
        
        # Start monitoring thread
        stop_monitoring = threading.Event()
        
        def monitor_search_progress():
            while not stop_monitoring.is_set():
                try:
                    status = bot.get_search_status()
                    if status["status"] == "success":
                        progress = status.get("progress", 0)
                        total = status.get("total_items", job.total_items or 1)
                        job.update_progress(progress, total)
                        
                        if status.get("search_completed", False) and not status.get("search_in_progress", False):
                            break
                except Exception as e:
                    logger.error(f"Error monitoring search progress: {str(e)}")
                time.sleep(2)
            job.update_progress(0, 0)

        monitor_thread = threading.Thread(target=monitor_search_progress)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Start search
        response = bot.start_search(query)
        if response["status"] != "success":
            job.update_status(Job.STATUS_FAILED, f"Search failed: {response.get('message', 'Unknown error')}")
            stop_monitoring.set()
            return
        
        try:
            monitor_thread.join(timeout=300)
            
            if not stop_monitoring.is_set():
                stop_monitoring.set()
            
            # Get search results
            results = bot.get_search_results()
            if results["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to get search results: {results.get('message', 'Unknown error')}")
                return
            
            job.update_search_results(results)
            job.update_status(Job.STATUS_SEARCH_COMPLETED)
            
        finally:
            if not stop_monitoring.is_set():
                stop_monitoring.set()
                monitor_thread.join(timeout=5.0)
            
    except Exception as e:
        logger.exception(f"Error in search task: {str(e)}")
        try:
            from ..models import Job
            job = Job.objects.get(id=job_id)
            job.update_status(Job.STATUS_FAILED, f"Search process error: {str(e)}")
        except Exception:
            pass

def _handle_download_task(bot, task):
    """Handle a download task"""
    job_id = task['job_id']
    novel_url = task['novel_url']
    
    try:
        from ..models import Job
        job = Job.objects.get(id=job_id)
        job.update_status(Job.STATUS_DOWNLOADING)
        
        # Initialize app session
        response = bot.init_app()
        if response["status"] != "success":
            job.update_status(Job.STATUS_FAILED, f"Failed to initialize app: {response.get('message', 'Unknown error')}")
            return
        
        # Set the novel URL
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
        response = bot.select_chapters("all")
        if response["status"] != "success":
            job.update_status(Job.STATUS_FAILED, f"Failed to select chapters: {response.get('message', 'Unknown error')}")
            return
        
        total_chapters = response.get("chapters_selected", 0)
        job.update_progress(0, total_chapters)
        
        # Start monitoring thread
        stop_monitoring = threading.Event()
        
        def monitor_progress():
            while not stop_monitoring.is_set():
                try:
                    status = bot.get_download_status()
                    if status["status"] == "success":
                        progress = status.get("progress", 0)
                        total = status.get("total_chapters", job.total_items or 1)
                        job.update_progress(progress, total)
                        
                        if status.get("download_completed", False):
                            break
                    
                except Exception as e:
                    logger.error(f"Error monitoring download progress: {str(e)}")
                time.sleep(2)
        
        monitor_thread = threading.Thread(target=monitor_progress)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        try:
            # Start download
            response = bot.start_download(["json"], pack_by_volume=False)
            if response["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Download failed: {response.get('message', 'Unknown error')}")
                stop_monitoring.set()
                return
            
            monitor_thread.join(timeout=1800)
            
            if monitor_thread.is_alive():
                stop_monitoring.set()
            
            # Check final status
            status = bot.get_download_status()
            if not status.get("download_completed", False):
                job.update_status(Job.STATUS_FAILED, "Download did not complete within the timeout period")
                return
            
            # Get download results
            results = bot.get_download_results()
            if results["status"] != "success":
                job.update_status(Job.STATUS_FAILED, f"Failed to get download results: {results.get('message', 'Unknown error')}")
                return
            
            output_path = results.get("output_path", "")
            output_files = results.get("archived_outputs", [])
            
            job.update_download_results(
                output_path=output_path,
                output_files=output_files
            )
            
            # Auto-import the novel to the database
            success, message = _import_novel_to_database(output_path, job)
            
            if success:
                job.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
                job.import_message = message
                job.save(update_fields=['import_message'])
            else:
                job.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
                job.import_message = f"Download completed but import failed: {message}"
                job.save(update_fields=['import_message'])
            
        finally:
            if not stop_monitoring.is_set():
                stop_monitoring.set()
                monitor_thread.join(timeout=5.0)
            
    except Exception as e:
        logger.exception(f"Error in download task: {str(e)}")
        try:
            from ..models import Job
            job = Job.objects.get(id=job_id)
            job.update_status(Job.STATUS_FAILED, f"Download process error: {str(e)}")
        except Exception:
            pass

class ProcessPool:
    """
    Manages a pool of worker processes for handling search and download tasks
    """
    
    def __init__(self, pool_size=2):
        self.pool_size = pool_size
        self.workers = []
        self.task_queues = []
        self.result_queue = multiprocessing.Queue()
        self.current_worker = 0
        self._start_workers()
    
    def _start_workers(self):
        """Start the worker processes"""
        self.workers.clear()
        self.task_queues.clear()
        
        for i in range(self.pool_size):
            self._start_single_worker(i)
            
        logger.info(f"Started {self.pool_size} worker processes")
    
    def _start_single_worker(self, worker_index):
        """Start a single worker process"""
        task_queue = multiprocessing.Queue()
        worker_process = multiprocessing.Process(
            target=worker_process_func,
            args=(task_queue,),
            name=f"WorkerProcess-{worker_index+1}"
        )
        worker_process.daemon = True
        worker_process.start()
        
        # Ensure we have the right number of slots
        while len(self.workers) <= worker_index:
            self.workers.append(None)
            self.task_queues.append(None)
        
        self.workers[worker_index] = worker_process
        self.task_queues[worker_index] = task_queue
        
        logger.info(f"Started worker process {worker_index+1} (PID: {worker_process.pid})")
    
    def _check_and_replace_dead_workers(self):
        """Check for dead workers and replace them"""
        for i in range(self.pool_size):
            worker = self.workers[i]
            if worker is None or not worker.is_alive():
                if worker is not None:
                    logger.warning(f"Worker {i+1} (PID: {worker.pid}) is dead, replacing...")
                    # Clean up the dead worker
                    if worker.is_alive():
                        worker.terminate()
                    worker.join(timeout=1.0)
                else:
                    logger.warning(f"Worker {i+1} slot is empty, creating new worker...")
                
                # Start a new worker
                self._start_single_worker(i)
    
    def submit_task(self, task):
        """Submit a task to the next available worker"""
        # Check for dead workers and replace them
        self._check_and_replace_dead_workers()
        
        # Find an alive worker
        attempts = 0
        while attempts < self.pool_size:
            worker = self.workers[self.current_worker]
            task_queue = self.task_queues[self.current_worker]
            
            if worker and worker.is_alive():
                try:
                    task_queue.put(task)
                    logger.info(f"Submitted task to worker {self.current_worker+1}")
                    
                    # Round-robin to next worker
                    self.current_worker = (self.current_worker + 1) % self.pool_size
                    return True
                except Exception as e:
                    logger.error(f"Failed to submit task to worker {self.current_worker+1}: {str(e)}")
            
            # Try next worker
            self.current_worker = (self.current_worker + 1) % self.pool_size
            attempts += 1
        
        logger.error("No alive workers available to handle task")
        return False

class DownloaderService:
    """
    Service that interfaces with the PythonApiBot to handle novel search and download.
    Uses Django's Job model to persist state across requests.
    """
    
    _process_pool = None
    _pool_lock = threading.Lock()

    @classmethod
    def get_process_pool(cls):
        """Get or create the process pool (singleton)"""
        print("Getting process pool")
        if cls._process_pool is None:
            with cls._pool_lock:
                if cls._process_pool is None:
                    try:
                        cls._process_pool = ProcessPool(pool_size=2)
                    except Exception as e:
                        print(f"Failed to create process pool: {str(e)}")
                        print(traceback.format_exc())
                        logger.error(f"Failed to create process pool: {str(e)}")
        return cls._process_pool
    
    @staticmethod
    def _import_novel_to_database(output_path, job):
        return _import_novel_to_database(output_path, job)
    
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
        
        # Submit search task to process pool
        pool = cls.get_process_pool()
        task = {
            'type': 'search',
            'job_id': job.id,
            'query': query
        }
        
        if pool.submit_task(task):
            pass
        else:
            job.update_status(Job.STATUS_FAILED, "Failed to submit search task to worker pool")
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
    def start_direct_download(cls, novel_url, job=None):
        if not novel_url:
            return {
                'status': 'error',
                'message': 'Could not determine novel URL',
            }
        
        if not job:
            from ..models import Job
            job = Job.objects.create(
                status=Job.STATUS_SEARCH_COMPLETED,
                query="Direct Download"
            )

        # Submit download task to process pool
        pool = cls.get_process_pool()
        task = {
            'type': 'download',
            'job_id': job.id,
            'novel_url': novel_url
        }
        
        if pool.submit_task(task):
            return {
                'status': 'success',
                'message': 'Download started',
                'job_id': str(job.id)
            }
        else:
            job.update_status(Job.STATUS_FAILED, "Failed to submit download task to worker pool")
            return {
                'status': 'error',
                'message': 'Failed to submit download task to worker pool',
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
            
            # if no direct url passed, get the selected novel URL
            novel_url = ""
            try:
                novel_url = job.search_results["results"][novel_index]["sources"][source_index]["url"]
            except (KeyError, IndexError):
                return {
                    'status': 'error',
                    'message': 'Invalid novel or source index',
                }
            
            return cls.start_direct_download(novel_url, job)
            
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
            
            result = {
                'status': 'success',
                'output_path': job.output_path,
                'output_files': job.output_files,
                'selected_novel': job.selected_novel,
                'output_slug': job.output_slug
            }
            
            # Include import message if available
            if hasattr(job, 'import_message') and job.import_message:
                result['import_message'] = job.import_message
                
            return result
            
        except Job.DoesNotExist:
            return {
                'status': 'error',
                'message': f'Job with ID {job_id} not found',
            }
