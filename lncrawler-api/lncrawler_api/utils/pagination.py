from django.core.paginator import Paginator
from rest_framework.response import Response


def parse_page_size(request, default=20, max_size=50):
    """Parse a user-supplied page_size safely, clamped to [1, max_size]."""
    raw = request.GET.get("page_size", default) if hasattr(request, "GET") else default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, max_size))


def _paginate(request, queryset, default_size, max_size, count_queryset=None):
    paginator = Paginator(queryset, parse_page_size(request, default_size, max_size))
    if count_queryset is not None:
        # A pre-trimmed queryset (e.g. distinct ids, no display-only
        # annotations) is much cheaper to COUNT(*) than the full SELECT.
        paginator.count = count_queryset.count()
    return paginator, paginator.get_page(request.GET.get("page", 1))


def paginated_response(
    request, queryset, serializer_class, *,
    default_size=20, max_size=100, context=None, extra=None, count_queryset=None,
):
    """Standard list envelope: {count, total_pages, current_page, results}."""
    paginator, page_obj = _paginate(request, queryset, default_size, max_size, count_queryset)
    serializer_context = {"request": request}
    if context:
        serializer_context.update(context)
    payload = {
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "results": serializer_class(page_obj, many=True, context=serializer_context).data,
    }
    if extra:
        payload.update(extra)
    return Response(payload)


def paginated_reviews_response(
    request, queryset, serializer_class, *, default_size=20, max_size=50,
):
    """Reviews envelope: {reviews, pagination:{...}}."""
    paginator, page_obj = _paginate(request, queryset, default_size, max_size)
    serializer = serializer_class(page_obj, many=True, context={"request": request})
    return Response({
        "reviews": serializer.data,
        "pagination": {
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_reviews": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
    })
