from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from interface_layer.api.responses import error_response
from interface_layer.services.errors import InterfaceError


async def interface_error_handler(request: Request, exc: InterfaceError):
    return error_response(exc, operation_id(request), request.path_params.get("session_id"))


async def validation_error_handler(request: Request, exc: RequestValidationError):
    error = InterfaceError("invalid_request", details={"errors": _safe_validation_errors(exc.errors())})
    return error_response(error, operation_id(request), request.path_params.get("session_id"))


def operation_id(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "operation_id", None) or getattr(route, "name", "unknown")


def _safe_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for item in errors:
        sanitized.append({key: _json_safe(value) for key, value in item.items() if key != "input"})
    return sanitized


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
