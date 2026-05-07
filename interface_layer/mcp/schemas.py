from __future__ import annotations

from typing import Any

from interface_layer.services.errors import InterfaceError


def success(operation: str, data: dict[str, Any] | None = None, *, session_id: str | None = None) -> dict[str, Any]:
    payload = dict(data or {})
    guidance = _success_guidance(operation, payload)
    if guidance is not None:
        payload["guidance"] = guidance
    return {"ok": True, "data": payload}


def failure(operation: str, error: InterfaceError, *, session_id: str | None = None) -> dict[str, Any]:
    spec = error.spec
    error_payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message or spec.message,
            "retryable": spec.retryable,
            "action": spec.action,
            "details": error.details,
        },
    }
    guidance = _failure_guidance(operation, error)
    if guidance is not None:
        error_payload["error"]["guidance"] = guidance
    return error_payload


def _success_guidance(operation: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if operation == "xhs_login_get_status":
        state = str(_get_value(data, "state", "") or "")
        if state == "ready":
            return {
                "evidence_level": "login_ready",
                "can_support_claims": False,
                "next_action_type": "tool",
                "next_action": "xhs_search_posts",
            }
        required_action = str(_get_value(data, "required_action", "none") or "none")
        strategy = required_action if required_action != "none" else "login_required"
        return {
            "evidence_level": "none",
            "can_support_claims": False,
            "next_action_type": "strategy",
            "next_action": "none",
            "strategy": strategy,
            "recovery_hint": "当前登录态还没就绪，不要继续搜索；先按 required_action 处理后再重试 xhs_login_get_status。",
        }
    if operation == "xhs_search_posts":
        payload = _result_payload(data)
        has_more = bool(_get_value(payload, "has_more", False))
        guidance = {
            "evidence_level": "candidate_only",
            "can_support_claims": False,
            "next_action_type": "tool",
            "next_action": "xhs_note_open_from_search",
            "claim_scope": [],
        }
        if has_more:
            guidance["continuation"] = {
                "when": "need_more_candidates",
                "next_action": "xhs_search_posts",
                "page_strategy": "same keyword/sort/filters with page + 1",
                "only_if_has_more": True,
            }
            guidance["avoid_strategy"] = "do not switch keywords just to get more results for the same topic"
        else:
            guidance["continuation"] = {
                "when": "need_more_candidates",
                "next_action": "none",
                "reason": "search response has_more is false",
            }
        return guidance
    if operation in {"xhs_note_open_from_search", "xhs_note_open_by_xsec"}:
        return {
            "evidence_level": "note_opened",
            "can_support_claims": True,
            "claim_scope": ["note_content"],
            "needs_more_evidence_for": ["comment_sentiment", "audience_reaction", "trend_or_group_claims"],
            "next_action_type": "tool",
            "next_action": "xhs_comment_fetch_root",
        }
    if operation == "xhs_comment_fetch_root":
        payload = _result_payload(data)
        comments = _comments_from_result(payload)
        root_count = len(comments)
        has_more = bool(_get_value(payload, "has_more", False))
        has_embedded_sub_comments = any(_has_embedded_sub_comments(comment) for comment in comments)
        roots_with_more_sub_comments = sum(1 for comment in comments if bool(_get_value(comment, "sub_comment_has_more", False)))
        next_action = "xhs_comment_fetch_sub" if roots_with_more_sub_comments > 0 else ("xhs_comment_fetch_root" if has_more else "none")
        recommended_actions = _root_comment_actions(roots_with_more_sub_comments, has_more)
        return {
            "evidence_level": "root_comments",
            "can_support_claims": True,
            "claim_scope": ["root_comment_content"],
            "coverage": {
                "root_count": root_count,
                "has_more": has_more,
                "has_embedded_sub_comments": has_embedded_sub_comments,
                "roots_with_more_sub_comments": roots_with_more_sub_comments,
            },
            "next_action_type": "tool" if next_action != "none" else "none",
            "next_action": next_action,
            "recommended_actions": recommended_actions,
        }
    if operation == "xhs_comment_fetch_sub":
        payload = _result_payload(data)
        comments = _comments_from_result(payload)
        has_more = bool(_get_value(payload, "has_more", False))
        guidance = {
            "evidence_level": "sub_comments",
            "can_support_claims": True,
            "claim_scope": ["sub_comment_content"],
            "coverage": {
                "sub_count": len(comments),
                "has_more": has_more,
                "limit_cap": 5,
            },
            "next_action_type": "tool" if has_more else "none",
            "next_action": "xhs_comment_fetch_sub" if has_more else "none",
        }
        if has_more:
            guidance["continuation"] = {
                "reuse_root_comment_id": True,
                "use_cursor_from_response": True,
            }
        return guidance
    return None


def _failure_guidance(operation: str, error: InterfaceError) -> dict[str, Any] | None:
    if error.code == "backend_unavailable":
        return _backend_unavailable_guidance()
    if error.code == "stale_context":
        return {
            "next_action_type": "tool",
            "next_action": "xhs_search_posts",
            "recovery_hint": "重新搜索，并且只使用新搜索结果里的 note_id。",
        }
    if error.code == "invalid_context":
        return {
            "next_action_type": "tool",
            "next_action": "xhs_note_open_from_search",
            "candidate_tools": [
                "xhs_note_open_from_search",
                "xhs_note_open_by_xsec",
                "xhs_comment_fetch_root",
            ],
            "fallback_actions": [{"when": "have_note_id_and_xsec_token", "next_action": "xhs_note_open_by_xsec"}],
            "recovery_hint": "当前 session context 与请求不匹配；优先用当前搜索结果调用 xhs_note_open_from_search 恢复 note context。若已有可靠 note_id 和 xsec_token，也可以改用 xhs_note_open_by_xsec。若要继续评论任务，再重新拉根评论，之后用新的 root_comment_id 继续子评论。",
        }
    if error.code == "parser_changed":
        return _parser_changed_guidance(operation)
    if error.code == "invalid_request":
        limit_cap = _limit_cap_hint(operation, error.details)
        if limit_cap is not None:
            return {
                "next_action_type": "strategy",
                "next_action": "none",
                "strategy": "inspect_error",
                "limit_cap": limit_cap,
                "recovery_hint": "请求参数不合法；如果是 limit 问题，请按上限重试。",
            }
    return None


def _backend_unavailable_guidance() -> dict[str, Any]:
    return {
        "evidence_level": "none",
        "can_support_claims": False,
        "business_actions_allowed": False,
        "business_actions_disallowed_reason": "backend_unavailable",
        "tool_policy": "candidate_tools are business/data tools; allowed_next_tools are recovery tools before login readiness",
        "candidate_tools": [],
        "blocked_actions": [
            "xhs_search_posts",
            "xhs_note_open_from_search",
            "xhs_note_open_by_xsec",
            "xhs_comment_fetch_root",
            "xhs_comment_fetch_sub",
        ],
        "next_action_type": "strategy",
        "next_action": "none",
        "strategy": "retry_or_restart_backend",
        "allowed_next_tools": [
            "xhs_login_get_status",
            "xhs_session_unbind",
        ],
        "recovery_hint": "不要继续搜索、打开帖子或获取评论。只允许重试登录状态或解绑；不要切换到搜索、打开或评论。当前是浏览器/runtime 后端不可用，不是搜索/帖子证据，也不等同 login_required；先等待后重试 xhs_login_get_status，若持续失败由管理员重启服务或检查浏览器 CDP。",
    }


def _root_comment_actions(roots_with_more_sub_comments: int, has_more: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if roots_with_more_sub_comments > 0:
        actions.append(
            {
                "when": "need_deeper_thread_context",
                "next_action": "xhs_comment_fetch_sub",
                "use_root_comment_id_from_response": True,
            }
        )
    if has_more:
        actions.append(
            {
                "when": "need_broader_comment_coverage",
                "next_action": "xhs_comment_fetch_root",
                "use_cursor_from_response": True,
            }
        )
    return actions


def _parser_changed_guidance(operation: str) -> dict[str, Any]:
    variants = {
        "search": {
            "strategy": "contact_admin_or_try_different_search",
            "recovery_hint": "搜索解析结果不可信，不能支撑结论；可尝试换一个搜索条件验证是否为局部异常，持续失败则联系管理员检查解析器。",
        },
        "note": {
            "strategy": "choose_another_note",
            "recovery_hint": "当前笔记详情解析失败，不能用该笔记支撑结论；可从当前搜索结果中换一篇笔记，或联系管理员检查解析器。",
        },
        "comment": {
            "strategy": "comment_parser_unavailable",
            "recovery_hint": "评论解析结果不可信，不能支撑评论或群体反馈结论；已打开的笔记内容仍可作为笔记正文证据使用。",
        },
        "default": {
            "strategy": "contact_admin",
            "recovery_hint": "解析结果不可信，不能支撑结论；请联系管理员检查解析器问题。",
        },
    }
    if operation == "xhs_search_posts":
        variant = "search"
    elif operation in {"xhs_note_open_from_search", "xhs_note_open_by_xsec"}:
        variant = "note"
    elif operation in {"xhs_comment_fetch_root", "xhs_comment_fetch_sub"}:
        variant = "comment"
    else:
        variant = "default"
    return {
        "next_action_type": "strategy",
        "next_action": "none",
        "parser_health": "raw_untrusted",
        "can_support_claims": False,
        "candidate_tools": [],
        **variants[variant],
    }
def _limit_cap_hint(operation: str, details: dict[str, Any]) -> int | None:
    if not _mentions_limit(details):
        return None
    if operation == "xhs_comment_fetch_sub":
        return 5
    if operation == "xhs_comment_fetch_root":
        return 10
    if operation == "xhs_search_posts":
        return 20
    return None


def _mentions_limit(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key == "limit" or _mentions_limit(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_mentions_limit(item) for item in value)
    if isinstance(value, str):
        return "limit" in value.lower()
    return False
def _comments_from_result(data: dict[str, Any]) -> list[dict[str, Any]]:
    comments = _get_value(data, "comments", [])
    if isinstance(comments, list):
        return [item for item in comments if isinstance(item, dict)]
    return []


def _result_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = _get_value(data, "data")
    if isinstance(payload, dict):
        nested = _get_value(payload, "data")
        if isinstance(nested, dict) and "raw" in payload:
            return nested
        return payload
    return data
def _has_embedded_sub_comments(comment: dict[str, Any]) -> bool:
    sub_comments = _get_value(comment, "sub_comments", [])
    return isinstance(sub_comments, list) and len(sub_comments) > 0


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
