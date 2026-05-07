from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlencode

from interface_layer.runtime.base import RuntimeBackendError
from interface_layer.models.xhs_blocks import XhsNoteDetail, XhsRootCommentsData, XhsSearchPage, XhsSubCommentsData
from interface_layer.runtime.xhs_browser_session import XhsBrowserSession
from interface_layer.runtime.xhs_normalizers import (
    build_comment_item,
    build_note_detail,
    build_search_item,
    classify_note_html,
    extract_note_detail_from_html,
)
from interface_layer.runtime.xhs_signing import build_sign_headers, get_search_id


class XhsPlatformClient:
    def __init__(self, browser: XhsBrowserSession) -> None:
        try:
            import httpx
        except Exception as exc:
            raise RuntimeBackendError("backend_unavailable", "httpx import failed", {"error": str(exc)}) from exc
        self._browser = browser
        self._host = "https://edith.xiaohongshu.com"
        self._domain = "https://www.xiaohongshu.com"
        self._headers = _browser_headers()
        self._cookie_dict: dict[str, str] = {}
        self._client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=20, max_keepalive_connections=10))

    async def close(self) -> None:
        await self._client.aclose()

    async def refresh_cookies(self) -> None:
        cookie_header, cookie_dict = await self._browser.cookie_state()
        self._headers["Cookie"] = cookie_header
        self._cookie_dict = cookie_dict

    async def login_status(self) -> dict[str, Any]:
        await self._browser.ensure_explore_page()
        await self.refresh_cookies()
        if not all(self._cookie_dict.get(key) for key in ("a1", "web_session")):
            return {"state": "login_required", "required_action": "cookie", "error": "missing_core_cookie"}
        page = self._browser.page
        page_url = str(getattr(page, "url", "") or "")
        lowered_url = page_url.lower()
        if "/website-login/error" in lowered_url or "error_code=300012" in lowered_url:
            return {"state": "risk_blocked", "required_action": "inspect_diagnostics", "page_url": page_url}
        if "/login" in lowered_url or "/web-login" in lowered_url:
            return {"state": "login_required", "required_action": "cookie", "page_url": page_url}
        try:
            page_title = str(await page.title() or "")
        except Exception:
            page_title = ""
        try:
            page_html = str(await page.content() or "")
        except Exception:
            page_html = ""
        category = classify_note_html(page_html)
        if category in {"captcha", "risk"} or "captcha" in page_title.lower() or "验证" in page_title:
            return {"state": "risk_blocked", "required_action": "inspect_diagnostics", "page_url": page_url, "page_title": page_title}
        if category == "login_required":
            return {"state": "login_required", "required_action": "cookie", "page_url": page_url, "page_title": page_title}
        return await self._account_probe_status()

    async def search_posts(self, payload: dict[str, Any]) -> tuple[XhsSearchPage, dict[str, Any]]:
        try:
            result = await self._search_with_http(payload)
            if not result.get("items"):
                raise RuntimeBackendError("request_failed", "search returned no items")
        except RuntimeBackendError as exc:
            if exc.code in {"risk_blocked", "login_required"}:
                raise
            result = await self._browser.goto_search_and_capture(str(payload.get("keyword") or ""))
        warning_types = sorted(
            {
                str(item.get("model_type"))
                for item in result["items"]
                if item.get("model_type") not in {"note", "rec_query", "hot_query"}
            }
        )
        if warning_types:
            logging.getLogger(__name__).warning("search response contains unsupported model_type values: %s", warning_types)
        items_for_normalization = [item for item in result["items"] if item.get("model_type") == "note"]
        try:
            items = [build_search_item(item) for item in items_for_normalization]
        except RuntimeBackendError as exc:
            _with_raw(exc, result)
            raise
        if not items:
            raise RuntimeBackendError("parser_changed", "search parser missed required fields", {"raw": result})
        return XhsSearchPage(has_more=result["has_more"], items=items[: payload["limit"]]), result

    async def open_note(self, payload: dict[str, Any]) -> tuple[XhsNoteDetail, dict[str, Any]]:
        note_id = str(payload["note_id"]).strip()
        note_token = str(payload["xsec_token"]).strip()
        xsec_source = "pc_search" if payload.get("_open_from_search") else "pc_share"
        url = self._note_detail_html_url(
            note_id=note_id,
            xsec_source=xsec_source,
            xsec_token=note_token,
            from_search=bool(payload.get("_open_from_search")),
        )
        headers = dict(self._headers)
        html = await self._request("GET", url, headers=headers, return_text=True, throttle_profile="detail")
        raw_html = {"url": url, "body": html}
        category = classify_note_html(html)
        if category in {"captcha", "risk"}:
            raise RuntimeBackendError("risk_blocked", f"risk control triggered(html_category={category})", {"note_id": note_id, "raw": raw_html})
        if category == "login_required":
            raise RuntimeBackendError("login_required", "login is required", {"raw": raw_html})
        if category == "not_found":
            raise RuntimeBackendError("not_found", "note is unavailable", {"note_id": note_id, "raw": raw_html})
        note = extract_note_detail_from_html(note_id, html)
        if not note:
            raise RuntimeBackendError("parser_changed", "note detail parser returned empty", {"note_id": note_id, "raw": raw_html})
        try:
            normalized_note = build_note_detail(note)
        except RuntimeBackendError as exc:
            _with_raw(exc, {"url": url, "body": note})
            raise
        return normalized_note, note

    async def root_comments(self, payload: dict[str, Any]) -> tuple[XhsRootCommentsData, dict[str, Any]]:
        raw = await self._get_root_comments(payload)
        try:
            comments = [build_comment_item(item) for item in raw["comments"]]
        except RuntimeBackendError as exc:
            _with_raw(exc, raw)
            raise
        comments = comments[: payload["limit"]]
        return XhsRootCommentsData(**_comment_page_metadata(raw), comments=comments), raw

    async def sub_comments(self, payload: dict[str, Any]) -> tuple[XhsSubCommentsData, dict[str, Any]]:
        raw = await self.get(
            "/api/sns/web/v2/comment/sub/page",
            {
                "note_id": payload.get("note_id"),
                "root_comment_id": payload.get("root_comment_id"),
                "num": payload["limit"],
                "cursor": payload.get("cursor") or "",
                "image_formats": "jpg,webp,avif",
                "top_comment_id": "",
                "xsec_token": payload.get("note_token"),
            },
            throttle_profile="sub_comment",
        )
        try:
            comments = [build_comment_item(item, is_sub_comment=True) for item in raw["comments"]]
        except RuntimeBackendError as exc:
            _with_raw(exc, raw)
            raise
        return XhsSubCommentsData(**_comment_page_metadata(raw), comments=comments), raw

    async def get(self, uri: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        final_uri = uri
        if params:
            final_uri = f"{uri}?{urlencode(params)}".replace("%2C", ",")
        headers = await self._signed_headers(final_uri)
        return await self._request("GET", f"{self._host}{final_uri}", headers=headers, **kwargs)

    async def post(self, uri: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        headers = await self._signed_headers(uri, data)
        body = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return await self._request("POST", f"{self._host}{uri}", data=body, headers=headers, **kwargs)

    async def _search_with_http(self, payload: dict[str, Any]) -> dict[str, Any]:
        filters = dict(payload.get("filters") or {})
        sort = str(payload["sort"])
        data = {
            "keyword": payload.get("keyword"),
            "page": payload["page"],
            "page_size": payload["page_size"],
            "search_id": get_search_id(),
            "sort": sort,
            "note_type": 0,
            "filters": [
                {"tags": [sort], "type": "sort_type"},
                {"tags": [filters.get("filter_note_type") or "不限"], "type": "filter_note_type"},
                {"tags": [filters.get("filter_note_time") or "不限"], "type": "filter_note_time"},
                {"tags": [filters.get("filter_note_range") or "不限"], "type": "filter_note_range"},
                {"tags": [filters.get("filter_pos_distance") or "不限"], "type": "filter_pos_distance"},
            ],
        }
        if filters.get("geo"):
            data["geo"] = filters["geo"]
        return await self.post("/api/sns/web/v1/search/notes", data, throttle_profile="search")

    async def _account_probe_status(self) -> dict[str, Any]:
        result = await self.get("/api/sns/web/v2/user/me")
        user = _normalize_me_user(result)
        return {"state": "ready", "required_action": "none", **user}

    async def _get_root_comments(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = await self.get(
                "/api/sns/web/v2/comment/page",
                {
                    "note_id": payload.get("note_id"),
                    "cursor": payload.get("cursor") or "",
                    "top_comment_id": "",
                    "image_formats": "jpg,webp,avif",
                    "xsec_token": payload.get("note_token"),
                },
                throttle_profile="comment",
            )
            if raw.get("comments") or payload.get("cursor"):
                return raw
        except RuntimeBackendError as exc:
            if payload.get("cursor") or exc.code in {"risk_blocked", "login_required"}:
                raise
        return await self._browser.goto_note_comments_and_capture(str(payload.get("note_id") or ""), str(payload.get("note_token") or ""))

    async def _signed_headers(self, uri: str, data: Any = None) -> dict[str, str]:
        await self.refresh_cookies()
        headers = dict(self._headers)
        headers.update(await build_sign_headers(self._browser.page, uri, data, a1_cookie=self._cookie_dict.get("a1", "")))
        return headers

    async def _request(self, method: str, url: str, *, return_text: bool = False, **kwargs: Any) -> Any:
        kwargs.pop("throttle_profile", None)
        response = await self._client.request(method, url, **kwargs)
        if response.status_code in {429, 461, 471}:
            raise RuntimeBackendError("risk_blocked", f"risk control triggered(status={response.status_code})", {"raw": _raw_response(response)})
        if response.status_code == 302:
            raise RuntimeBackendError("risk_blocked", "risk control triggered(status=302)", {"location": response.headers.get("location", ""), "raw": _raw_response(response)})
        if 500 <= response.status_code < 600:
            raise RuntimeBackendError("request_failed", f"platform server error(status={response.status_code})", {"raw": _raw_response(response)})
        if return_text:
            return response.text
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeBackendError("request_failed", f"unexpected response format(status={response.status_code})", {"raw": _raw_response(response)}) from exc
        if isinstance(payload, dict) and payload.get("code") == -100:
            raise RuntimeBackendError("risk_blocked", "risk control triggered(code=-100)", {"raw": _raw_response(response, payload)})
        if isinstance(payload, dict) and payload.get("success"):
            return payload["data"]
        raise RuntimeBackendError("request_failed", f"platform request failed(status={response.status_code}, code={payload.get('code') if isinstance(payload, dict) else ''})", {"raw": _raw_response(response, payload)})

    def _note_detail_html_url(self, *, note_id: str, xsec_source: str, xsec_token: str, from_search: bool = False) -> str:
        if from_search:
            query = urlencode({"xsec_token": xsec_token, "xsec_source": xsec_source, "source": "web_explore_feed"})
            return f"{self._domain}/explore/{note_id}?{query}"
        path = "search_result" if xsec_source == "pc_search" else "explore"
        return f"{self._domain}/{path}/{note_id}?{urlencode({'xsec_token': xsec_token, 'xsec_source': xsec_source})}"


def _browser_headers() -> dict[str, str]:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://www.xiaohongshu.com",
        "pragma": "no-cache",
        "referer": "https://www.xiaohongshu.com/",
        "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    }


def _comment_page_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "cursor": raw["cursor"],
        "has_more": raw["has_more"],
        "time": raw["time"],
        "xsec_token": raw["xsec_token"],
    }


def _normalize_me_user(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "red_id": str(payload["red_id"]),
        "user_id": str(payload["user_id"]),
        "nickname": str(payload["nickname"]),
    }


def _with_raw(error: RuntimeBackendError, raw: Any) -> RuntimeBackendError:
    error.details.setdefault("raw", raw)
    return error


def _raw_response(response: Any, body: Any | None = None) -> dict[str, Any]:
    return {"status_code": response.status_code, "url": str(response.url), "body": response.text if body is None else body}
