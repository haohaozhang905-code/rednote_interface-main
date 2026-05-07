#!/usr/bin/env python3
"""
XHS Interface Service - 服务启动入口

一键启动服务，支持环境变量配置 Cookie 自动登录。

用法:
    XHS_COOKIE="a1=xxx; web_session=xxx" python3 run.py
    python3 run.py --mock                    # Mock 模式，无需浏览器/Cookie
    python3 run.py --port 9000               # 自定义端口
    python3 run.py --host 0.0.0.0            # 监听所有网卡
    python3 run.py --headless                # 无头浏览器模式（服务器部署）

环境变量:
    XHS_COOKIE              小红书 Cookie（a1 + web_session）
    XHS_BROWSER_PATH        自定义 Chrome 浏览器路径
    XHS_BROWSER_HEADLESS    无头模式（true/false）
    XHS_INTERFACE_RUNTIME   运行模式: xhs（默认）或 mock
    XHS_INTERFACE_DEBUG     调试模式（1/true/yes/on）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
import uvicorn

BASE_DIR = Path(__file__).resolve().parent

# ── 确保可以从项目根目录导入 interface_layer ──
sys.path.insert(0, str(BASE_DIR))


def _resolve_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="XHS Interface Service - 小红书接口服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--mock", action="store_true", help="Mock 模式运行，无需浏览器和 Cookie")
    parser.add_argument("--headless", action="store_true", help="浏览器以无头模式运行（服务器部署用）")
    parser.add_argument("--profile-root", default=None, help="浏览器 profile 存储目录（默认 browser_data/sessions）")
    parser.add_argument("--no-login", action="store_true", help="启动后不自动登录（即使设置了 XHS_COOKIE）")
    return parser.parse_args()


def _apply_env(args: argparse.Namespace) -> None:
    """将命令行参数同步到环境变量。"""
    if args.mock:
        os.environ.setdefault("XHS_INTERFACE_RUNTIME", "mock")
    if args.headless:
        os.environ.setdefault("XHS_BROWSER_HEADLESS", "true")
    if args.profile_root:
        os.environ["XHS_INTERFACE_PROFILE_ROOT"] = args.profile_root


def _cookie_from_env() -> str:
    return str(os.getenv("XHS_COOKIE", "") or "").strip()


async def _wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """等待 uvicorn server 就绪。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                return True
        except Exception:
            await asyncio.sleep(0.3)
    return False


async def _auto_login(base_url: str, cookie: str) -> dict:
    """自动创建 session、绑定并用 Cookie 登录。"""
    async with httpx.AsyncClient(timeout=60.0, base_url=base_url) as client:
        # 1. 创建 session
        create_resp = await client.post("/v1/sessions", json={"purpose": "auto-login"})
        create_resp.raise_for_status()
        session_id = create_resp.json()["data"]["session_id"]
        print(f"  session_id: {session_id}", flush=True)

        # 2. 绑定
        bind_resp = await client.post(f"/v1/sessions/{session_id}/bind")
        bind_resp.raise_for_status()
        token = bind_resp.json()["data"]["token"]
        print(f"  bind_token: {token}", flush=True)

        # 3. Cookie 登录
        login_resp = await client.post(
            f"/v1/sessions/{session_id}/login",
            json={"token": token, "action": "cookie", "cookie": cookie},
        )
        login_data = login_resp.json()
        if not login_data.get("ok"):
            error = login_data.get("error", {})
            print(f"  [WARN] 登录失败: code={error.get('code')}, msg={error.get('message')}", flush=True)
            return {"session_id": session_id, "token": token, "login": None}

        login_result = login_data["data"]
        if login_result.get("state") == "ready":
            print(f"  登录成功: 昵称={login_result.get('nickname')}, red_id={login_result.get('red_id')}", flush=True)
        else:
            print(f"  登录状态: {login_result.get('state')}", flush=True)

        return {"session_id": session_id, "token": token, "login": login_result}


def _save_session_info(info: dict, path: Path) -> None:
    """将 session 信息保存到文件，供 xhs_workflow.py 等工具使用。"""
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"  Session 信息已保存至: {path}", flush=True)


async def _async_main() -> None:
    args = _resolve_args()
    _apply_env(args)

    base_url = f"http://{args.host}:{args.port}"
    cookie = _cookie_from_env()
    session_file = BASE_DIR / ".session.json"

    # ── 打印启动信息 ──
    runtime_mode = os.getenv("XHS_INTERFACE_RUNTIME", "xhs")
    print("=" * 50, flush=True)
    print(f"  XHS Interface Service", flush=True)
    print(f"  运行模式: {runtime_mode}", flush=True)
    print(f"  监听地址: {base_url}", flush=True)
    if cookie:
        print(f"  Cookie: 已设置（{cookie[:20]}...）", flush=True)
    else:
        print(f"  Cookie: 未设置", flush=True)
    print("=" * 50, flush=True)

    # ── 启动 uvicorn 并自动登录 ──
    config = uvicorn.Config(
        "interface_layer.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    async def _post_start() -> None:
        if not await _wait_for_server(base_url):
            print("[ERROR] 服务启动超时", file=sys.stderr, flush=True)
            return

        if cookie and not args.no_login:
            info = await _auto_login(base_url, cookie)
            _save_session_info(info, session_file)
        print(f"\n服务已就绪。Ctrl+C 停止服务。\n", flush=True)

    # 并行执行：服务启动 + 启动后自动登录
    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve())
        tg.create_task(_post_start())


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        print("\n服务已停止。", flush=True)


if __name__ == "__main__":
    main()
