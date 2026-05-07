from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from interface_layer.models.xhs_blocks import XhsRootCommentsData, XhsSearchPage, XhsSubCommentsData
from interface_layer.runtime.xhs_normalizers import build_comment_item, build_note_detail, build_search_item
from interface_layer.runtime.session_state import RuntimeSessionState
from interface_layer.runtime.xhs_response_views import XhsResponseView


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class MockRuntime:
    async def create_session(self, payload: dict[str, Any]) -> "MockRuntimeSession":
        return MockRuntimeSession(payload)


class MockRuntimeSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._runtime_state = RuntimeSessionState()
        self._state: dict[str, Any] = {
            "qr_sequence": 0,
            "profile": payload.get("user_data_dir", ""),
        }

    def snapshot(self) -> dict[str, Any]:
        return self._runtime_state.snapshot()

    async def close(self) -> None:
        self._state.clear()

    async def run_login_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "cookie":
            return self._runtime_state.apply_login_result({"state": "ready", "required_action": "none"})
        elif action == "qrcode":
            self._state["qr_sequence"] += 1
            return self._runtime_state.apply_login_result(self._qr_challenge(self._state["qr_sequence"]))
        elif action == "phone_start":
            return self._runtime_state.apply_login_result({"state": "waiting_sms", "required_action": "submit_sms_code"})
        elif action == "phone_submit":
            return self._runtime_state.apply_login_result({"state": "ready", "required_action": "none"})
        return await self.get_login_status()

    async def get_login_status(self) -> dict[str, Any]:
        return dict(self._runtime_state.login)

    async def search_posts(self, payload: dict[str, Any], view: XhsResponseView = "full") -> dict[str, Any]:
        keyword = str(payload.get("keyword") or "")
        raw_item = {
            "id": "65f0example",
            "xsec_token": "mock_xsec_token",
            "model_type": "note",
            "note_card": {
                "type": "normal",
                "display_title": f"{keyword} 示例笔记",
                "user": {"user_id": "user_demo", "nickname": "demo", "avatar": "https://example.invalid/avatar.jpg", "xsec_token": "mock_user_xsec"},
                "interact_info": {"liked_count": "1", "collected_count": "2", "comment_count": "3", "shared_count": "4", "liked": False, "collected": False},
                "cover": {"height": 1920, "width": 1080},
                "image_list": [{"height": 1920, "width": 1080}],
                "corner_tag_info": [{"type": "publish_time", "text": "刚刚"}],
            },
        }
        raw = {"items": [raw_item], "cursor": "", "has_more": False}
        data = XhsSearchPage(has_more=False, items=[build_search_item(raw_item)])
        return self._runtime_state.apply_search_result(data, raw, payload, view=view)

    async def open_note_from_search(self, note_id: str, view: XhsResponseView = "full") -> dict[str, Any]:
        search_item = self._runtime_state.get_search_item(note_id)
        raw_note = _mock_note_raw(str(search_item["note_id"]))
        return self._runtime_state.apply_note_result(build_note_detail(raw_note), raw_note, view=view)

    async def open_note_by_xsec(self, payload: dict[str, Any], view: XhsResponseView = "full") -> dict[str, Any]:
        raw_note = _mock_note_raw(str(payload["note_id"]))
        return self._runtime_state.apply_note_result(build_note_detail(raw_note), raw_note, view=view)

    async def fetch_root_comments(self, note_id: str, cursor: str | None, limit: int, view: XhsResponseView = "full") -> dict[str, Any]:
        note_context = self._runtime_state.get_note_context(note_id)
        raw_sub_comment = _mock_comment_raw("sc_demo", sub=True)
        raw_comment = {
            **_mock_comment_raw("c_demo"),
            "sub_comment_count": "1",
            "sub_comment_cursor": "sc_demo",
            "sub_comment_has_more": False,
            "sub_comments": [raw_sub_comment],
        }
        data = XhsRootCommentsData(cursor="", has_more=False, time=1777588485531, xsec_token="mock_page_xsec", comments=[build_comment_item(raw_comment)])
        raw = {"comments": [raw_comment], "cursor": "", "has_more": False, "time": 1777588485531, "xsec_token": "mock_page_xsec", "user_id": "user_demo"}
        return self._runtime_state.apply_root_comments_result(data, raw, note_context, view=view)

    async def fetch_sub_comments(self, root_comment_id: str, cursor: str | None, limit: int, view: XhsResponseView = "full") -> dict[str, Any]:
        self._runtime_state.build_sub_comments_payload(root_comment_id, cursor, limit)
        raw_comment = _mock_comment_raw("sc_demo", sub=True)
        data = XhsSubCommentsData(cursor="", has_more=False, time=1777588485531, xsec_token="mock_page_xsec", comments=[build_comment_item(raw_comment, is_sub_comment=True)])
        raw = {"comments": [raw_comment], "cursor": "", "has_more": False, "time": 1777588485531, "xsec_token": "mock_page_xsec", "user_id": "user_demo"}
        return self._runtime_state.build_sub_comments_result(data, raw, view=view)

    @staticmethod
    def _qr_challenge(sequence: int) -> dict[str, Any]:
        issued = datetime.now(UTC).replace(microsecond=0)
        expires = issued + timedelta(minutes=2)
        return {
            "state": "waiting_qr_scan",
            "required_action": "scan_qr",
            "challenge": {
                "challenge_id": _id("qrch"),
                "type": "login_qr" if sequence == 1 else "security_qr",
                "sequence": sequence,
                "status": "pending",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
                "image_mime": "image/png",
                "issued_at": issued.isoformat().replace("+00:00", "Z"),
                "expires_at": expires.isoformat().replace("+00:00", "Z"),
            },
        }


def _mock_note_raw(note_id: str) -> dict[str, Any]:
    return {
        "noteId": note_id,
        "xsecToken": "mock_xsec_token",
        "type": "normal",
        "title": "xsec note",
        "desc": "demo note detail",
        "time": 1776483020000,
        "lastUpdateTime": 1776483161000,
        "ipLocation": "上海",
        "user": {"userId": "user_demo", "nickname": "demo", "avatar": "https://example.invalid/avatar.jpg", "xsecToken": "mock_user_xsec"},
        "interactInfo": {"shareCount": "4", "likedCount": "1", "collectedCount": "2", "commentCount": "3", "liked": False, "collected": False, "followed": False, "relation": "none"},
        "imageList": [{"url": "", "urlDefault": "https://example.invalid/default.jpg", "urlPre": "https://example.invalid/pre.jpg", "height": 1920, "width": 1080, "livePhoto": False, "fileId": "", "traceId": "", "infoList": [{"imageScene": "WB_DFT", "url": "https://example.invalid/default.jpg"}]}],
        "tagList": [{"id": "tag_demo", "name": "demo", "type": "topic"}],
        "atUserList": [],
        "shareInfo": {"unShare": False},
    }


def _mock_comment_raw(comment_id: str, *, sub: bool = False) -> dict[str, Any]:
    raw = {
        "id": comment_id,
        "note_id": "65f0example",
        "content": "sub demo" if sub else "demo",
        "create_time": 1776483020000,
        "ip_location": "上海",
        "like_count": "1",
        "liked": False,
        "status": 0,
        "user_info": {"user_id": "user_demo", "nickname": "demo", "image": "https://example.invalid/avatar.jpg", "ai_agent": False, "xsec_token": "mock_user_xsec"},
        "pictures": [],
        "at_users": [],
        "show_tags": [],
    }
    if sub:
        raw["target_comment"] = {"id": "c_demo", "user_info": raw["user_info"]}
    return raw
