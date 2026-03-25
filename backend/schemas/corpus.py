from __future__ import annotations

from datetime import date

from pydantic import Field, field_validator, model_validator

from schemas.common import (
    CanonicalBaseModel,
    InternalIdentifiedModel,
    ReferenceType,
    UnitType,
    parse_date_value,
)


class SourceMeta(CanonicalBaseModel):
    jurisdiction: str = "kr"
    ministry_name: str | None = None
    ministry_code: str | None = None
    law_kind_name: str | None = None
    law_kind_code: str | None = None
    status_name: str | None = None
    promulgation_number: str | None = None
    promulgated_at: date | None = None
    source_system: str = "law.go.kr"
    source_url: str | None = None
    current_history_code: str | None = None

    _parse_promulgated_at = field_validator("promulgated_at", mode="before")(parse_date_value)


class AmendmentHistory(CanonicalBaseModel):
    event_date: date | None = None
    amendment_type: str | None = None
    description: str | None = None
    promulgation_number: str | None = None

    _parse_event_date = field_validator("event_date", mode="before")(parse_date_value)


class Version(InternalIdentifiedModel):
    law_id: str
    official_law_id: str
    version_key: str
    promulgated_at: date | None = None
    effective_at: date | None = None
    repealed_at: date | None = None
    amendment_type: str | None = None
    history_code: str | None = None
    is_repealed: bool = False
    history_entries: list[AmendmentHistory] = Field(default_factory=list)
    source_meta: SourceMeta

    _parse_promulgated_at = field_validator("promulgated_at", mode="before")(parse_date_value)
    _parse_effective_at = field_validator("effective_at", mode="before")(parse_date_value)
    _parse_repealed_at = field_validator("repealed_at", mode="before")(parse_date_value)

    @model_validator(mode="after")
    def _validate_keys(self) -> "Version":
        if self.law_id == self.id:
            raise ValueError("version id must be distinct from law id")
        if self.version_key == "":
            raise ValueError("version_key must not be empty")
        return self


class Unit(InternalIdentifiedModel):
    law_id: str
    version_id: str
    version_key: str
    unit_path: str
    unit_type: UnitType
    unit_number: str
    heading: str | None = None
    body_text: str | None = None
    parent_id: str | None = None
    order_index: int = 0
    effective_at: date | None = None

    _parse_effective_at = field_validator("effective_at", mode="before")(parse_date_value)

    @model_validator(mode="after")
    def _validate_unit(self) -> "Unit":
        if not self.unit_path:
            raise ValueError("unit_path must not be empty")
        if self.version_key not in self.id:
            raise ValueError("unit id must contain version_key")
        return self


class Reference(InternalIdentifiedModel):
    source_unit_id: str
    source_law_id: str
    version_id: str
    reference_type: ReferenceType
    raw_text: str
    normalized_citation: str | None = None
    target_law_id: str | None = None
    target_unit_id: str | None = None


class Law(InternalIdentifiedModel):
    jurisdiction: str = "kr"
    official_law_id: str
    name_ko: str
    name_alias: str | None = None
    source_meta: SourceMeta
    version_ids: list[str] = Field(default_factory=list)
    latest_version_id: str | None = None

    @model_validator(mode="after")
    def _validate_law(self) -> "Law":
        if self.latest_version_id and self.latest_version_id not in self.version_ids:
            raise ValueError("latest_version_id must exist in version_ids")
        return self


class CorpusBundle(CanonicalBaseModel):
    law: Law
    versions: list[Version]
    units: list[Unit]
    references: list[Reference]

    @model_validator(mode="after")
    def _validate_relationships(self) -> "CorpusBundle":
        version_ids = {version.id for version in self.versions}
        for unit in self.units:
            if unit.version_id not in version_ids:
                raise ValueError("all units must reference an existing version")
        return self
