from __future__ import annotations

from fastapi import APIRouter, Depends

from interface_layer.api.dependencies import get_store
from interface_layer.api.responses import ok
from interface_layer.models.requests import FetchRootCommentsRequest, FetchSubCommentsRequest
from interface_layer.services.session_store import SessionStore

router = APIRouter(prefix="/v1/sessions/{session_id}/comments", tags=["Comments"])


@router.post("/root", operation_id="fetchRootComments")
async def fetch_root_comments(session_id: str, request: FetchRootCommentsRequest, store: SessionStore = Depends(get_store)):
    data = await store.root_comments(session_id, request.token, request.note_id, request.cursor, request.limit)
    return ok("fetchRootComments", data, session_id=session_id)


@router.post("/sub", operation_id="fetchSubComments")
async def fetch_sub_comments(session_id: str, request: FetchSubCommentsRequest, store: SessionStore = Depends(get_store)):
    data = await store.sub_comments(session_id, request.token, request.root_comment_id, request.cursor, request.limit)
    return ok("fetchSubComments", data, session_id=session_id)
