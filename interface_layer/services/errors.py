from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorSpec:
    status_code: int
    message: str
    retryable: bool
    action: str


ERRORS: dict[str, ErrorSpec] = {
    "invalid_request": ErrorSpec(400, "request is invalid", False, "fix_request"),
    "session_not_found": ErrorSpec(404, "session not found", False, "fix_request"),
    "session_busy": ErrorSpec(409, "session is already bound", False, "unbind_or_force_unbind"),
    "session_create_failed": ErrorSpec(500, "session create failed", False, "inspect_diagnostics"),
    "session_destroy_failed": ErrorSpec(500, "session destroy failed", False, "inspect_diagnostics"),
    "invalid_session_token": ErrorSpec(401, "invalid session token", False, "bind_session"),
    "invalid_context": ErrorSpec(409, "context does not match current session position", False, "reopen_note"),
    "stale_context": ErrorSpec(409, "context id is stale", False, "refresh_search"),
    "login_required": ErrorSpec(401, "login is required", False, "login"),
    "risk_blocked": ErrorSpec(429, "platform risk control blocked the request", False, "inspect_diagnostics"),
    "invalid_xsec_token": ErrorSpec(400, "invalid xsec token", False, "refresh_search"),
    "note_unavailable": ErrorSpec(404, "note is unavailable", False, "inspect_diagnostics"),
    "diagnostics_not_found": ErrorSpec(404, "diagnostics not found", False, "inspect_diagnostics"),
    "admin_unauthorized": ErrorSpec(401, "admin token is missing or invalid", False, "contact_admin"),
    "request_failed": ErrorSpec(502, "platform request failed", True, "wait_and_retry"),
    "parser_changed": ErrorSpec(502, "platform parser changed", False, "contact_admin"),
    "backend_unavailable": ErrorSpec(503, "backend is unavailable", True, "wait_and_retry"),
}


@dataclass
class InterfaceError(Exception):
    code: str
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def spec(self) -> ErrorSpec:
        return ERRORS[self.code]

    @property
    def status_code(self) -> int:
        return self.spec.status_code
