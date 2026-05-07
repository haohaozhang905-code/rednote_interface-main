from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

from interface_layer.models.xhs_blocks import XhsNoteDetail, XhsRootCommentsData, XhsSearchPage, XhsSubCommentsData
from interface_layer.runtime.base import RuntimeBackendError
from interface_layer.runtime.browser_profile import BrowserProfile, launch_browser_profile
from interface_layer.runtime.session_state import RuntimeSessionState
from interface_layer.runtime.xhs_response_views import XhsResponseView
from interface_layer.runtime.xhs_browser_session import XhsBrowserSession
from interface_layer.runtime.xhs_platform_client import XhsPlatformClient


def parse_cookie_header(cookie: str) -> dict[str, str]:
    parsed = SimpleCookie()
    parsed.load(str(cookie or ""))
    return {key: morsel.value for key, morsel in parsed.items()}


def require_cookie_keys(cookie_dict: dict[str, str]) -> None:
    missing = [key for key in ("a1", "web_session") if not str(cookie_dict.get(key) or "").strip()]
    if missing:
        raise RuntimeBackendError("missing_params", f"cookie missing required keys: {', '.join(missing)}", {"missing": missing})


def _is_browser_closed_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "targetclosed" in text or "target page, context or browser has been closed" in text


def _to_backend_error(exc: Exception) -> RuntimeBackendError:
    if _is_browser_closed_error(exc):
        return RuntimeBackendError("backend_unavailable", "browser has been closed")
    return RuntimeBackendError("backend_error", str(exc))


class XhsRuntimeAdapter:
    def __init__(self) -> None:
        pass

    async def create_session(self, payload: dict[str, Any]) -> "XhsRuntimeSession":
        return XhsRuntimeSession(payload)


class XhsRuntimeSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)
        self._browser: XhsBrowserSession | None = None
        self._client: XhsPlatformClient | None = None
        self._runtime_state = RuntimeSessionState()

    def snapshot(self) -> dict[str, Any]:
        return self._runtime_state.snapshot()

    async def close(self) -> None:
        client, browser = self._client, self._browser
        self._client = None
        self._browser = None
        if client is not None:
            await client.close()
        if browser is not None:
            await browser.close()

    async def run_login_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            action = payload.get("action")
            if action == "cookie":
                return self._runtime_state.apply_login_result(await self._login_by_cookie(payload))
            if action in {"qrcode", "phone_start", "phone_submit"}:
                raise RuntimeBackendError("not_supported", "login action is not implemented")
            return await self.get_login_status()
        except RuntimeBackendError:
            raise
        except Exception as exc:
            raise _to_backend_error(exc) from exc

    async def get_login_status(self) -> dict[str, Any]:
        client = await self._ensure_client()
        try:
            return self._runtime_state.apply_login_result(await client.login_status())
        except RuntimeBackendError:
            raise
        except Exception as exc:
            raise _to_backend_error(exc) from exc

    async def search_posts(self, payload: dict[str, Any], view: XhsResponseView = "full") -> dict[str, Any]:
        client = await self._ensure_client()
        try:
            data: XhsSearchPage
            raw: dict[str, Any]
            data, raw = await client.search_posts(payload)
            return self._runtime_state.apply_search_result(data, raw, payload, view=view)
        except RuntimeBackendError:
            raise
        except Exception as exc:
            raise _to_backend_error(exc) from exc

    async def open_note_from_search(self, note_id: str, view: XhsResponseView = "full") -> dict[str, Any]:
        search_item = self._runtime_state.get_search_item(note_id)
        note: XhsNoteDetail
        raw: dict[str, Any]
        note, raw = await self._open_note({**search_item, "_open_from_search": True})
        return self._runtime_state.apply_note_result(note, raw, view=view)

    async def open_note_by_xsec(self, payload: dict[str, Any], view: XhsResponseView = "full") -> dict[str, Any]:
        note: XhsNoteDetail
        raw: dict[str, Any]
        note, raw = await self._open_note(payload)
        return self._runtime_state.apply_note_result(note, raw, view=view)

    async def fetch_root_comments(self, note_id: str, cursor: str | None, limit: int, view: XhsResponseView = "full") -> dict[str, Any]:
        note_context = self._runtime_state.get_note_context(note_id)
        payload = {**note_context, "cursor": cursor or "", "limit": limit}
        client = await self._ensure_client()
        try:
            data: XhsRootCommentsData
            raw: dict[str, Any]
            data, raw = await client.root_comments(payload)
            return self._runtime_state.apply_root_comments_result(data, raw, note_context, view=view)
        except RuntimeBackendError:
            raise
        except Exception as exc:
            raise _to_backend_error(exc) from exc

    async def fetch_sub_comments(self, root_comment_id: str, cursor: str | None, limit: int, view: XhsResponseView = "full") -> dict[str, Any]:
        payload = self._runtime_state.build_sub_comments_payload(root_comment_id, cursor, limit)
        client = await self._ensure_client()
        try:
            data: XhsSubCommentsData
            raw: dict[str, Any]
            data, raw = await client.sub_comments(payload)
            return self._runtime_state.build_sub_comments_result(data, raw, view=view)
        except RuntimeBackendError:
            raise
        except Exception as exc:
            raise _to_backend_error(exc) from exc

    async def _login_by_cookie(self, payload: dict[str, Any]) -> dict[str, Any]:
        cookie = str(payload.get("cookie") or "").strip()
        require_cookie_keys(parse_cookie_header(cookie))
        browser, client = await self._ensure_browser_and_client()
        await browser.apply_cookie_header(cookie)
        return await client.login_status()

    async def _open_note(self, payload: dict[str, Any]) -> tuple[XhsNoteDetail, dict[str, Any]]:
        client = await self._ensure_client()
        try:
            return await client.open_note(payload)
        except RuntimeBackendError:
            raise
        except Exception as exc:
            raise _to_backend_error(exc) from exc

    async def _ensure_client(self) -> XhsPlatformClient:
        _browser, client = await self._ensure_browser_and_client()
        return client

    async def _discard_browser(self) -> None:
        client, browser = self._client, self._browser
        self._client = None
        self._browser = None
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

    async def _ensure_browser_and_client(self) -> tuple[XhsBrowserSession, XhsPlatformClient]:
        if self._browser is not None and self._client is not None:
            if not self._browser.is_alive():
                await self._discard_browser()
            else:
                return self._browser, self._client
        if self._browser is not None or self._client is not None:
            await self._discard_browser()
        user_data_dir = str(self._payload.get("user_data_dir") or "").strip()
        if not user_data_dir:
            raise RuntimeBackendError("missing_params", "user_data_dir is required")
        browser: XhsBrowserSession | None = None
        profile: BrowserProfile | None = None
        try:
            profile = await launch_browser_profile(user_data_dir)
            browser = XhsBrowserSession(profile)
            await browser.connect()
            client = XhsPlatformClient(browser)
            await client.refresh_cookies()
        except RuntimeBackendError:
            if browser is not None:
                await browser.close()
            elif profile is not None:
                await profile.close()
            raise
        except Exception as exc:
            if browser is not None:
                await browser.close()
            elif profile is not None:
                await profile.close()
            raise RuntimeBackendError("backend_unavailable", str(exc)) from exc
        self._browser = browser
        self._client = client
        return browser, client
