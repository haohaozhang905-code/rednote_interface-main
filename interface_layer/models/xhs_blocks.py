from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class XhsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")


class XhsUserInfo(XhsBlock):
    user_id: str
    nickname: str
    avatar: str
    ai_agent: bool | None = None
    xsec_token: str


class XhsInteractInfo(XhsBlock):
    liked_count: str
    collected_count: str
    comment_count: str
    shared_count: str


class XhsDimensions(XhsBlock):
    width: int
    height: int


class XhsCornerTagInfo(XhsBlock):
    type: str
    text: str


class XhsImageInfo(XhsBlock):
    image_scene: str
    url: str


class XhsImageAsset(XhsDimensions):
    url_default: str
    url_pre: str
    info_list: list[XhsImageInfo]


class XhsNoteImage(XhsImageAsset):
    url: str
    live_photo: bool
    file_id: str
    trace_id: str


class XhsCommentPicture(XhsImageAsset):
    pass


class XhsTag(XhsBlock):
    id: str
    name: str
    type: str


class XhsTargetComment(XhsBlock):
    comment_id: str
    user_info: XhsUserInfo


class XhsSearchItemPayload(XhsBlock):
    note_id: str
    xsec_token: str
    model_type: str
    note_card_type: str
    title: str
    user: XhsUserInfo
    interact_info: XhsInteractInfo
    cover: XhsDimensions
    image_list: list[XhsDimensions]
    corner_tag_info: list[XhsCornerTagInfo]


class XhsNoteDetail(XhsBlock):
    note_id: str
    xsec_token: str
    type: str
    title: str
    desc: str
    time: int
    last_update_time: int
    ip_location: str
    user: XhsUserInfo
    interact_info: XhsInteractInfo
    image_list: list[XhsNoteImage]
    tag_list: list[XhsTag]
    at_user_list: list[dict[str, Any]]
    un_share: bool


class XhsComment(XhsBlock):
    comment_id: str
    note_id: str
    content: str
    create_time: int
    ip_location: str
    like_count: str
    status: int
    user_info: XhsUserInfo
    at_users: list[XhsUserInfo]
    show_tags: list[str]
    pictures: list[XhsCommentPicture]


class XhsRootComment(XhsComment):
    sub_comment_count: str
    sub_comment_cursor: str
    sub_comment_has_more: bool
    sub_comments: list[XhsSubComment]


class XhsSubComment(XhsComment):
    target_comment: XhsTargetComment


class XhsSearchPage(XhsBlock):
    has_more: bool
    items: list[XhsSearchItemPayload]


class XhsSearchPostsResult(XhsBlock):
    data: XhsSearchPage
    raw: dict[str, Any]


class XhsNoteOpenResult(XhsBlock):
    data: XhsNoteDetail
    raw: dict[str, Any]


class XhsRootCommentsData(XhsBlock):
    cursor: str
    has_more: bool
    time: int
    xsec_token: str
    comments: list[XhsRootComment]


class XhsSubCommentsData(XhsBlock):
    cursor: str
    has_more: bool
    time: int
    xsec_token: str
    comments: list[XhsSubComment]


class XhsRootCommentsResult(XhsBlock):
    data: XhsRootCommentsData
    raw: dict[str, Any]


class XhsSubCommentsResult(XhsBlock):
    data: XhsSubCommentsData
    raw: dict[str, Any]
