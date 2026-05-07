from __future__ import annotations

import hashlib
import json
import random
import time
from functools import cache
from typing import Any

_APP_ID = "xhs-pc-web"
_DEFAULT_PLATFORM = "Windows"
_DEFAULT_SIGN_VERSION = "4.2.6"
_DEFAULT_COMMON_VERSION = "4.84.2"
_CUSTOM_B64_ALPHABET = "ZmserbBoHQtNP+wOcza/LpngG8yJq42KWYj0DSfdikx3VT16IlUAFM97hECvuRX5"

# Keep the stable, understood parts in Python. Only the opaque mnsv2 function
# and browser runtime values are read from the Xiaohongshu page context.


def get_search_id() -> str:
    value = (int(time.time() * 1000) << 64) + int(random.uniform(0, 2147483646))
    return _base36encode(value)


def get_b3_trace_id() -> str:
    alphabet = "abcdef0123456789"
    return "".join(alphabet[random.randint(0, len(alphabet) - 1)] for _ in range(16))


async def build_sign_headers(page: Any, url: Any, data: Any, *, a1_cookie: str = "") -> dict[str, str]:
    payload_url = _build_payload_url(url, data)
    x_t = str(int(time.time() * 1000))
    try:
        await page.wait_for_function("typeof window.mnsv2 === 'function'", timeout=15000)
    except Exception:
        pass
    runtime = await page.evaluate(
        """
([url, payloadUrl, payloadHash, urlHash]) => {
  const storage = window.localStorage;
  const session = window.sessionStorage;
  const platform = /Win/i.test(window.navigator.platform || '') ? 'Windows' : (window.navigator.platform || 'PC');
  let x3 = '';
  try {
    x3 = window.mnsv2(payloadUrl, payloadHash, urlHash);
  } catch (_firstError) {
    x3 = window.mnsv2(payloadUrl, payloadHash);
  }
  return {
    x3,
    platform,
    b1: storage.getItem('b1') || '',
    b1b1: storage.getItem('b1b1') || '1',
    dsl: String(window._dsl || ''),
    dsllt: storage.getItem('dsllt') || '',
    sig_count: Number(session.getItem('sigCount') || '0') || 0,
  };
}
""",
        [str(url), payload_url, _md5_hex(payload_url), _md5_hex(str(url))],
    )
    platform = str(runtime.get("platform") or _DEFAULT_PLATFORM)
    x_s = _build_x_s(runtime.get("x3"), _js_typeof(data), platform)
    x_s_common = _build_x_s_common(runtime, a1_cookie, platform)
    return {
        "X-s": x_s,
        "X-t": x_t,
        "X-S-Common": x_s_common,
        "X-B3-Traceid": get_b3_trace_id(),
    }


def _build_payload_url(url: Any, data: Any) -> str:
    payload_url = str(url)
    if isinstance(data, (dict, list)):
        payload_url += json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    elif isinstance(data, str):
        payload_url += data
    return payload_url


def _js_typeof(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return "object"
    if value is None:
        return ""
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return ""


def _build_x_s(x3: Any, data_type: str, platform: str) -> str:
    payload = {
        "x0": _DEFAULT_SIGN_VERSION,
        "x1": _APP_ID,
        "x2": platform or _DEFAULT_PLATFORM,
        "x3": str(x3 or ""),
        "x4": data_type or "",
    }
    return "XYS_" + _xhs_base64(_json_bytes(payload))


def _build_x_s_common(runtime: dict[str, Any], a1_cookie: str, platform: str) -> str:
    b1 = str(runtime.get("b1") or "")
    b1b1 = str(runtime.get("b1b1") or "1")
    dsl = str(runtime.get("dsl") or "")
    dsllt = str(runtime.get("dsllt") or "")
    sig_count = int(runtime.get("sig_count") or 0)
    payload = {
        "s0": _platform_code(platform),
        "s1": "",
        "x0": b1b1,
        "x1": _DEFAULT_SIGN_VERSION,
        "x2": platform or _DEFAULT_PLATFORM,
        "x3": _APP_ID,
        "x4": _DEFAULT_COMMON_VERSION,
        "x5": str(a1_cookie or ""),
        "x6": "",
        "x7": "",
        "x8": b1,
        "x9": _mrc(b1),
        "x10": sig_count,
        "x11": "normal",
    }
    if dsl or dsllt:
        payload["x12"] = dsllt + ";" + dsl
    return _xhs_base64(_json_bytes(payload))


def _platform_code(platform: str) -> int:
    return 5 if "win" in str(platform or "").lower() else 5


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _mrc(value: str) -> int:
    output = -1
    for char in value:
        output = _mrc_table()[(output & 255) ^ ord(char)] ^ _mrc_right_shift(output, 8)
    return output ^ -1 ^ 3988292384


def _mrc_right_shift(value: int, bits: int) -> int:
    return (value & 0xFFFFFFFF) >> bits


@cache
def _mrc_table() -> tuple[int, ...]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = 0xEDB88320 ^ (value >> 1) if value & 1 else value >> 1
        table.append(value)
    return tuple(table)


def _xhs_base64(raw: bytes) -> str:
    result = []
    full_len = len(raw) - len(raw) % 3
    for index in range(0, full_len, 3):
        triplet = (raw[index] << 16) + (raw[index + 1] << 8) + raw[index + 2]
        result.append(_encode_triplet(triplet))
    remain = len(raw) - full_len
    if remain == 1:
        value = raw[-1]
        result.append(_CUSTOM_B64_ALPHABET[value >> 2] + _CUSTOM_B64_ALPHABET[(value << 4) & 63] + "==")
    elif remain == 2:
        value = (raw[-2] << 8) + raw[-1]
        result.append(
            _CUSTOM_B64_ALPHABET[value >> 10]
            + _CUSTOM_B64_ALPHABET[(value >> 4) & 63]
            + _CUSTOM_B64_ALPHABET[(value << 2) & 63]
            + "="
        )
    return "".join(result)


def _encode_triplet(value: int) -> str:
    return (
        _CUSTOM_B64_ALPHABET[(value >> 18) & 63]
        + _CUSTOM_B64_ALPHABET[(value >> 12) & 63]
        + _CUSTOM_B64_ALPHABET[(value >> 6) & 63]
        + _CUSTOM_B64_ALPHABET[value & 63]
    )


def _base36encode(number: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if number == 0:
        return "0"
    sign = ""
    if number < 0:
        sign = "-"
        number = -number
    result = ""
    while number:
        number, index = divmod(number, len(alphabet))
        result = alphabet[index] + result
    return sign + result
