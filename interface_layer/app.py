from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from interface_layer.api.exception_handlers import interface_error_handler, validation_error_handler
from interface_layer.api.responses import (
    DEBUG_RAW_HEADER,
    reset_debug_raw_mode,
    set_debug_raw_mode,
)
from interface_layer.api.routes import comments, diagnostics, login, notes, search, sessions
from interface_layer.mcp import create_mcp_server
from interface_layer.runtime.base import RuntimeBackend
from interface_layer.runtime.factory import build_runtime
from interface_layer.services.errors import InterfaceError
from interface_layer.services.session_store import SessionStore


class _PostOnlyMcpApp:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") == "GET":
            response = JSONResponse(
                {"error": "mcp_get_stream_disabled", "message": "Use POST requests for streamable HTTP JSON."},
                status_code=405,
                headers={"Allow": "POST"},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


def create_app(runtime: RuntimeBackend | None = None, profile_root: Path | None = None) -> FastAPI:
    profiles = profile_root or Path(os.getenv("XHS_INTERFACE_PROFILE_ROOT", "browser_data/sessions"))
    admin_token = secrets.token_urlsafe(32)
    store = SessionStore(runtime or build_runtime(), profile_root=profiles)
    setattr(store, "admin_token", admin_token)
    mcp_server = create_mcp_server(store)
    mcp_app = _PostOnlyMcpApp(mcp_server.streamable_http_app())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print(f"XHS interface admin token: {admin_token}", flush=True)
        async with mcp_server.session_manager.run():
            try:
                yield
            finally:
                await store.close()

    app = FastAPI(title="XHS Interface Layer API", version="0.1.0", lifespan=lifespan)
    app.state.admin_token = admin_token
    app.state.session_store = store
    app.state.mcp_server = mcp_server

    @app.middleware("http")
    async def debug_raw_middleware(request: Request, call_next):
        token = set_debug_raw_mode(request.headers.get(DEBUG_RAW_HEADER) is not None)
        try:
            return await call_next(request)
        finally:
            reset_debug_raw_mode(token)

    app.add_exception_handler(InterfaceError, interface_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(sessions.router)
    app.include_router(login.router)
    app.include_router(search.router)
    app.include_router(notes.router)
    app.include_router(comments.router)
    app.include_router(diagnostics.router)
    app.include_router(sessions.admin_router)
    app.mount("/mcp", mcp_app)
    return app
