from __future__ import annotations

import asyncio
import time
from http.cookies import SimpleCookie
from typing import Any, Callable, Awaitable
from urllib.parse import quote

from interface_layer.runtime.base import RuntimeBackendError
from interface_layer.runtime.browser_profile import BrowserProfile

_PERSISTENT_COOKIE_TTL_SECONDS = 180 * 24 * 60 * 60


class XhsBrowserSession:
    def __init__(self, profile: BrowserProfile) -> None:
        self._profile = profile
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._created_page = False

    @property
    def page(self) -> Any:
        if self._page is None:
            raise RuntimeBackendError("detached", "browser page is not initialized")
        return self._page

    async def connect(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise RuntimeBackendError("backend_unavailable", "playwright import failed", {"error": str(exc)}) from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(self._profile.cdp_url)
        self._context, self._page, self._created_page = await self._pick_context_page(self._browser)

    def is_alive(self) -> bool:
        try:
            return bool(
                self._browser is not None
                and self._browser.is_connected()
                and self._context is not None
                and self._page is not None
                and not self._page.is_closed()
            )
        except Exception:
            return False

    async def apply_cookie_header(self, cookie_header: str) -> None:
        cookies = cookie_header_to_playwright_cookies(cookie_header)
        if cookies:
            await self.context.add_cookies(cookies)
            await self.ensure_explore_page()

    async def ensure_explore_page(self) -> None:
        page = self.page
        if page.is_closed():
            page = await self.context.new_page()
            self._page = page
            self._created_page = True
        if "xiaohongshu.com" not in str(getattr(page, "url", "") or ""):
            await page.goto("https://www.xiaohongshu.com/explore", wait_until="load")
            await page.wait_for_timeout(3000)

    async def cookie_state(self) -> tuple[str, dict[str, str]]:
        cookies = await self.context.cookies()
        pairs: list[str] = []
        cookie_dict: dict[str, str] = {}
        for item in cookies:
            domain = str(item.get("domain") or "")
            if "xiaohongshu.com" not in domain and "xhscdn.com" not in domain:
                continue
            name = str(item.get("name") or "")
            value = str(item.get("value") or "")
            if not name:
                continue
            cookie_dict[name] = value
            pairs.append(f"{name}={value}")
        return "; ".join(pairs), cookie_dict

    async def wait_for_json_response(self, api_path: str, trigger: Callable[[], Awaitable[None]], timeout_seconds: float = 20) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        response_future = loop.create_future()

        async def on_response(response: Any) -> None:
            if api_path not in str(getattr(response, "url", "") or "") or response_future.done():
                return
            try:
                payload = await response.json()
                if isinstance(payload, dict) and payload.get("success") is True and isinstance(payload.get("data"), dict):
                    response_future.set_result(payload["data"])
                else:
                    response_future.set_exception(RuntimeError(f"response failed: status={getattr(response, 'status', '')}"))
            except Exception as exc:
                if not response_future.done():
                    response_future.set_exception(exc)

        self.page.on("response", on_response)
        try:
            await trigger()
            return await asyncio.wait_for(response_future, timeout=timeout_seconds)
        finally:
            try:
                self.page.remove_listener("response", on_response)
            except Exception:
                pass

    async def goto_search_and_capture(self, keyword: str) -> dict[str, Any]:
        encoded = quote(str(keyword or ""))
        url = f"https://www.xiaohongshu.com/search_result?keyword={encoded}&source=web_explore_feed"
        return await self.wait_for_json_response(
            "/api/sns/web/v1/search/notes",
            lambda: self.page.goto(url, wait_until="load", timeout=20000),
        )

    async def goto_note_comments_and_capture(self, note_id: str, note_token: str) -> dict[str, Any]:
        token = quote(str(note_token or ""))
        url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_search"
        return await self.wait_for_json_response(
            "/api/sns/web/v2/comment/page",
            lambda: self.page.goto(url, wait_until="load", timeout=20000),
        )

    async def close(self) -> None:
        try:
            if self._created_page and self._page is not None and not self._page.is_closed():
                await self._page.close()
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
        finally:
            self._page = None
            self._context = None
            self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
            await self._profile.close()

    @property
    def context(self) -> Any:
        if self._context is None:
            raise RuntimeBackendError("detached", "browser context is not initialized")
        return self._context

    @staticmethod
    async def _pick_context_page(browser: Any) -> tuple[Any, Any, bool]:
        contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeBackendError("detached", "connected browser has no context")
        for context in contexts:
            for page in list(context.pages):
                if "xiaohongshu.com" in str(getattr(page, "url", "") or ""):
                    return context, page, False
        context = contexts[0]
        if context.pages:
            page = context.pages[-1]
            await page.goto("https://www.xiaohongshu.com/explore", wait_until="load")
            await page.wait_for_timeout(3000)
            return context, page, False
        page = await context.new_page()
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="load")
        await page.wait_for_timeout(3000)
        return context, page, True


def cookie_header_to_playwright_cookies(cookie_header: str) -> list[dict[str, Any]]:
    parsed = SimpleCookie()
    parsed.load(str(cookie_header or ""))
    expires = int(time.time()) + _PERSISTENT_COOKIE_TTL_SECONDS
    return [
        {"name": key, "value": morsel.value, "domain": ".xiaohongshu.com", "path": "/", "expires": expires}
        for key, morsel in parsed.items()
        if str(morsel.value or "")
    ]
