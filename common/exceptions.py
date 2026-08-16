"""One error shape for the whole API.

DRF's default handler returns whatever the exception carried: sometimes
`{"detail": "..."}`, sometimes `{"field": ["..."]}`, sometimes a bare list. The
frontend then needs a different unwrapping rule per endpoint. This normalises
every error to the same two keys:

    {"detail": "Human-readable summary.", "errors": {"field": ["..."]}}

`errors` is present only for field validation failures. Nothing else about
DRF's behaviour changes — status codes, throttling headers and authentication
challenges are left exactly as they were.
"""

import logging

from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("api")


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        # Not a DRF exception, so DRF is about to let it become a 500. Django
        # logs the traceback itself; this adds the endpoint, which is the part
        # that makes the traceback actionable.
        logger.exception(
            "Unhandled error in %s", context.get("view").__class__.__name__
        )
        return None

    data = response.data

    if isinstance(exc, exceptions.ValidationError) and isinstance(data, dict):
        # Field errors. `non_field_errors` is DRF's key for object-level
        # failures and reads as noise to a client, so it is promoted to detail.
        non_field = data.pop("non_field_errors", None)
        detail = (
            str(non_field[0])
            if non_field
            else "Some of the details you entered need fixing."
        )
        response.data = {"detail": detail, "errors": data} if data else {"detail": detail}
        return response

    if isinstance(data, dict) and "detail" in data:
        response.data = {"detail": str(data["detail"])}
        return response

    # A list, or a dict with no detail — flatten rather than invent a shape.
    response.data = {"detail": str(data[0]) if isinstance(data, list) and data else str(data)}
    return response
