from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from interface_layer.models.xhs_blocks import (
    XhsCommentPicture,
    XhsCornerTagInfo,
    XhsDimensions,
    XhsImageInfo,
    XhsInteractInfo,
    XhsNoteDetail,
    XhsNoteImage,
    XhsRootComment,
    XhsSearchItemPayload,
    XhsSubComment,
    XhsTag,
    XhsTargetComment,
    XhsUserInfo,
)
from interface_layer.runtime.base import RuntimeBackendError


def build_search_item(item: dict[str, Any]) -> XhsSearchItemPayload:
    raw = _as_dict(item)
    note_card = _as_dict(raw.get("note_card"))
    try:
        return XhsSearchItemPayload(
            note_id=_value(raw, "id"),
            xsec_token=_value(raw, "xsec_token"),
            model_type=_value(raw, "model_type"),
            note_card_type=_value(note_card, "type"),
            title=_value(note_card, "display_title") or "",
            user=_search_user(_as_dict(note_card.get("user"))),
            interact_info=_search_interact(_as_dict(note_card.get("interact_info"))),
            cover=_dimensions(_as_dict(note_card.get("cover"))),
            image_list=_dimensions_list(note_card.get("image_list")),
            corner_tag_info=_corner_tags(note_card.get("corner_tag_info")),
        )
    except ValidationError as exc:
        raise RuntimeBackendError("parser_changed", "search item parser missed required fields", _validation_details(exc)) from exc


def build_note_detail(note: dict[str, Any] | None) -> XhsNoteDetail:
    raw = _as_dict(note)
    try:
        return XhsNoteDetail(
            note_id=_value(raw, "noteId"),
            xsec_token=_value(raw, "xsecToken"),
            type=_value(raw, "type"),
            title=_value(raw, "title"),
            desc=_value(raw, "desc"),
            time=_value(raw, "time"),
            last_update_time=_value(raw, "lastUpdateTime"),
            ip_location=_value(raw, "ipLocation") or "",
            user=_note_user(_as_dict(raw.get("user"))),
            interact_info=_note_interact(_as_dict(raw.get("interactInfo"))),
            image_list=_note_images(_as_list(raw.get("imageList"))),
            tag_list=_tags(_as_list(raw.get("tagList"))),
            at_user_list=_list_value(raw, "atUserList"),
            un_share=_value(_as_dict(raw.get("shareInfo")), "unShare"),
        )
    except ValidationError as exc:
        raise RuntimeBackendError("parser_changed", "note detail parser missed required fields", _validation_details(exc)) from exc


def build_comment_item(comment: dict[str, Any], *, is_sub_comment: bool = False, include_sub_comments: bool = True) -> XhsRootComment | XhsSubComment:
    raw = _as_dict(comment)
    comment_id = _value(raw, "id")
    target_raw = _as_dict(raw.get("target_comment"))
    comment_model = XhsSubComment if is_sub_comment else XhsRootComment
    try:
        target_comment = _target_comment(target_raw)
        comment_fields = dict(
            comment_id=comment_id,
            note_id=_value(raw, "note_id"),
            content=_value(raw, "content"),
            create_time=_value(raw, "create_time"),
            ip_location=_value(raw, "ip_location") or "",
            like_count=_value(raw, "like_count"),
            status=_value(raw, "status"),
            user_info=_comment_user(_as_dict(raw.get("user_info"))),
            at_users=_comment_users(raw.get("at_users")),
            show_tags=_list_value(raw, "show_tags"),
            pictures=_comment_pictures(raw.get("pictures")),
        )
        if is_sub_comment:
            return comment_model(
                **comment_fields,
                target_comment=target_comment,
            )
        return comment_model(
            **comment_fields,
            sub_comment_count=_value(raw, "sub_comment_count"),
            sub_comment_cursor=_value(raw, "sub_comment_cursor"),
            sub_comment_has_more=_value(raw, "sub_comment_has_more"),
            sub_comments=_sub_comments(raw.get("sub_comments")) if include_sub_comments else None,
        )
    except ValidationError as exc:
        raise RuntimeBackendError("parser_changed", "comment parser missed required fields", _validation_details(exc)) from exc


def extract_note_detail_from_html(note_id: str, html: str) -> dict[str, Any] | None:
    match = re.search(r"window\.__INITIAL_STATE__=({.*})</script>", html)
    if match is None:
        return None
    payload = match.group(1).replace("undefined", '""')
    state = json.loads(payload)
    note_state = _as_dict(_get_any(state, "note"))
    detail_map = _as_dict(_get_any(note_state, "noteDetailMap", "note_detail_map"))
    detail = _as_dict(detail_map.get(note_id))
    note = _get_any(detail, "note")
    return _as_dict(note)


def classify_note_html(html: str) -> str:
    page = str(html or "").lower()
    if "notedetailmap" in page:
        return "normal"
    if any(signal in page for signal in ("web-login/captcha", "verifyuuid", "verifytype", "扫码验证", "请通过验证")):
        return "captcha"
    if any(signal in page for signal in ("请先登录", "登录后查看", "登录后查看更多", "web-login")):
        return "login_required"
    if any(signal in page for signal in ("页面不存在", "内容无法展示", "笔记不存在", "404")):
        return "not_found"
    if any(signal in page for signal in ("访问过于频繁", "异常请求", "error-page", "系统检测到异常")):
        return "risk"
    return "unknown"


def _search_user(user: dict[str, Any]) -> XhsUserInfo | None:
    if not user:
        return None
    return XhsUserInfo(
        user_id=_value(user, "user_id"),
        nickname=_value(user, "nickname") if "nickname" in user else _value(user, "nick_name"),
        avatar=_value(user, "avatar"),
        xsec_token=_value(user, "xsec_token"),
    )
def _note_user(user: dict[str, Any]) -> XhsUserInfo | None:
    if not user:
        return None
    return XhsUserInfo(
        user_id=_value(user, "userId"),
        nickname=_value(user, "nickname"),
        avatar=_value(user, "avatar"),
        xsec_token=_value(user, "xsecToken"),
    )
def _comment_user(user: dict[str, Any]) -> XhsUserInfo | None:
    if not user:
        return None
    return XhsUserInfo(
        user_id=_value(user, "user_id"),
        nickname=_value(user, "nickname"),
        avatar=_value(user, "image") if "image" in user else _value(user, "avatar"),
        ai_agent=_value(user, "ai_agent"),
        xsec_token=_value(user, "xsec_token"),
    )
def _comment_users(raw_users: Any) -> list[XhsUserInfo] | None:
    if not isinstance(raw_users, list):
        return None
    return [_comment_user(item) for item in raw_users if isinstance(item, dict)]
def _search_interact(interact: dict[str, Any]) -> XhsInteractInfo | None:
    return XhsInteractInfo(
        liked_count=_value(interact, "liked_count"),
        collected_count=_value(interact, "collected_count"),
        comment_count=_value(interact, "comment_count"),
        shared_count=_value(interact, "shared_count"),
    )
def _note_interact(interact: dict[str, Any]) -> XhsInteractInfo | None:
    return XhsInteractInfo(
        shared_count=_value(interact, "shareCount"),
        liked_count=_value(interact, "likedCount"),
        collected_count=_value(interact, "collectedCount"),
        comment_count=_value(interact, "commentCount"),
    )
def _dimensions(raw: dict[str, Any]) -> XhsDimensions | None:
    return XhsDimensions(width=_value(raw, "width"), height=_value(raw, "height"))
def _dimensions_list(raw_items: Any) -> list[XhsDimensions] | None:
    if not isinstance(raw_items, list):
        return None
    items = [_dimensions(_as_dict(item)) for item in raw_items if isinstance(item, dict)]
    return [item for item in items if item is not None]
def _corner_tags(raw_tags: Any) -> list[XhsCornerTagInfo] | None:
    if not isinstance(raw_tags, list):
        return None
    tags = [
        XhsCornerTagInfo(type=_value(item, "type"), text=_value(item, "text"))
        for item in raw_tags
        if isinstance(item, dict)
    ]
    return tags
def _note_images(raw_images: list[Any]) -> list[XhsNoteImage]:
    return [_note_image(item) for item in raw_images if isinstance(item, dict)]
def _note_image(image: dict[str, Any]) -> XhsNoteImage:
    return XhsNoteImage(
        url=_value(image, "url"),
        url_default=_value(image, "urlDefault"),
        url_pre=_value(image, "urlPre"),
        width=_value(image, "width"),
        height=_value(image, "height"),
        live_photo=_value(image, "livePhoto"),
        file_id=_value(image, "fileId"),
        trace_id=_value(image, "traceId"),
        info_list=_image_infos(_as_list(image.get("infoList"))),
    )


def _image_infos(raw_infos: list[Any]) -> list[XhsImageInfo]:
    infos = [
        XhsImageInfo(image_scene=_value(item, "imageScene"), url=_value(item, "url"))
        for item in raw_infos
        if isinstance(item, dict)
    ]
    return infos


def _comment_pictures(raw_pictures: Any) -> list[XhsCommentPicture] | None:
    if raw_pictures is None:
        return []
    if not isinstance(raw_pictures, list):
        return None
    return [_comment_picture(item) for item in raw_pictures if isinstance(item, dict)]


def _comment_picture(picture: dict[str, Any]) -> XhsCommentPicture:
    return XhsCommentPicture(
        url_default=_value(picture, "url_default"),
        url_pre=_value(picture, "url_pre"),
        width=_value(picture, "width"),
        height=_value(picture, "height"),
        info_list=_comment_image_infos(_as_list(picture.get("info_list"))),
    )


def _comment_image_infos(raw_infos: list[Any]) -> list[XhsImageInfo]:
    return [
        XhsImageInfo(image_scene=_value(item, "image_scene"), url=_value(item, "url"))
        for item in raw_infos
        if isinstance(item, dict)
    ]


def _tags(raw_tags: list[Any]) -> list[XhsTag]:
    return [XhsTag(id=_value(item, "id"), name=_value(item, "name"), type=_value(item, "type")) for item in raw_tags if isinstance(item, dict)]


def _target_comment(target: dict[str, Any]) -> XhsTargetComment | None:
    if not target:
        return None
    return XhsTargetComment(comment_id=_value(target, "id"), user_info=_comment_user(_as_dict(target.get("user_info"))))


def _sub_comments(raw_comments: Any) -> list[XhsSubComment] | None:
    if not isinstance(raw_comments, list):
        return None
    return [
        build_comment_item(item, is_sub_comment=True, include_sub_comments=False)
        for item in raw_comments
        if isinstance(item, dict)
    ]


def _validation_details(exc: ValidationError) -> dict[str, Any]:
    return {"errors": exc.errors(include_context=False)}


def _value(source: dict[str, Any], key: str) -> Any:
    return source[key] if key in source else None


def _list_value(source: dict[str, Any], key: str) -> list[Any] | None:
    return list(source[key]) if isinstance(source.get(key), list) else None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _get_any(value: Any, *keys: str) -> Any:
    if not isinstance(value, dict):
        return None
    for key in keys:
        if key in value:
            return value[key]
    return None
