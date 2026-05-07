from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from interface_layer.services.session_store import SessionStore

from .prompts import register_prompts
from .resources import register_resources
from .tools import register_tools


def create_mcp_server(store: SessionStore) -> FastMCP:
    mcp = FastMCP(
        "XHS Interface Layer",
        instructions=(
            "在调用任何数据获取工具之前，必须先判断当前是否具备登录信息。"
            "如果用户已经提供登录信息，例如 cookie、二维码登录指令、手机号/验证码信息，"
            "或明确要求使用这些信息创建一个新的已登录 session，则创建新 session，"
            "bind 后执行对应登录流程，并且必须调用 xhs_login_get_status 确认 "
            "login.state=ready 后，才能继续调用数据获取工具。"
            "如果用户没有提供登录信息，不要创建新 session。应先调用 xhs_session_list "
            "查找空闲 session，然后逐个 bind，调用 xhs_login_get_status 验证登录态。"
            "只使用第一个返回 login.state=ready 的 session；对未 ready 的 session "
            "必须先 unbind，再尝试下一个空闲 session。"
            "如果没有任何空闲 session 能验证为 ready，则停止操作，向请求发起者索要登录信息。"
            "不要在没有 verified ready login 的情况下反复创建 session，也不要反复重试数据获取工具。"
            "以下数据获取工具都要求已经验证 login.state=ready：xhs_search_posts、"
            "xhs_note_open_from_search、xhs_note_open_by_xsec、xhs_comment_fetch_root、"
            "xhs_comment_fetch_sub。Handles 是短期上下文引用，必须与当前 session context 匹配。"
            "MCP 数据工具默认使用 compact 视图；除非请求发起者明确要求完整字段、原始调试信息或排查解析问题，"
            "不要传 view='full'。xhs_search_posts 只返回搜索结果摘要和打开帖子所需 handle，"
            "不是帖子详情；需要分析标题以外的正文、图片、标签、评论或完整互动上下文时，"
            "必须使用搜索结果中的 note_id 调用 xhs_note_open_from_search 打开帖子后再判断。"
            "同一个 session_id 是有状态游标：搜索会覆盖 search context，打开帖子会覆盖 note context，"
            "评论工具依赖当前 note context。因此同一 session_id 下所有数据工具必须严格串行调用，"
            "不要为了提速并发调用搜索、打开帖子、根评论或子评论工具；如需并行处理多个帖子，必须使用不同 session。"
        ),
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )
    register_tools(mcp, store)
    register_resources(mcp, store)
    register_prompts(mcp)
    return mcp
