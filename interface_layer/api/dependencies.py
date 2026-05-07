from __future__ import annotations

import secrets

from fastapi import Header, Request

from interface_layer.services.errors import InterfaceError
from interface_layer.services.session_store import SessionStore


def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def require_admin(request: Request, x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    admin_token = getattr(request.app.state, "admin_token", "")
    if not x_admin_token or not admin_token or not secrets.compare_digest(x_admin_token, admin_token):
        raise InterfaceError("admin_unauthorized")
