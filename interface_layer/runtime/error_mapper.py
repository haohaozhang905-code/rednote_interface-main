from __future__ import annotations

from interface_layer.runtime.base import RuntimeBackendError
from interface_layer.services.errors import InterfaceError


_DEFAULT_CODE_MAP = {
    "not_found": "note_unavailable",
    "missing_params": "invalid_request",
    "not_supported": "backend_unavailable",
    "invalid_state": "invalid_context",
    "invalid_context": "invalid_context",
    "stale_context": "stale_context",
    "login_required": "login_required",
    "risk_blocked": "risk_blocked",
    "detached": "backend_unavailable",
    "backend_error": "request_failed",
    "parser_changed": "parser_changed",
    "request_failed": "request_failed",
    "backend_unavailable": "backend_unavailable",
}

_BIND_CODE_MAP = {
    "not_found": "backend_unavailable",
    "invalid_state": "backend_unavailable",
}


def to_interface_error(error: RuntimeBackendError, operation: str = "") -> InterfaceError:
    mapping = _BIND_CODE_MAP if operation == "bind" else _DEFAULT_CODE_MAP
    code = mapping.get(error.code, _DEFAULT_CODE_MAP.get(error.code, "request_failed"))
    details = {"runtime_code": error.code, **error.details}
    return InterfaceError(code, message=error.message, details=details)
