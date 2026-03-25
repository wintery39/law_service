from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERNAL_ID_SEGMENTS = 4


class CanonicalBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=True)


class UnitType(StrEnum):
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    ITEM = "item"
    SUBITEM = "subitem"


class ReferenceType(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    AMENDMENT = "amendment"
    DELEGATION = "delegation"
    RELATED = "related"


class ObservationContext(CanonicalBaseModel):
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    corpus_version: str = "v1"
    ingestion_run_id: str = Field(default_factory=lambda: f"ing-{uuid4().hex}")

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "corpus_version": self.corpus_version,
            "ingestion_run_id": self.ingestion_run_id,
        }


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def validate_internal_id(value: str) -> str:
    parts = value.split(":")
    if len(parts) != INTERNAL_ID_SEGMENTS or any(part == "" for part in parts):
        raise ValueError(
            "internal id must follow jurisdiction:law_id:version_key:unit_path format"
        )
    return value


class InternalIdentifiedModel(CanonicalBaseModel):
    id: str

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_internal_id(value)


def parse_date_value(value: str | int | date | None) -> date | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
    return date.fromisoformat(text)
