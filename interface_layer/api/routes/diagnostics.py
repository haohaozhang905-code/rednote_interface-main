from __future__ import annotations

from fastapi import APIRouter, Depends

from interface_layer.api.dependencies import get_store
from interface_layer.api.responses import ok
from interface_layer.services.session_store import SessionStore

router = APIRouter(prefix="/v1/sessions/{session_id}/diagnostics", tags=["Diagnostics"])


@router.get("", operation_id="getDiagnostics")
def get_diagnostics(session_id: str, token: str, diagnostics_ref: str | None = None, store: SessionStore = Depends(get_store)):
    store.verify_token(session_id, token)
    return ok("getDiagnostics", {"session_id": session_id, "context": {}}, session_id=session_id)
