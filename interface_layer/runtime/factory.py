from __future__ import annotations

import os

from interface_layer.runtime.base import RuntimeBackend
from interface_layer.runtime.mock import MockRuntime


def build_runtime() -> RuntimeBackend:
    mode = str(os.getenv("XHS_INTERFACE_RUNTIME", "xhs")).strip().lower() or "xhs"
    if mode == "mock":
        return MockRuntime()
    if mode == "xhs":
        from interface_layer.runtime.xhs_runtime_adapter import XhsRuntimeAdapter

        return XhsRuntimeAdapter()
    raise ValueError(f"unknown XHS_INTERFACE_RUNTIME: {mode}")
