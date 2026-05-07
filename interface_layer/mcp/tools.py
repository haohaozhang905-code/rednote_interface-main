from __future__ import annotations

from typing import Any, Callable, Coroutine

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from interface_layer.models.requests import (
    CookieLoginActionRequest,
    CreateSessionRequest,
    FetchRootCommentsRequest,
    FetchSubCommentsRequest,
    OpenNoteByXsecRequest,
    OpenNoteFromSearchRequest,
    PhoneStartLoginActionRequest,
    PhoneSubmitLoginActionRequest,
    QrcodeLoginActionRequest,
    SearchFilters,
    SearchNoteRangeFilter,
    SearchNoteTimeFilter,
    SearchNoteTypeFilter,
    SearchPosDistanceFilter,
    SearchPostsRequest,
    SearchSort,
    TokenRequest,
)
from interface_layer.services.errors import InterfaceError
from interface_layer.services.session_store import SessionStore

from .schemas import failure, success


def register_tools(mcp: FastMCP, store: SessionStore) -> None:
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)

    @mcp.tool(annotations=read)
    def xhs_session_list(bound: bool | None = None, status: str | None = None) -> dict[str, Any]:
        """列出 session。没有 cookie、二维码、手机号/验证码等登录信息时，先用本工具查找空闲 session，再逐个 bind 并验证登录态；列表中的 login 只作线索，不代表已验证可用。

        参数说明：
        - bound: JSON 布尔值 true/false 或 null；true 只返回已绑定 session，false 只返回空闲 session，null 不筛选。
        - status: 字符串或 null；可传 "idle"、"bound"，null 不筛选。字符串值必须按双引号内容原样传入。
        """
        return _wrap("xhs_session_list", lambda: success("xhs_session_list", {"items": store.list_sessions(bound, status)}))

    @mcp.tool(annotations=write)
    async def xhs_session_create(purpose: str | None = None) -> dict[str, Any]:
        """创建新 session。调用前必须确认手头有登录信息，或用户明确要求新建登录 session；没有登录信息时不要调用本工具，应先遍历空闲 session。

        参数说明：
        - purpose: 字符串或 null，最多 256 字符；用于标记用途，例如 "cookie-login"。字符串值必须用双引号包裹。
        """
        request = CreateSessionRequest(purpose=purpose)
        return await _awrap(
            "xhs_session_create",
            None,
            lambda: store.create_session(request.purpose),
        )

    @mcp.tool(annotations=write)
    async def xhs_session_bind(session_id: str) -> dict[str, Any]:
        """绑定空闲 session 并获取 token。绑定后必须立刻调用 xhs_login_get_status；只有 login.state=ready 才能继续获取数据。同一 session 的后续工具必须串行调用。任务完成、失败或放弃时必须调用 xhs_session_unbind 释放 session。

        参数说明：
        - session_id: 字符串，来自 xhs_session_list 或 xhs_session_create 的返回值，例如 "sess_xxx"。必须用双引号包裹。
        """
        return await _awrap("xhs_session_bind", session_id, lambda: store.bind(session_id))

    @mcp.tool(annotations=write)
    def xhs_session_unbind(session_id: str, token: str) -> dict[str, Any]:
        """释放已绑定 session。每次完成 MCP 任务、遇到不可恢复失败、放弃当前 session 或遍历到未 ready session 时，都必须调用本工具。

        参数说明：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        """
        request = TokenRequest(token=token)
        return _wrap("xhs_session_unbind", lambda: _unbind(store, session_id, request.token), session_id=session_id)

    @mcp.tool(annotations=write)
    async def xhs_login_run_action(
        session_id: str,
        token: str,
        action: str,
        cookie: str | None = None,
        phone: str | None = None,
        code: str | None = None,
    ) -> dict[str, Any]:
        """执行登录动作。只有用户提供对应登录信息时才调用；没有 cookie、二维码或手机号/验证码时，不要反复创建 session 试登录。同一 session 内不要与其他工具并发。任务结束或失败后记得 unbind。

        参数说明：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        - action: 字符串枚举，只能传 "qrcode"、"cookie"、"phone_start"、"phone_submit"，必须按双引号内容原样传入。
        - cookie: 字符串或 null；action 为 "cookie" 时必填，传完整 cookie 字符串。
        - phone: 字符串或 null；action 为 "phone_start" 时必填，传手机号字符串。
        - code: 字符串或 null；action 为 "phone_submit" 时必填，传短信验证码字符串。
        """
        request = _login_request(token, action, cookie, phone, code)
        return await _awrap("xhs_login_run_action", session_id, lambda: store.run_login_action(session_id, request))

    @mcp.tool(annotations=read)
    async def xhs_login_get_status(session_id: str, token: str | None = None) -> dict[str, Any]:
        """检查登录态。这是调用数据工具前的必经步骤；只有返回 login.state=ready 的 session 才能搜索、打开帖子或获取评论。若返回 backend_unavailable，说明浏览器/runtime 后端不可用，不代表登录凭证一定失效，也不等同 login_required；先等待后重试 xhs_login_get_status，持续失败再由管理员重启服务或检查浏览器 CDP。失败后不要继续搜索。

        参数说明：
        - session_id: 字符串，要检查的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串或 null；已绑定 session 建议传 "btok_xxx"，未绑定只读检查可传 null。
        """
        return await _awrap("xhs_login_get_status", session_id, lambda: store.get_login_status(session_id, token))

    @mcp.tool(annotations=write)
    async def xhs_search_posts(
        session_id: str,
        token: str,
        keyword: str,
        sort: SearchSort = "general",
        page: int = 1,
        page_size: int = 20,
        limit: int = 20,
        filter_note_type: SearchNoteTypeFilter = "不限",
        filter_note_time: SearchNoteTimeFilter = "不限",
        filter_note_range: SearchNoteRangeFilter = "不限",
        filter_pos_distance: SearchPosDistanceFilter = "不限",
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        """搜索小红书帖子。调用前必须已验证 login.state=ready；会更新当前 session 的搜索上下文。同一 session 内不要并发搜索、打开帖子或获取评论。搜索结果的 note_id 可用于 xhs_note_open_from_search；任务结束后必须 unbind。

        参数取值必须严格使用字符串；枚举值请按下列双引号内容原样传入，避免传入未加引号的标识符或近义词：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        - keyword: 字符串，搜索关键词，例如 "露营"。必须用双引号包裹。
        - sort: "general", "time_descending", "popularity_descending", "comment_descending", "collect_descending"。
        - page: 整数，最小 1，默认 1。
        - page_size: 整数，1 到 20，默认 20。
        - limit: 整数，1 到 20，默认 20。
        - filter_note_type: "不限", "视频笔记", "普通笔记"，默认 "不限"。
        - filter_note_time: "不限", "一天内", "一周内", "半年内"，默认 "不限"。
        - filter_note_range: "不限", "已看过", "未看过", "已关注"，默认 "不限"。
        - filter_pos_distance: "不限", "同城", "附近"，默认 "不限"。
        - latitude: 数字或 null；纬度，仅在 filter_pos_distance 为 "同城" 或 "附近" 时传入。
        - longitude: 数字或 null；经度，仅在 filter_pos_distance 为 "同城" 或 "附近" 时传入。
        """
        filters = SearchFilters(
            filter_note_type=filter_note_type,
            filter_note_time=filter_note_time,
            filter_note_range=filter_note_range,
            filter_pos_distance=filter_pos_distance,
            latitude=latitude,
            longitude=longitude,
        )
        request = SearchPostsRequest(
            token=token,
            keyword=keyword,
            sort=sort,
            page=page,
            page_size=page_size,
            limit=limit,
            filters=filters,
        )
        return await _awrap("xhs_search_posts", session_id, lambda: store.search_posts(session_id, token, request, "compact"))

    @mcp.tool(annotations=write)
    async def xhs_note_open_from_search(session_id: str, token: str, note_id: str) -> dict[str, Any]:
        """打开搜索结果中的帖子并获取帖子详情。这里是 note_opened 级证据，可以支持笔记本身的观察，但评论结论仍需继续拉评论。搜索结果不能替代本工具：分析正文 desc、图片、标签、作者详情、完整互动数或后续评论前，必须先打开帖子。note_id 必须来自当前 session 最近一次 xhs_search_posts 结果；本工具会切换当前 note context，同一 session 内必须串行调用。任务结束后必须 unbind。

        参数说明：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        - note_id: 字符串，来自当前 session 最近一次 xhs_search_posts 结果。必须用双引号包裹。
        """
        request = OpenNoteFromSearchRequest(token=token, note_id=note_id)
        return await _awrap("xhs_note_open_from_search", session_id, lambda: store.open_from_search(session_id, request.token, request.note_id, "compact"))

    @mcp.tool(annotations=write)
    async def xhs_note_open_by_xsec(session_id: str, token: str, note_id: str, xsec_token: str) -> dict[str, Any]:
        """通过 note_id 和 xsec_token 打开帖子并获取帖子详情。这里是 note_opened 级证据，可以支持笔记本身的观察，但评论结论仍需继续拉评论。用于已有可靠 note_id/xsec_token 的场景；若 note_id 来自刚搜索的结果，优先调用 xhs_note_open_from_search。xsec_token 是短期上下文值，必须与当前 note_id 和 session 匹配；本工具会切换当前 note context，必须串行调用。任务结束后必须 unbind。

        参数说明：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        - note_id: 字符串，目标帖子 id。必须用双引号包裹。
        - xsec_token: 字符串，和 note_id 配套的短期上下文 token。必须用双引号包裹。
        """
        request = OpenNoteByXsecRequest(token=token, note_id=note_id, xsec_token=xsec_token)
        return await _awrap("xhs_note_open_by_xsec", session_id, lambda: store.open_by_xsec(session_id, token, request, "compact"))

    @mcp.tool(annotations=write)
    async def xhs_comment_fetch_root(session_id: str, token: str, note_id: str, cursor: str | None = None, limit: int = 10) -> dict[str, Any]:
        """获取当前已打开帖子的根评论。这里是 root_comments 级证据，只代表当前页根评论；若响应里有 sub_comment_has_more，继续拉子评论，若 has_more 才继续翻根评论。必须先用 xhs_note_open_from_search 或 xhs_note_open_by_xsec 打开当前 note_id 对应的帖子；搜索结果本身不能直接获取评论。cursor 只能沿用本工具返回的下一页游标。同一 session 内不要并发请求评论页或切换帖子。任务结束后必须 unbind。

        参数说明：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        - note_id: 字符串，必须匹配当前已打开的帖子。必须用双引号包裹。
        - cursor: 字符串或 null；首页传 null，下一页只能传本工具上次返回的 cursor。
        - limit: 整数，1 到 10，默认 10。
        """
        request = FetchRootCommentsRequest(token=token, note_id=note_id, cursor=cursor, limit=limit)
        return await _awrap("xhs_comment_fetch_root", session_id, lambda: store.root_comments(session_id, token, request.note_id, request.cursor, request.limit, "compact"))

    @mcp.tool(annotations=write)
    async def xhs_comment_fetch_sub(session_id: str, token: str, root_comment_id: str, cursor: str | None = None, limit: int = 5) -> dict[str, Any]:
        """获取当前已打开帖子下某条根评论的子评论。这里是 sub_comments 级证据；limit 上限固定为 5，只代表当前 root_comment_id 的分页子评论，不是全量。root_comment_id 必须来自当前 session 最近一次 xhs_comment_fetch_root 结果；搜索结果或帖子详情不会提供可直接分页的子评论上下文。cursor 只能沿用本工具返回的下一页游标。同一 session 内不要并发请求子评论、根评论或切换帖子。任务结束后必须 unbind。

        参数说明：
        - session_id: 字符串，当前绑定的 session id，例如 "sess_xxx"。必须用双引号包裹。
        - token: 字符串，xhs_session_bind 返回的绑定 token，例如 "btok_xxx"。必须用双引号包裹。
        - root_comment_id: 字符串，来自当前 session 最近一次 xhs_comment_fetch_root 结果。必须用双引号包裹。
        - cursor: 字符串或 null；首页传 null，下一页只能传本工具上次返回的 cursor。
        - limit: 整数，1 到 5，默认 5。
        """
        request = FetchSubCommentsRequest(token=token, root_comment_id=root_comment_id, cursor=cursor, limit=limit)
        return await _awrap("xhs_comment_fetch_sub", session_id, lambda: store.sub_comments(session_id, token, request.root_comment_id, request.cursor, request.limit, "compact"))


def _wrap(operation: str, fn: Callable[[], dict[str, Any]], *, session_id: str | None = None) -> dict[str, Any]:
    try:
        return fn()
    except InterfaceError as exc:
        return failure(operation, exc, session_id=session_id)


async def _awrap(operation: str, session_id: str | None, fn: Callable[[], Coroutine[Any, Any, dict[str, Any]]]) -> dict[str, Any]:
    try:
        return success(operation, await fn(), session_id=session_id)
    except InterfaceError as exc:
        return failure(operation, exc, session_id=session_id)


def _login_request(token: str, action: str, cookie: str | None, phone: str | None, code: str | None) -> Any:
    if action == "cookie":
        return CookieLoginActionRequest(token=token, action="cookie", cookie=cookie or "")
    if action == "qrcode":
        return QrcodeLoginActionRequest(token=token, action="qrcode")
    if action == "phone_start":
        return PhoneStartLoginActionRequest(token=token, action="phone_start", phone=phone or "")
    if action == "phone_submit":
        return PhoneSubmitLoginActionRequest(token=token, action="phone_submit", code=code or "")
    raise InterfaceError("invalid_request", details={"action": action})


def _unbind(store: SessionStore, session_id: str, token: str) -> dict[str, Any]:
    store.unbind(session_id, token)
    return success("xhs_session_unbind", {}, session_id=session_id)
