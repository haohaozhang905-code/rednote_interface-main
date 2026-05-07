from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RuntimeBackendError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)


class RuntimeSession(Protocol):
    def snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def run_login_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def get_login_status(self) -> dict[str, Any]:
        raise NotImplementedError

    async def search_posts(self, payload: dict[str, Any], view: str = "full") -> dict[str, Any]:
        raise NotImplementedError

    async def open_note_from_search(self, note_id: str, view: str = "full") -> dict[str, Any]:
        raise NotImplementedError

    async def open_note_by_xsec(self, payload: dict[str, Any], view: str = "full") -> dict[str, Any]:
        raise NotImplementedError

    async def fetch_root_comments(self, note_id: str, cursor: str | None, limit: int, view: str = "full") -> dict[str, Any]:
        raise NotImplementedError

    async def fetch_sub_comments(self, root_comment_id: str, cursor: str | None, limit: int, view: str = "full") -> dict[str, Any]:
        raise NotImplementedError


class RuntimeBackend(Protocol):
    async def create_session(self, payload: dict[str, Any]) -> RuntimeSession:
        raise NotImplementedError
