from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from interface_layer.services.errors import InterfaceError
from interface_layer.services.session_store import SessionStore

from .schemas import failure, success


def register_resources(mcp: FastMCP, store: SessionStore) -> None:
    @mcp.resource("xhs://sessions", name="xhs_sessions", mime_type="application/json")
    def sessions() -> str:
        return _dump(success("xhs_resource_sessions", {"items": store.list_sessions()}))

    @mcp.resource("xhs://session/{session_id}/state", name="xhs_session_state", mime_type="application/json")
    def session_state(session_id: str) -> str:
        try:
            return _dump(success("xhs_resource_session_state", store.get(session_id).public_state(), session_id=session_id))
        except InterfaceError as exc:
            return _dump(failure("xhs_resource_session_state", exc, session_id=session_id))

    @mcp.resource("xhs://session/{session_id}/diagnostics", name="xhs_session_diagnostics", mime_type="application/json")
    def session_diagnostics(session_id: str) -> str:
        try:
            record = store.get(session_id)
            data: dict[str, Any] = record.public_state()
            return _dump(success("xhs_resource_session_diagnostics", data, session_id=session_id))
        except InterfaceError as exc:
            return _dump(failure("xhs_resource_session_diagnostics", exc, session_id=session_id))


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
