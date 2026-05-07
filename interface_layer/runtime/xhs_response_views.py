from __future__ import annotations

from typing import Any, Literal

from pydantic import TypeAdapter

from interface_layer.models.xhs_blocks import (
    XhsCommentPicture,
    XhsImageAsset,
    XhsInteractInfo,
    XhsNoteDetail,
    XhsNoteOpenResult,
    XhsRootComment,
    XhsRootCommentsData,
    XhsRootCommentsResult,
    XhsSearchItemPayload,
    XhsSearchPage,
    XhsSearchPostsResult,
    XhsSubComment,
    XhsSubCommentsData,
    XhsSubCommentsResult,
    XhsUserInfo,
)

XhsResponseView = Literal["compact", "full"]

_DUMPER = TypeAdapter(Any)


def dump_response(value: Any) -> Any:
    return _DUMPER.dump_python(value, mode="json")


def search_response(data: XhsSearchPage, raw: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
    if view == "compact":
        return {"data": {"has_more": data.has_more, "items": [_compact_search_item(item) for item in data.items]}}
    return dump_response(XhsSearchPostsResult(data=data, raw=raw))


def note_response(note: XhsNoteDetail, raw: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
    if view == "compact":
        return {"data": _compact_note(note)}
    return dump_response(XhsNoteOpenResult(data=note, raw=raw))


def root_comments_response(data: XhsRootCommentsData, raw: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
    if view == "compact":
        return {"data": _compact_comments_page(data, root=True)}
    return dump_response(XhsRootCommentsResult(data=data, raw=raw))


def sub_comments_response(data: XhsSubCommentsData, raw: dict[str, Any], *, view: XhsResponseView = "full") -> dict[str, Any]:
    if view == "compact":
        return {"data": _compact_comments_page(data, root=False)}
    return dump_response(XhsSubCommentsResult(data=data, raw=raw))


def _compact_search_item(item: XhsSearchItemPayload) -> dict[str, Any]:
    return _prune(
        {
            "note_id": item.note_id,
            "xsec_token": item.xsec_token,
            "type": item.note_card_type,
            "title": item.title,
            "author": _nickname(item.user),
            "interact_info": _interact(item.interact_info),
            "tags": [tag.text for tag in item.corner_tag_info or []],
        }
    )


def _compact_note(note: XhsNoteDetail) -> dict[str, Any]:
    return _prune(
        {
            "note_id": note.note_id,
            "xsec_token": note.xsec_token,
            "type": note.type,
            "title": note.title,
            "desc": note.desc,
            "time": note.time,
            "last_update_time": note.last_update_time,
            "ip_location": note.ip_location,
            "author": _nickname(note.user),
            "interact_info": _interact(note.interact_info),
            "tags": [tag.name for tag in note.tag_list or []],
            "images": [_image_url(image) for image in note.image_list or []],
        }
    )


def _compact_comments_page(data: XhsRootCommentsData | XhsSubCommentsData, *, root: bool) -> dict[str, Any]:
    return _prune(
        {
            "cursor": data.cursor,
            "has_more": data.has_more,
            "comments": [_compact_comment(comment, root=root) for comment in data.comments],
        }
    )


def _compact_comment(comment: XhsRootComment | XhsSubComment, *, root: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "comment_id": comment.comment_id,
        "content": comment.content,
        "create_time": comment.create_time,
        "ip_location": comment.ip_location,
        "like_count": comment.like_count,
        "author": _nickname(comment.user_info),
        "pictures": [_image_url(picture) for picture in comment.pictures or []],
    }
    if isinstance(comment, XhsRootComment):
        data.update(
            {
                "sub_comment_count": comment.sub_comment_count,
                "sub_comment_cursor": comment.sub_comment_cursor,
                "sub_comment_has_more": comment.sub_comment_has_more,
                "sub_comments": [_compact_comment(item, root=False) for item in comment.sub_comments or []],
            }
        )
    else:
        data["target_comment_id"] = comment.target_comment.comment_id if comment.target_comment is not None else None
        data["target_author"] = _nickname(comment.target_comment.user_info if comment.target_comment is not None else None)
    return _prune(data)


def _interact(value: XhsInteractInfo | None) -> dict[str, Any] | None:
    return dump_response(value) if value is not None else None


def _nickname(value: XhsUserInfo | None) -> str | None:
    return value.nickname if value is not None else None


def _image_url(value: XhsImageAsset | XhsCommentPicture) -> str | None:
    return value.url_default or getattr(value, "url", None) or value.url_pre


def _prune(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, [], {})}
