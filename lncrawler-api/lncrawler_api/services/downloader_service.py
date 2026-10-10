import os
import sys
import threading
import time
import logging
from pathlib import Path
import django
from ..utils import lncrawler_paths
from ..utils import chapter_utils

from django.conf import settings

# Configure logger
logger = logging.getLogger('lncrawler_api')

# Set once the crawler package has been added to sys.path.
_crawler_package_loaded = False


def _load_app():
    """Add the lncrawler-crawler package to sys.path and return its App class."""
    global _crawler_package_loaded
    crawler_dir = Path(settings.BASE_DIR).parent / "lncrawler-crawler"
    for path in (crawler_dir.parent, crawler_dir):
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)
    if not _crawler_package_loaded:
        if not (crawler_dir / "lncrawl" / "core" / "app.py").exists():
            raise ImportError(f"Could not find lncrawler-crawler package at {crawler_dir}")
        _crawler_package_loaded = True
    from lncrawl.core.app import App
    return App


def _is_expected_crawler_error(exc) -> bool:
    """True for failures that are not bugs in our code: source-level
    ``LNException``s (novel unavailable: removed from the site, no downloads,
    bad URL) and transport errors (HTTP 5xx / network / IO) that exhausted their
    retries. Chapter-level failures are classified inside the crawler, so an
    exception reaching the download loop is either one of these or a real bug."""
    try:
        from lncrawl.core.exeptions import LNException, RetryErrorGroup
    except Exception:
        return False
    return isinstance(exc, (LNException, *RetryErrorGroup))


def _poll_download_progress(job, app, phase, total_chapters):
    """Push one progress reading from the crawler/app onto the job.

    Before the chapter list exists the crawler reports its own TOC progress in
    ``progress_unit`` (volumes for EPUB sources); afterwards progress is the
    number of downloaded chapters. ``phase`` is a mutable ``{"chapters": bool}``
    flipped once ``get_novel_info()`` has run.
    """
    if phase.get("chapters"):
        job.update_progress(app.progress, total_chapters, "chapters")
    else:
        crawler = app.crawler
        job.update_progress(
            getattr(crawler, "progress", 0),
            getattr(crawler, "progress_total", 0),
            getattr(crawler, "progress_unit", "chapters"),
        )


def _format_search_results(app):
    """Convert App.search_results into the shape stored on Job.search_results."""
    results = []
    for novel_index, novel in enumerate(app.search_results):
        sources = []
        for source_index, source in enumerate(novel.get("novels", [])):
            entry = {"index": source_index, "url": source.get("url", "")}
            if source.get("info"):
                entry["info"] = source["info"]
            sources.append(entry)
        results.append({
            "index": novel_index,
            "title": novel.get("title", ""),
            "sources": sources,
        })
    return results


class DownloaderService:
    """
    Service that drives the lncrawler-crawler library to handle novel search and
    download. Uses Django's Job model to persist state across requests.
    """

    @staticmethod
    def _setup_django():
        """Set up Django environment in a subprocess"""
        try:
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_project.settings')
            django.setup()
            DownloaderService.refresh_connection()
        except Exception as e:
            logger.error(f"Failed to setup Django in subprocess: {str(e)}")
            raise

    @staticmethod
    def refresh_connection():
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

    @classmethod
    def _inject_existing_chapters(cls, app, novel_url):
        """Hand the crawler the chapters/metadata already stored for this source.

        Sources with an expensive table of contents (EPUB volumes) use this to
        rebuild their chapter list without re-fetching archives that have
        already been downloaded; only new volumes are fetched.

        Returns the matched ``NovelFromSource`` (or ``None``) so the caller can
        keep writing to the directory that source already lives in.
        """
        from ..models import NovelFromSource
        try:
            novel_source = (
                NovelFromSource.objects.filter(source_url=novel_url).first()
                or NovelFromSource.objects.filter(
                    source_url=novel_url.rstrip("/")
                ).first()
            )
            if novel_source is None:
                return None
            app.crawler.existing_chapters = [
                {"id": ch.chapter_id, "url": ch.url, "title": ch.title}
                for ch in novel_source.chapters.order_by("chapter_id")
            ]
            app.crawler.existing_meta = {
                "title": novel_source.title,
                "authors": ", ".join(a.name for a in novel_source.authors.all()),
                "language": novel_source.language,
                "cover_url": novel_source.cover_url,
                "synopsis": novel_source.synopsis,
                "novelupdates_url": novel_source.novelupdates_url,
            }
            logger.debug(
                "Injected %s existing chapters for %s",
                len(app.crawler.existing_chapters),
                novel_url,
            )
            return novel_source
        except Exception as e:
            logger.debug("Could not load previous chapters for %s: %s", novel_url, e)
            return None

    @staticmethod
    def _run_search_process(job_id, query):
        """
        Run novel search in a background thread
        """
        job = None
        app = None
        try:
            App = _load_app()
            DownloaderService._setup_django()

            from ..models import Job
            job = Job.objects.get(id=job_id)
            job.update_status(Job.STATUS_SEARCHING)

            app = App()
            app.user_input = query
            app.prepare_search()

            # A direct novel URL needs no search.
            if app.crawler is not None:
                job.update_search_results({
                    "status": "success",
                    "direct_novel": True,
                    "novel_url": app.crawler.novel_url,
                })
                job.update_status(Job.STATUS_SEARCH_COMPLETED)
                return

            total = len(app.crawler_links) or 1
            job.update_progress(0, total)

            stop_monitoring = threading.Event()

            def monitor_progress():
                try:
                    while not stop_monitoring.is_set():
                        job.update_progress(app.progress, total)
                        time.sleep(2)
                finally:
                    # Threads get their own DB connection; close it so a
                    # long-lived worker does not accumulate Postgres sessions.
                    from django.db import connection
                    connection.close()

            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.daemon = True
            monitor_thread.start()

            try:
                app.search_novel()
            finally:
                stop_monitoring.set()
                monitor_thread.join(timeout=5.0)

            # Respect a cancel request that arrived while searching.
            if Job.objects.filter(pk=job.id, status=Job.STATUS_FAILED).exists():
                return

            job.update_search_results({
                "status": "success",
                "results": _format_search_results(app),
            })
            job.update_progress(0, 0)
            job.update_status(Job.STATUS_SEARCH_COMPLETED)

        except Exception as e:
            logger.exception(f"Error in search process: {str(e)}")
            try:
                DownloaderService._setup_django()
                from ..models import Job
                job = Job.objects.get(id=job_id)
                job.update_status(Job.STATUS_FAILED, f"Search process error: {str(e)}")
            except Exception:
                pass
        finally:
            if app is not None:
                try:
                    app.destroy()
                except Exception:
                    pass

    @staticmethod
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

                logger.info(f"Successfully imported novel: {novel.title} from {novel.external_source.source_name}")
                return True, f"Successfully imported novel: {novel.title} from {novel.external_source.source_name}"
            else:
                return False, "Failed to import novel from meta.json"

        except Exception as e:
            logger.exception(f"Error importing novel to database: {str(e)}")
            return False, f"Error importing novel to database: {str(e)}"

    @staticmethod
    def _run_download_process(job_id, novel_url):
        """
        Run novel download in a background thread
        """
        logger.debug(f"Running download process for job ID: {job_id}")
        app = None
        try:
            App = _load_app()
            DownloaderService._setup_django()

            from ..models import Job
            job = Job.objects.get(id=job_id)
            job.update_status(Job.STATUS_DOWNLOADING)

            app = App()
            app.user_input = novel_url
            app.prepare_search()

            if app.crawler is None:
                job.update_status(Job.STATUS_FAILED, f"No crawler found for URL: {novel_url}")
                return

            # Give the crawler the previous chapter list/metadata (if any) so
            # sources with expensive tables of contents (EPUB volumes) can
            # reuse them instead of re-fetching every archive on update.
            existing_source = DownloaderService._inject_existing_chapters(app, novel_url)

            # Monitor both phases: the crawler's TOC/volume phase (before
            # get_novel_info returns, when chapters are not known yet) and the
            # chapter download phase afterwards.
            phase = {"chapters": False}
            total_chapters = 0
            stop_monitoring = threading.Event()

            def monitor_progress():
                try:
                    while not stop_monitoring.is_set():
                        _poll_download_progress(job, app, phase, total_chapters)
                        time.sleep(2)
                finally:
                    # Threads get their own DB connection; close it so a
                    # long-lived worker does not accumulate Postgres sessions.
                    from django.db import connection
                    connection.close()

            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.daemon = True
            monitor_thread.start()

            try:
                # Fetch novel info (title, chapters, volumes). This is slow for
                # EPUB sources that must fetch every volume archive.
                app.get_novel_info()

                job.selected_novel = {
                    "title": app.crawler.novel_title or "Unknown title",
                    "volumes": len(app.crawler.volumes),
                    "chapters": len(app.crawler.chapters),
                    "url": app.crawler.novel_url,
                }
                job.save(update_fields=['selected_novel', 'updated_at'])

                # Set custom output path. An existing source keeps writing to
                # the folder it already lives in (important after a merge, so
                # an update does not re-split it into the old name). Otherwise
                # derive it from the crawler's canonical source name so mirror
                # domains handled by the same crawler share one directory.
                existing_path = (
                    existing_source.absolute_source_path
                    if existing_source is not None
                    else None
                )
                if existing_path and os.path.isdir(existing_path):
                    custom_output_path = existing_path
                else:
                    source_host = (
                        getattr(app.crawler, "source_name", "")
                        or job.selected_novel["url"].split("/")[2]
                    )
                    custom_output_path = lncrawler_paths.get_novel_output_path(
                        source=source_host,
                        novel=job.selected_novel["title"]
                    )

                # If the path exists and is compressed, decompress it
                if os.path.exists(custom_output_path):
                    potential_compressed_path = os.path.join(custom_output_path, "json.7z")
                    if os.path.exists(potential_compressed_path):
                        chapter_utils.extract_tar_7zip_folder(tar_file_path=Path(potential_compressed_path))

                os.makedirs(custom_output_path, exist_ok=True)
                app.output_path = custom_output_path

                # Chapter list is known now; switch the monitor to chapters.
                total_chapters = len(app.chapters)
                phase["chapters"] = True
                job.update_progress(0, total_chapters, "chapters")
                logger.debug(f"Selected {total_chapters} chapters")

                # Download all chapters (JSON format only)
                app.start_download()
            finally:
                stop_monitoring.set()
                monitor_thread.join(timeout=5.0)

            output_path = app.output_path

            job.update_download_results(output_path=output_path, output_files=[])

            # Auto-import the novel to the database
            logger.debug(f"Attempting to import novel from {output_path}")
            success, message = DownloaderService._import_novel_to_database(output_path, job)

            # Respect a cancel request that arrived while downloading.
            if Job.objects.filter(pk=job.id, status=Job.STATUS_FAILED).exists():
                return

            if not success:
                # An unusable meta.json (e.g. missing title) means nothing reached
                # the library, so the job failed rather than merely warning.
                job.import_message = message
                job.save(update_fields=['import_message'])
                job.update_status(Job.STATUS_FAILED, f"Download completed but import failed: {message}")
                return

            job.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
            job.import_message = message
            job.save(update_fields=['import_message'])

            logger.debug(f"Download process completed successfully for job {job_id}")

        except Exception as e:
            # A source-level LNException means the novel is unavailable, which
            # is expected and user-facing rather than a bug. Keep it below ERROR
            # so it fails the job without opening an auto-issue.
            if _is_expected_crawler_error(e):
                logger.warning("Download process stopped: %s", e)
            else:
                logger.exception(f"Error in download process: {str(e)}")
            try:
                DownloaderService._setup_django()
                from ..models import Job
                job = Job.objects.get(id=job_id)
                job.update_status(Job.STATUS_FAILED, f"Download process error: {str(e)}")
            except Exception:
                pass
        finally:
            if app is not None:
                try:
                    app.destroy()
                except Exception:
                    pass

    @classmethod
    def start_search(cls, query):
        """
        Queue a search for novels with the given query.
        The dedicated crawler worker picks it up and runs it.
        Returns a job object that can be used to track progress.
        """
        from ..models import Job
        job = Job.objects.create(
            status=Job.STATUS_CREATED,
            job_type=Job.JOB_TYPE_SEARCH,
            query=query,
        )
        return job

    @classmethod
    def run_job(cls, job_id, job_type, payload):
        """Execute a claimed job synchronously."""
        from ..models import Job

        if job_type == Job.JOB_TYPE_DOWNLOAD:
            cls._run_download_process(job_id, payload)
        else:
            cls._run_search_process(job_id, payload)

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

        from ..models import Job
        if not job:
            job = Job.objects.create(
                status=Job.STATUS_CREATED,
                job_type=Job.JOB_TYPE_DOWNLOAD,
                query="Direct Download",
            )

        # Queue the download; the dedicated crawler worker runs it.
        job.status = Job.STATUS_CREATED
        job.job_type = Job.JOB_TYPE_DOWNLOAD
        job.target_url = novel_url
        job.error_message = None
        job.save(update_fields=[
            'status', 'job_type', 'target_url', 'error_message', 'updated_at',
        ])
        logger.debug(f"Queued novel URL: {novel_url}")

        return {
            'status': 'success',
            'message': 'Download queued',
            'job_id': str(job.id)
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

            if not novel_url:
                return {
                    'status': 'error',
                    'message': 'Could not determine novel URL',
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
                'progress_unit': job.progress_unit,
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

    @classmethod
    def cancel_job(cls, job_id):
        """Cancel a job (queued or running)."""
        from ..models import Job

        try:
            job = Job.objects.get(id=job_id)

            if job.status == Job.STATUS_DOWNLOAD_COMPLETED:
                return {
                    'status': 'error',
                    'message': 'Job already completed',
                }

            # Mark it failed; a running worker checks this flag before
            # publishing results, and a queued job will never be claimed.
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
