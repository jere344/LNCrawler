from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

@require_GET
@ensure_csrf_cookie
def get_csrf_token(request):
    """
    This view does nothing but ensure that the CSRF cookie is set.
    This view should be called before any POST/PUT/DELETE requests
    if a CSRF token is needed.
    """
    return JsonResponse({"detail": "CSRF cookie set"})
