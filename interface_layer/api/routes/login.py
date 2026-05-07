from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from interface_layer.api.dependencies import get_store
from interface_layer.api.responses import ok
from interface_layer.models.requests import LoginActionRequest
from interface_layer.services.session_store import SessionStore

router = APIRouter(prefix="/v1/sessions/{session_id}/login", tags=["Login"])


@router.post("", operation_id="runLoginAction")
async def run_login_action(session_id: str, request: LoginActionRequest = Body(...), store: SessionStore = Depends(get_store)):
    return ok("runLoginAction", await store.run_login_action(session_id, request), session_id=session_id)


@router.get("/status", operation_id="getLoginStatus")
async def get_login_status(session_id: str, token: str | None = None, store: SessionStore = Depends(get_store)):
    return ok("getLoginStatus", await store.get_login_status(session_id, token), session_id=session_id)
