# Create your views here.

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from ..services import DownloaderService
from ..models import Job


def _current_user(request):
    """Resolve the authenticated user for this plain (non-DRF) view module.

    Every other view is DRF, so ``request.user`` is populated by DRF's
    authentication. These downloader endpoints predate that and stay plain
    Django views, where AuthenticationMiddleware only sees sessions - and login
    is token-only, so ``request.user`` is always anonymous here. Run the same
    TokenAuthentication DRF would, so an authenticated download is attributed
    to its submitter. Returns None for anonymous or invalid-token requests.
    """
    if request.user.is_authenticated:
        return request.user
    try:
        authenticated = TokenAuthentication().authenticate(request)
    except AuthenticationFailed:
        return None
    if authenticated is None:
        return None
    user, _ = authenticated
    return user if user.is_authenticated else None


@csrf_exempt
@require_http_methods(["POST"])
def start_search(request):
    """Start a novel search"""
    try:
        data = json.loads(request.body)
        query = data.get("query")

        if not query or len(query.strip()) < 3:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Query must be at least 3 characters long",
                },
                status=400,
            )
        
        job = DownloaderService.start_search(query, user=_current_user(request))

        return JsonResponse(
            {"status": "success", "message": "Search started", "job_id": str(job.id)}
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON in request body"}, status=400
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def get_search_status(request, job_id):
    """Get the status of a search job"""
    try:
        status = DownloaderService.get_search_status(job_id)
        return JsonResponse(status)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def get_search_results(request, job_id):
    """Get the results of a search job"""
    try:
        results = DownloaderService.get_search_results(job_id)
        return JsonResponse(results)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def start_download(request, job_id):
    """Start downloading a novel"""
    try:
        data = json.loads(request.body)
        novel_index = int(data.get("novel_index", 0))
        source_index = int(data.get("source_index", 0))
        novel_url = data.get("novel_url") or None

        # Always use JSON format and download all chapters
        result = DownloaderService.start_download(
            job_id,
            novel_index=novel_index,
            source_index=source_index,
            user=_current_user(request),
            novel_url=novel_url,
        )

        return JsonResponse(result)
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON in request body"}, status=400
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def get_download_status(request, job_id):
    """Get the status of a download job"""
    try:
        status = DownloaderService.get_download_status(job_id)
        return JsonResponse(status)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def get_download_results(request, job_id):
    """Get the results of a download job"""
    try:
        results = DownloaderService.get_download_results(job_id)
        return JsonResponse(results)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def cancel_job(request, job_id):
    """Cancel a running job"""
    try:
        result = DownloaderService.cancel_job(job_id)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def list_jobs(request):
    """List jobs. Pass ?active=1 to only get queued/running jobs, ?job_type=download to only get downloads."""
    try:
        # EPUB builds are polled per book by the frontend, not listed here.
        jobs = Job.objects.exclude(job_type=Job.JOB_TYPE_EPUB)
        if request.GET.get("job_type"):
            jobs = jobs.filter(job_type=request.GET["job_type"])
        if request.GET.get("active"):
            jobs = jobs.filter(status__in=[
                Job.STATUS_CREATED, Job.STATUS_SEARCHING, Job.STATUS_DOWNLOADING,
            ])
        jobs = jobs.order_by("-created_at")
        return JsonResponse(
            {"status": "success", "jobs": [job.to_dict() for job in jobs]}
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def job_details(request, job_id):
    """Get details of a specific job"""
    try:
        job = Job.objects.get(id=job_id)
        return JsonResponse({"status": "success", "job": job.to_dict()})
    except Job.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": f"Job with ID {job_id} not found"},
            status=404,
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def start_direct_download(request):
    """Start downloading a novel directly from URL"""
    try:
        data = json.loads(request.body)
        novel_url = data.get("novel_url")

        if not novel_url or not novel_url.startswith('http'):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Valid URL is required (must start with http)",
                },
                status=400,
            )
        
        # Use the existing direct download method from the service
        result = DownloaderService.start_direct_download(
            novel_url, user=_current_user(request)
        )
        return JsonResponse(result)
    
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON in request body"}, status=400
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
