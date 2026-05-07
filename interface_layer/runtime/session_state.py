from __future__ import annotations

from typing import Any

from interface_layer.models.xhs_blocks import (
    XhsNoteDetail,
    XhsRootCommentsData,
    XhsRootComment,
    XhsSearchPage,
    XhsSubCommentsData,
)
from interface_layer.runtime.base import RuntimeBackendError
from interface_layer.runtime.xhs_response_views import (
    XhsResponseView,
    dump_response,
    note_response,
    root_comments_response,
    search_response,
    sub_comments_response,
)


def default_login() -> dict[str, Any]:
    return {"state": "not_started", "required_action": "none"}


def _search_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    return (
        str(payload.get("keyword") or ""),
        str(payload.get("sort") or "general"),
        tuple(sorted((str(key), str(value)) for key, value in filters.items())),
        int(payload.get("page_size") or 20),
        int(payload.get("limit") or 20),
    )


class RuntimeSessionState:
    def __init__(self) -> None:
        self.login: dict[str, Any] = default_login()
        self.current_context: dict[str, Any] = {}
        self.search_signature: tuple[Any, ...] | None = None
        self.search_items: dict[str, Any] = {}
        self.root_comments: dict[str, XhsRootComment] = {}

    def snapshot(self) -> dict[str, Any]:
        return {
            "login": dict(self.login),
            "current_context": dict(self.current_context),
        }

    def apply_login_result(self, login: dict[str, Any]) -> dict[str, Any]:
        self.login = dict(login)
        return self.login

    def apply_search_result(self, data: XhsSearchPage, raw: dict[str, Any], payload: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
        signature = _search_signature(payload)
        if self.search_signature != signature:
            self.search_items = {}
            self.search_signature = signature
        for item in data.items:
            self.search_items[item.note_id] = item
        self.current_context = {"type": "search", "keyword": payload["keyword"], "page": payload.get("page", 1)}
        return search_response(data, raw, view=view)

    def get_search_item(self, note_id: str) -> dict[str, Any]:
        item = self.search_items.get(note_id)
        if item is None:
            raise RuntimeBackendError("stale_context", "note_id does not belong to current search context")
        return dump_response(item)

    def apply_note_result(self, note: XhsNoteDetail, raw: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
        self.current_context = {
            "type": "note",
            "note_id": note.note_id,
            "note_token": note.xsec_token,
        }
        self.root_comments.clear()
        return note_response(note, raw, view=view)

    def get_note_context(self, note_id: str) -> dict[str, Any]:
        current = self.current_context
        if current.get("type") != "note":
            raise RuntimeBackendError("invalid_context", "current context is not note")
        if note_id != current.get("note_id"):
            raise RuntimeBackendError("invalid_context", "note_id does not match current note context")
        return {
            "note_id": str(current.get("note_id") or ""),
            "note_token": str(current.get("note_token") or ""),
        }

    def apply_root_comments_result(self, data: XhsRootCommentsData, raw: dict[str, Any], note_context: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
        comments = []
        for item in data.comments:
            self.root_comments[item.comment_id] = item
            comments.append(item)
        response_data = XhsRootCommentsData(
            cursor=data.cursor,
            has_more=data.has_more,
            time=data.time,
            xsec_token=data.xsec_token,
            comments=comments,
        )
        return root_comments_response(response_data, raw, view=view)

    def build_sub_comments_payload(self, root_comment_id: str, cursor: str | None, limit: int) -> dict[str, Any]:
        root_comment = self.root_comments.get(root_comment_id)
        if root_comment is None:
            raise RuntimeBackendError("invalid_context", "root_comment_id does not belong to current note context")
        return {
            **self.get_note_context(root_comment.note_id),
            "root_comment_id": root_comment.comment_id,
            "cursor": cursor or "",
            "limit": limit,
        }

    @staticmethod
    def build_sub_comments_result(data: XhsSubCommentsData, raw: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
        response_data = XhsSubCommentsData(
            cursor=data.cursor,
            has_more=data.has_more,
            time=data.time,
            xsec_token=data.xsec_token,
            comments=data.comments,
        )
        return sub_comments_response(response_data, raw, view=view)
