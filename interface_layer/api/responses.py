from __future__ import annotations

import os
import secrets
import traceback
from contextvars import ContextVar, Token
from typing import Any

from fastapi.responses import JSONResponse

from interface_layer.models.common import ApiError, ErrorEnvelope, ResponseMeta, SuccessEnvelope
from interface_layer.services.errors import InterfaceError

DEBUG_RAW_HEADER = "X-Debug-Raw"
_DEBUG_RAW_MODE: ContextVar[bool] = ContextVar("debug_raw_mode", default=False)
_CLIENT_ERROR_CODES = {
    "invalid_request",
    "session_not_found",
    "session_busy",
    "invalid_session_token",
    "invalid_context",
    "stale_context",
    "invalid_xsec_token",
    "diagnostics_not_found",
    "admin_unauthorized",
}


def ok(operation: str, data: dict[str, Any] | None = None, session_id: str | None = None, status_code: int = 200) -> JSONResponse:
    meta = ResponseMeta(request_id=_request_id(), operation=operation, session_id=session_id)
    body = SuccessEnvelope(data=data or {}, meta=meta)
    return JSONResponse(status_code=status_code, content=_response_content(body.model_dump(exclude_none=True)))


def error_response(error: InterfaceError, operation: str, session_id: str | None = None) -> JSONResponse:
    spec = error.spec
    details = _error_details(error)
    api_error = ApiError(
        code=error.code,
        message=error.message or spec.message,
        retryable=spec.retryable,
        action=spec.action,
        details=details,
    )
    meta = ResponseMeta(request_id=_request_id(), operation=operation, session_id=session_id)
    body = ErrorEnvelope(error=api_error, meta=meta)
    return JSONResponse(status_code=spec.status_code, content=_response_content(body.model_dump(exclude_none=True)))


def set_debug_raw_mode(enabled: bool) -> Token[bool]:
    return _DEBUG_RAW_MODE.set(enabled)


def reset_debug_raw_mode(token: Token[bool]) -> None:
    _DEBUG_RAW_MODE.reset(token)


def _request_id() -> str:
    return f"req_{secrets.token_hex(8)}"


def _response_content(content: dict[str, Any]) -> dict[str, Any]:
    if _debug_mode_enabled():
        return content
    return _strip_raw(content)


def _error_details(error: InterfaceError) -> dict[str, Any]:
    details = dict(error.details)
    if _debug_error_enabled(error):
        details["debug"] = _debug_payload(error)
    return details


def _debug_mode_enabled() -> bool:
    return _DEBUG_RAW_MODE.get() or str(os.getenv("XHS_INTERFACE_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}


def _debug_error_enabled(error: InterfaceError) -> bool:
    return _debug_mode_enabled() and error.code not in _CLIENT_ERROR_CODES


def _debug_payload(error: InterfaceError) -> dict[str, Any]:
    cause = error.__cause__
    payload: dict[str, Any] = {
        "exception_type": type(error).__name__,
        "traceback": traceback.format_exception(type(error), error, error.__traceback__),
    }
    if cause is not None:
        payload["cause_type"] = type(cause).__name__
        payload["cause_message"] = str(cause)
    return payload


def _strip_raw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_raw(item) for key, item in value.items() if key != "raw"}
    if isinstance(value, list):
        return [_strip_raw(item) for item in value]
    return value
