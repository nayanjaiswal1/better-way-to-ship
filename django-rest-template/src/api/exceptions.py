from __future__ import annotations

from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Wrap DRF exceptions in a consistent JSON envelope."""
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            "error": {
                "status_code": response.status_code,
                "detail": response.data,
            }
        }
    return response
