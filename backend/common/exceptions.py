"""Turns every error into {"detail": "<friendly message>", "errors": {...}} and never leaks Python/Django internals."""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def _friendly(field, detail):
    code = getattr(detail, "code", None)
    label = (field or "this field").replace("_", " ")
    if code in ("required", "blank", "null"):
        return f"Please enter {label}."
    if code == "invalid_choice":
        return f"Please select a valid {label}."
    text = str(detail)
    if code == "invalid" and text.startswith(("A valid", "Date has wrong", "Enter a valid")):
        return f"Please enter a valid {label}."
    return text


def _clean(detail, field=""):
    if isinstance(detail, dict):
        return {key: _clean(value, key) for key, value in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_clean(item, field) if isinstance(item, (dict, list, tuple)) else _friendly(field, item) for item in detail]
    return _friendly(field, detail)


def _first_message(data):
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        if "non_field_errors" in data:
            return _first_message(data["non_field_errors"])
        for value in data.values():
            message = _first_message(value)
            if message:
                return message
    if isinstance(data, list):
        for value in data:
            message = _first_message(value)
            if message:
                return message
    return ""


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled error in API", exc_info=exc)
        return Response(
            {"detail": "Something went wrong on our side. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        errors = _clean(exc.detail)
        message = _first_message(errors) or "Please check the form and try again."
        response.data = {"detail": message, "errors": errors if isinstance(errors, dict) else {"non_field_errors": errors}}
    elif isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        response.data = {"detail": "Please sign in to continue."}
    elif isinstance(exc, exceptions.PermissionDenied):
        detail = str(exc.detail)
        if detail == str(exceptions.PermissionDenied.default_detail):
            detail = "You do not have permission to do that."
        response.data = {"detail": detail}
    elif isinstance(exc, exceptions.NotFound):
        response.data = {"detail": "We couldn't find what you were looking for."}
    elif isinstance(exc, exceptions.Throttled):
        response.data = {"detail": "Too many requests. Please wait a moment and try again."}
    elif isinstance(exc, exceptions.ParseError):
        response.data = {"detail": "We couldn't read that request. Please check your input."}
    elif isinstance(exc, exceptions.MethodNotAllowed):
        response.data = {"detail": "That action is not available."}
    else:
        response.data = {"detail": str(getattr(exc, "detail", "Request failed."))}
    return response
