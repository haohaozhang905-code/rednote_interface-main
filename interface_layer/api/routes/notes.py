from __future__ import annotations

from fastapi import APIRouter, Depends

from interface_layer.api.dependencies import get_store
from interface_layer.api.responses import ok
from interface_layer.models.requests import OpenNoteByXsecRequest, OpenNoteFromSearchRequest
from interface_layer.services.session_store import SessionStore

router = APIRouter(prefix="/v1/sessions/{session_id}/notes", tags=["Notes"])


@router.post("/open-from-search", operation_id="openNoteFromSearch")
async def open_from_search(session_id: str, request: OpenNoteFromSearchRequest, store: SessionStore = Depends(get_store)):
    data = await store.open_from_search(session_id, request.token, request.note_id)
    return ok("openNoteFromSearch", data, session_id=session_id)


@router.post("/open-by-xsec", operation_id="openNoteByXsec")
async def open_by_xsec(session_id: str, request: OpenNoteByXsecRequest, store: SessionStore = Depends(get_store)):
    data = await store.open_by_xsec(session_id, request.token, request)
    return ok("openNoteByXsec", data, session_id=session_id)
