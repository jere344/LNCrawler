from rest_framework import status
from rest_framework.response import Response


def forbidden(detail):
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
