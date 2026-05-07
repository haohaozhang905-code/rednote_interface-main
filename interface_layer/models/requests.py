from __future__ import annotations

import base64
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator


SearchSort = Literal["general", "time_descending", "popularity_descending", "comment_descending", "collect_descending"]
SearchNoteTypeFilter = Literal["不限", "视频笔记", "普通笔记"]
SearchNoteTimeFilter = Literal["不限", "一天内", "一周内", "半年内"]
SearchNoteRangeFilter = Literal["不限", "已看过", "未看过", "已关注"]
SearchPosDistanceFilter = Literal["不限", "同城", "附近"]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str | None = Field(default=None, max_length=256)


class TokenRequest(BaseModel):
    token: str


class QrcodeLoginActionRequest(BaseModel):
    token: str
    action: Literal["qrcode"]


class CookieLoginActionRequest(BaseModel):
    token: str
    action: Literal["cookie"]
    cookie: str


class PhoneStartLoginActionRequest(BaseModel):
    token: str
    action: Literal["phone_start"]
    phone: str


class PhoneSubmitLoginActionRequest(BaseModel):
    token: str
    action: Literal["phone_submit"]
    code: str


LoginActionRequest = Annotated[
    QrcodeLoginActionRequest
    | CookieLoginActionRequest
    | PhoneStartLoginActionRequest
    | PhoneSubmitLoginActionRequest,
    Field(discriminator="action"),
]


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter_note_type: SearchNoteTypeFilter = Field(default="不限", description="笔记类型")
    filter_note_time: SearchNoteTimeFilter = Field(default="不限", description="发布时间")
    filter_note_range: SearchNoteRangeFilter = Field(default="不限", description="搜索范围")
    filter_pos_distance: SearchPosDistanceFilter = Field(default="不限", description="位置距离")
    latitude: float | None = Field(default=None, description="纬度，用于同城或附近搜索")
    longitude: float | None = Field(default=None, description="经度，用于同城或附近搜索")

    @model_validator(mode="after")
    def validate_location_pair(self) -> "SearchFilters":
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_latitude != has_longitude:
            raise ValueError("latitude and longitude must be provided together")
        if self.filter_pos_distance in {"同城", "附近"} and not has_latitude:
            raise ValueError("latitude and longitude are required for 同城 or 附近 filters")
        return self

    @model_serializer(mode="wrap")
    def serialize_for_runtime(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        latitude = data.pop("latitude", None)
        longitude = data.pop("longitude", None)
        if latitude is not None and longitude is not None:
            payload = {"latitude": latitude, "longitude": longitude}
            raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            data["geo"] = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return data


class SearchPostsRequest(BaseModel):
    token: str
    keyword: str
    sort: SearchSort = "general"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=20)
    limit: int = Field(default=20, ge=1, le=20)


class OpenNoteFromSearchRequest(BaseModel):
    token: str
    note_id: str


class OpenNoteByXsecRequest(BaseModel):
    token: str
    note_id: str
    xsec_token: str


class FetchRootCommentsRequest(BaseModel):
    token: str
    note_id: str
    cursor: str | None = None
    limit: int = Field(default=10, ge=1, le=10)


class FetchSubCommentsRequest(BaseModel):
    token: str
    root_comment_id: str
    cursor: str | None = None
    limit: int = Field(default=5, ge=1, le=5)
