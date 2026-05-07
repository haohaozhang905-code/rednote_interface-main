#!/usr/bin/env python3
"""
XHS Workflow CLI - 小红书工作流工具

连接到本地运行的服务，执行搜索、打开帖子、获取评论等操作，输出结构化 JSON。

用法:
    # 完整流水线：搜索→打开前 N 篇→获取评论→输出 JSON
    python3 xhs_workflow.py run <关键词> [--limit 3] [--output result.json]

    # 分步执行
    python3 xhs_workflow.py search <关键词> [--limit 10] [--sort general]
    python3 xhs_workflow.py note <note_id>
    python3 xhs_workflow.py comments <note_id> [--limit 5]
    python3 xhs_workflow.py status                          # 查看连接状态

选项:
    --base-url URL      服务地址（默认从 .session.json 或 http://127.0.0.1:8000 读取）
    --session SID       手动指定 session_id
    --token TOKEN       手动指定 bind_token
    --output FILE       输出到文件（默认 stdout）
    --pretty            格式化输出
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BASE_DIR = Path(__file__).resolve().parent
SESSION_FILE = BASE_DIR / ".session.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


# ── Session 信息管理 ──


def _load_session() -> dict[str, Any]:
    """从 .session.json 读取 session 信息。"""
    if SESSION_FILE.is_file():
        return json.loads(SESSION_FILE.read_text())
    return {}


def _get_base_url(args: argparse.Namespace) -> str:
    return (str(args.base_url or "") or os.environ.get("XHS_BASE_URL") or "").strip() or DEFAULT_BASE_URL


def _get_session_id(args: argparse.Namespace) -> str | None:
    if args.session:
        return args.session
    session = _load_session()
    return session.get("session_id")


def _get_token(args: argparse.Namespace) -> str | None:
    if args.token:
        return args.token
    session = _load_session()
    return session.get("token")


# ── API 调用 ──


async def _api_get(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    resp = await client.get(path)
    resp.raise_for_status()
    return resp.json()


async def _api_post(client: httpx.AsyncClient, path: str, json_data: dict[str, Any]) -> dict[str, Any]:
    """POST 请求，返回 JSON。即使 API 返回错误也正常返回，不抛异常。"""
    resp = await client.post(path, json=json_data)
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": {"code": "http_error", "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}}


async def cmd_status(args: argparse.Namespace) -> None:
    """查看服务连接状态。"""
    base_url = _get_base_url(args)
    session = _load_session()
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        # 检查服务是否存活
        try:
            sessions_resp = await client.get("/v1/sessions")
            sessions_resp.raise_for_status()
            data = sessions_resp.json()
            print(f"服务: {base_url}  [OK]", file=sys.stderr)
            print(f"会话数: {len(data['data']['items'])}", file=sys.stderr)
        except Exception as exc:
            print(f"服务: {base_url}  [无法连接: {exc}]", file=sys.stderr)
            sys.exit(1)

        if session.get("session_id"):
            sid = session["session_id"]
            try:
                status_resp = await client.get(f"/v1/sessions/{sid}/login/status?token={session.get('token', '')}")
                status_resp.raise_for_status()
                login = status_resp.json()["data"]
                print(f"当前 session: {sid}", file=sys.stderr)
                print(f"登录状态: {login.get('state')}", file=sys.stderr)
                if login.get("nickname"):
                    print(f"昵称: {login.get('nickname')}", file=sys.stderr)
            except Exception as exc:
                print(f"当前 session: {sid}  [状态检查失败: {exc}]", file=sys.stderr)

    # 输出 JSON
    result = {
        "ok": True,
        "service": base_url,
        "session": session.get("session_id"),
    }
    _output_json(result, args)


async def cmd_search(args: argparse.Namespace) -> None:
    """搜索帖子。"""
    base_url = _get_base_url(args)
    session_id = _get_session_id(args)
    token = _get_token(args)

    if not session_id or not token:
        print("[ERROR] 缺少 session_id/token。先通过 run.py 启动并登录，或手动指定 --session / --token", file=sys.stderr)
        sys.exit(1)

    keyword = args.keyword
    limit = min(args.limit or 20, 20)
    sort = args.sort or "general"
    page = args.page or 1

    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        payload = {
            "token": token,
            "keyword": keyword,
            "sort": sort,
            "page": page,
            "page_size": limit,
            "limit": limit,
            "filters": {
                "filter_note_type": "不限",
                "filter_note_time": "不限",
                "filter_note_range": "不限",
                "filter_pos_distance": "不限",
            },
        }
        result = await _api_post(client, f"/v1/sessions/{session_id}/search", payload)

    _output_json(result, args)


async def cmd_note(args: argparse.Namespace) -> None:
    """打开帖子详情。"""
    base_url = _get_base_url(args)
    session_id = _get_session_id(args)
    token = _get_token(args)

    if not session_id or not token:
        print("[ERROR] 缺少 session_id/token", file=sys.stderr)
        sys.exit(1)

    note_id = args.note_id

    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        payload = {"token": token, "note_id": note_id}
        result = await _api_post(client, f"/v1/sessions/{session_id}/notes/open-from-search", payload)

    _output_json(result, args)


async def cmd_comments(args: argparse.Namespace) -> None:
    """获取帖子根评论。"""
    base_url = _get_base_url(args)
    session_id = _get_session_id(args)
    token = _get_token(args)

    if not session_id or not token:
        print("[ERROR] 缺少 session_id/token", file=sys.stderr)
        sys.exit(1)

    note_id = args.note_id
    limit = min(args.limit or 10, 10)
    cursor = args.cursor or None

    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        payload = {"token": token, "note_id": note_id, "limit": limit}
        if cursor:
            payload["cursor"] = cursor
        result = await _api_post(client, f"/v1/sessions/{session_id}/comments/root", payload)

    _output_json(result, args)


async def cmd_run(args: argparse.Namespace) -> None:
    """完整流水线：搜索 → 打开帖子 → 获取评论 → 输出结构化 JSON。"""
    base_url = _get_base_url(args)
    session_id = _get_session_id(args)
    token = _get_token(args)

    if not session_id or not token:
        print("[ERROR] 缺少 session_id/token。请先启动 run.py", file=sys.stderr)
        sys.exit(1)

    keyword = args.keyword
    max_results = min(args.limit or 3, 10)
    get_comments = not args.no_comments

    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        # ── 1. 搜索 ──
        print(f"[1/3] 搜索: {keyword}", file=sys.stderr)
        search_payload = {
            "token": token,
            "keyword": keyword,
            "sort": args.sort or "general",
            "page": 1,
            "page_size": max_results,
            "limit": max_results,
            "filters": {
                "filter_note_type": "不限",
                "filter_note_time": "不限",
                "filter_note_range": "不限",
                "filter_pos_distance": "不限",
            },
        }
        search_result = await _api_post(client, f"/v1/sessions/{session_id}/search", search_payload)

        if not search_result.get("ok"):
            print(f"[ERROR] 搜索失败: {search_result}", file=sys.stderr)
            _output_json(search_result, args)
            return

        search_data = search_result["data"]["data"]
        items = search_data.get("items", [])

        print(f"  找到 {len(items)} 条结果", file=sys.stderr)

        if not items:
            _output_json({"ok": True, "keyword": keyword, "results": [], "meta": search_result.get("meta", {})}, args)
            return

        # ── 2. 依次打开帖子详情 ──
        print(f"[2/3] 打开帖子详情...", file=sys.stderr)
        enriched_items = []
        for i, item in enumerate(items):
            note_id = item.get("note_id")
            if not note_id:
                continue

            print(f"  [{i+1}/{len(items)}] note_id={note_id}", file=sys.stderr)
            try:
                note_payload = {"token": token, "note_id": note_id}
                note_result = await _api_post(client, f"/v1/sessions/{session_id}/notes/open-from-search", note_payload)
            except Exception as exc:
                print(f"    [WARN] 打开失败: {exc}", file=sys.stderr)
                enriched_items.append(_build_note_summary(item, None, None))
                continue

            note_data = note_result.get("data", {}).get("data", {}) if note_result.get("ok") else {}

            # ── 3. 可选：获取评论 ──
            comments_data = []
            if get_comments:
                try:
                    print(f"    [3/3] 获取评论...", file=sys.stderr)
                    cmt_payload = {"token": token, "note_id": note_id, "limit": min(args.comment_limit or 5, 10)}
                    cmt_result = await _api_post(client, f"/v1/sessions/{session_id}/comments/root", cmt_payload)
                    if cmt_result.get("ok"):
                        raw_comments = cmt_result["data"]["data"].get("comments", [])
                        comments_data = [_build_comment_summary(c) for c in raw_comments]
                except Exception as exc:
                    print(f"    [WARN] 评论获取失败: {exc}", file=sys.stderr)

            enriched_items.append(_build_note_summary(item, note_data, comments_data))

        # ── 构造最终输出 ──
        output = {
            "ok": True,
            "keyword": keyword,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "result_count": len(enriched_items),
            "results": enriched_items,
        }
        _output_json(output, args)
        print(f"\n完成！共 {len(enriched_items)} 条结果。", file=sys.stderr)


# ── 数据结构构造 ──


def _build_note_summary(search_item: dict, note_data: dict | None, comments: list | None) -> dict:
    """构造结构化的笔记摘要。"""
    summary = {
        "note_id": search_item.get("note_id", ""),
        "xsec_token": search_item.get("xsec_token", ""),
        "title": search_item.get("title", ""),
    }
    if note_data:
        summary["desc"] = note_data.get("desc", "")
        summary["time"] = note_data.get("time")
        summary["ip_location"] = note_data.get("ip_location", "")
        summary["author"] = {
            "nickname": note_data.get("user", {}).get("nickname", ""),
            "user_id": note_data.get("user", {}).get("user_id", ""),
            "avatar": note_data.get("user", {}).get("avatar", ""),
        }
        summary["interact_info"] = {
            "liked_count": note_data.get("interact_info", {}).get("liked_count", "0"),
            "collected_count": note_data.get("interact_info", {}).get("collected_count", "0"),
            "comment_count": note_data.get("interact_info", {}).get("comment_count", "0"),
            "shared_count": note_data.get("interact_info", {}).get("shared_count", "0"),
        }
        summary["images"] = [
            {"url": img.get("url_default", ""), "width": img.get("width", 0), "height": img.get("height", 0)}
            for img in (note_data.get("image_list") or [])
        ]
        summary["tags"] = [t.get("name", "") for t in (note_data.get("tag_list") or []) if t.get("name")]
    else:
        summary["author"] = {
            "nickname": search_item.get("user", {}).get("nickname", ""),
            "user_id": search_item.get("user", {}).get("user_id", ""),
        }
        summary["interact_info"] = {
            "liked_count": search_item.get("interact_info", {}).get("liked_count", "0"),
            "collected_count": search_item.get("interact_info", {}).get("collected_count", "0"),
            "comment_count": search_item.get("interact_info", {}).get("comment_count", "0"),
            "shared_count": search_item.get("interact_info", {}).get("shared_count", "0"),
        }
        summary["images"] = []
        summary["tags"] = []
        summary["desc"] = ""

    summary["comments"] = comments or []
    return summary


def _build_comment_summary(comment: dict) -> dict:
    """构造结构化的评论摘要。"""
    return {
        "comment_id": comment.get("comment_id", ""),
        "content": comment.get("content", ""),
        "like_count": comment.get("like_count", "0"),
        "ip_location": comment.get("ip_location", ""),
        "create_time": comment.get("create_time"),
        "user": {
            "nickname": comment.get("user_info", {}).get("nickname", ""),
            "user_id": comment.get("user_info", {}).get("user_id", ""),
        },
        "sub_comment_count": comment.get("sub_comment_count", "0"),
    }


def _output_json(data: dict, args: argparse.Namespace) -> None:
    """输出 JSON。"""
    indent = 2 if args.pretty else None
    ensure_ascii = args.ascii if hasattr(args, "ascii") else True
    json_str = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)

    output_path = args.output if hasattr(args, "output") and args.output else None
    if output_path:
        Path(output_path).write_text(json_str)
        print(f"已写入: {output_path}", file=sys.stderr)
    else:
        print(json_str)


# ── CLI ──


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="XHS Workflow CLI - 小红书工作流工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--base-url", default=None, help="服务地址（默认从 .session.json 或 http://127.0.0.1:8000）")
    parser.add_argument("--session", default=None, help="手动指定 session_id")
    parser.add_argument("--token", default=None, help="手动指定 bind_token")
    parser.add_argument("--output", default=None, help="输出到文件")
    parser.add_argument("--pretty", action="store_true", help="格式化输出")
    parser.add_argument("--ascii", action="store_true", help="ASCII 转义输出")

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="查看服务连接状态")

    # search
    p_search = sub.add_parser("search", help="搜索帖子")
    p_search.add_argument("keyword", help="搜索关键词")
    p_search.add_argument("--limit", type=int, default=10, help="返回条数（最大 20）")
    p_search.add_argument("--sort", default="general", choices=["general", "time_descending", "popularity_descending", "comment_descending", "collect_descending"])
    p_search.add_argument("--page", type=int, default=1, help="页码")

    # note
    p_note = sub.add_parser("note", help="打开帖子详情")
    p_note.add_argument("note_id", help="笔记 ID")

    # comments
    p_cmt = sub.add_parser("comments", help="获取帖子评论")
    p_cmt.add_argument("note_id", help="笔记 ID")
    p_cmt.add_argument("--limit", type=int, default=10, help="评论条数（最大 10）")
    p_cmt.add_argument("--cursor", default=None, help="分页游标")

    # run (full pipeline)
    p_run = sub.add_parser("run", help="完整流水线：搜索→打开→获取评论→输出 JSON")
    p_run.add_argument("keyword", help="搜索关键词")
    p_run.add_argument("--limit", type=int, default=3, help="处理前 N 篇帖子（最大 10，默认 3）")
    p_run.add_argument("--sort", default="general", choices=["general", "time_descending", "popularity_descending", "comment_descending", "collect_descending"])
    p_run.add_argument("--comment-limit", type=int, default=5, help="每篇帖子获取评论数（最大 10）")
    p_run.add_argument("--no-comments", action="store_true", help="不获取评论")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "search": cmd_search,
        "note": cmd_note,
        "comments": cmd_comments,
        "run": cmd_run,
    }

    coro = commands[args.command](args)
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
