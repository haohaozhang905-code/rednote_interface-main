from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(name="xhs_cookie_login_workflow", description="使用用户提供的 cookie 创建并验证一个新的已登录 session。")
    def cookie_login_workflow() -> str:
        return (
            "当用户已经提供 cookie 时，创建新 session，bind 后调用 "
            "xhs_login_run_action，action='cookie'，cookie 必须包含 a1 和 "
            "web_session。随后调用 xhs_login_get_status 检查登录态。只有 "
            "login.state=ready 时，才能继续搜索、打开帖子或获取评论。"
        )

    @mcp.prompt(name="xhs_search_open_comment_workflow", description="在已验证登录后搜索帖子、打开帖子并读取评论。")
    def search_open_comment_workflow() -> str:
        return (
            "调用数据获取工具前必须已验证 login.state=ready。先调用 "
            "xhs_search_posts 搜索小红书帖子，再使用搜索结果返回的 note_id "
            "调用 xhs_note_open_from_search 打开帖子。打开后用当前 note_id "
            "调用 xhs_comment_fetch_root 获取根评论；如需子评论，使用根评论结果里的 "
            "root_comment_id 调用 xhs_comment_fetch_sub。"
        )

    @mcp.prompt(name="xhs_recover_from_context_error", description="处理 stale_context、invalid_context 等上下文失效错误。")
    def recover_from_context_error() -> str:
        return (
            "遇到 stale_context 时，重新搜索，并只使用新搜索结果中的 note_id。"
            "获取评论时遇到 invalid_context，应重新打开对应帖子，再重新获取根评论，"
            "之后才能继续请求子评论。不要复用不属于当前 session context 的 note_id、"
            "xsec_token、root_comment_id 或其他短期 handle。"
        )
