from __future__ import annotations

from fastapi import APIRouter, Depends

from interface_layer.api.dependencies import get_store, require_admin
from interface_layer.api.responses import ok
from interface_layer.models.requests import CreateSessionRequest, TokenRequest
from interface_layer.services.session_store import SessionStore

router = APIRouter(prefix="/v1/sessions", tags=["Sessions"])
admin_router = APIRouter(prefix="/admin/v1/sessions", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("", operation_id="listSessions")
def list_sessions(bound: bool | None = None, status: str | None = None, store: SessionStore = Depends(get_store)):
    return ok("listSessions", {"items": store.list_sessions(bound=bound, status=status)})


@router.post("", operation_id="createSession")
async def create_session(request: CreateSessionRequest | None = None, store: SessionStore = Depends(get_store)):
    purpose = request.purpose if request else None
    return ok("createSession", await store.create_session(purpose), status_code=201)


@router.post("/{session_id}/bind", operation_id="bindSession")
async def bind_session(session_id: str, store: SessionStore = Depends(get_store)):
    return ok("bindSession", await store.bind(session_id), session_id=session_id)


@router.post("/{session_id}/unbind", operation_id="unbindSession")
def unbind_session(session_id: str, request: TokenRequest, store: SessionStore = Depends(get_store)):
    store.unbind(session_id, request.token)
    return ok("unbindSession", {}, session_id=session_id)


@admin_router.post("/{session_id}/force-unbind", operation_id="adminForceUnbindSession")
def force_unbind(session_id: str, store: SessionStore = Depends(get_store)):
    store.force_unbind(session_id)
    return ok("adminForceUnbindSession", {}, session_id=session_id)


@admin_router.delete("/{session_id}", operation_id="adminDestroySession")
async def destroy_session(session_id: str, store: SessionStore = Depends(get_store)):
    await store.destroy(session_id)
    return ok("adminDestroySession", {}, session_id=session_id)
