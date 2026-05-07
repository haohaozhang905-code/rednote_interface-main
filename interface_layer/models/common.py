from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResponseMeta(BaseModel):
    request_id: str
    operation: str
    retry_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    session_id: str | None = None
    diagnostics_ref: str | None = None


class ApiError(BaseModel):
    code: str
    message: str
    retryable: bool
    action: str
    details: dict[str, Any] = Field(default_factory=dict)


class SuccessEnvelope(BaseModel):
    ok: Literal[True] = True
    data: dict[str, Any] = Field(default_factory=dict)
    meta: ResponseMeta


class ErrorEnvelope(BaseModel):
    ok: Literal[False] = False
    error: ApiError
    meta: ResponseMeta


class ExtraObject(BaseModel):
    model_config = ConfigDict(extra="allow")
