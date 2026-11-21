from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORMResponse(Schema):
    model_config = ConfigDict(from_attributes=True)


ResponseItem = TypeVar("ResponseItem")


class Page(ORMResponse, Generic[ResponseItem]):
    items: list[ResponseItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
