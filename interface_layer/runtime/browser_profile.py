from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from interface_layer.runtime.base import RuntimeBackendError


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass
class BrowserProfile:
    process: Any
    cdp_url: str

    async def close(self) -> None:
        await asyncio.to_thread(_wait_then_terminate_process, self.process)


async def launch_browser_profile(user_data_dir: str) -> BrowserProfile:
    return await asyncio.to_thread(_launch_browser_profile_sync, user_data_dir)


def _launch_browser_profile_sync(user_data_dir: str) -> BrowserProfile:
    browser_path, profile_dir = _resolve_browser_profile(user_data_dir)
    debug_port = _pick_debug_port()
    process = _launch_process(
        browser_path=browser_path,
        debug_port=debug_port,
        user_data_dir=str(profile_dir),
        headless=_env_flag("XHS_INTERFACE_BROWSER_HEADLESS", False),
    )
    timeout = int(os.getenv("XHS_INTERFACE_BROWSER_READY_TIMEOUT", "30") or "30")
    if not _wait_for_browser_ready(process, debug_port, timeout=timeout):
        _terminate_process(process)
        raise RuntimeBackendError(
            "backend_unavailable",
            f"browser did not expose CDP within {timeout}s",
            {"debug_port": debug_port, "user_data_dir": str(profile_dir)},
        )
    return BrowserProfile(process=process, cdp_url=f"http://127.0.0.1:{debug_port}")


def _resolve_browser_profile(user_data_dir: str) -> tuple[str, Path]:
    if not str(user_data_dir or "").strip():
        raise RuntimeBackendError("missing_params", "user_data_dir is required")
    browser_path = _detect_browser_path()
    if not browser_path:
        raise RuntimeBackendError("backend_unavailable", "no Chrome or Edge browser executable was found")
    profile_dir = Path(user_data_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return browser_path, profile_dir


def _detect_browser_path() -> str:
    env_path = str(os.getenv("XHS_BROWSER_PATH", "") or "").strip()
    if env_path:
        resolved = shutil.which(env_path) or env_path
        if Path(resolved).is_file():
            return resolved
    if platform.system() == "Windows":
        return _detect_windows_browser_path()
    for command in (
        "google-chrome",
        "google-chrome-stable",
        "google-chrome-beta",
        "google-chrome-unstable",
        "chromium-browser",
        "chromium",
        "microsoft-edge",
        "microsoft-edge-stable",
        "microsoft-edge-beta",
        "microsoft-edge-dev",
    ):
        browser_path = shutil.which(command)
        if browser_path:
            return browser_path
    return ""


def _detect_windows_browser_path() -> str:
    import winreg

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for name in ("chrome.exe", "msedge.exe"):
            key_path = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}"
            try:
                with winreg.OpenKey(root, key_path) as key:
                    value, _kind = winreg.QueryValueEx(key, "")
            except OSError:
                continue
            if value and Path(str(value)).is_file():
                return str(value)
    return ""


def _pick_debug_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _launch_process(*, browser_path: str, debug_port: int, user_data_dir: str, headless: bool) -> Any:
    args = [
        browser_path,
        f"--remote-debugging-port={debug_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={user_data_dir}",
    ]
    args.extend(_browser_switches(headless=headless))
    args.append("https://www.xiaohongshu.com/explore")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)


def _browser_switches(*, headless: bool) -> list[str]:
    args = [
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=TranslateUI",
        "--disable-ipc-flooding-protection",
        "--disable-hang-monitor",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--exclude-switches=enable-automation",
    ]
    args.extend(["--headless=new", "--disable-gpu"] if headless else ["--start-maximized"])
    return args


def _wait_for_browser_ready(process: Any, debug_port: int, *, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urlopen(f"http://127.0.0.1:{debug_port}/json/version", timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("webSocketDebuggerUrl"):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _wait_then_terminate_process(process: Any) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.wait(timeout=5)
        return
    except Exception:
        _terminate_process(process)


def _terminate_process(process: Any) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
