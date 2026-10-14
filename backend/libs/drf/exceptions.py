import logging

from django.db import DatabaseError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def exception_handler(exc, context):
    if isinstance(exc, DatabaseError):
        logger.error("database_unavailable")
        return Response(
            {
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Database unavailable.",
                    "details": {},
                }
            },
            status=503,
        )
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    codes = {
        400: "VALIDATION_ERROR",
        401: "AUTHENTICATION_REQUIRED",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        415: "UNSUPPORTED_MEDIA_TYPE",
        429: "RATE_LIMITED",
    }
    response.data = {
        "error": {
            "code": codes.get(response.status_code, "HTTP_ERROR"),
            "message": "Request could not be completed.",
            "details": response.data,
        }
    }
    return response
