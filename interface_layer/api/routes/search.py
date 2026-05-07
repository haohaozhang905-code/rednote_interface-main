from __future__ import annotations

from fastapi import APIRouter, Depends

from interface_layer.api.dependencies import get_store
from interface_layer.api.responses import ok
from interface_layer.models.requests import SearchPostsRequest
from interface_layer.services.session_store import SessionStore

router = APIRouter(prefix="/v1/sessions/{session_id}/search", tags=["Search"])


@router.post("", operation_id="searchPosts")
async def search_posts(session_id: str, request: SearchPostsRequest, store: SessionStore = Depends(get_store)):
    data = await store.search_posts(session_id, request.token, request)
    return ok("searchPosts", data, session_id=session_id)
