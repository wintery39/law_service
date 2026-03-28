from __future__ import annotations

from datetime import date

from pydantic import Field, field_validator

from schemas.common import CanonicalBaseModel, parse_date_value
from schemas.corpus import Law, Reference, Unit, Version


class IngestLawRequest(CanonicalBaseModel):
    law_id: str | None = None
    mst: str | None = None
    query: str | None = None


class IngestLawResponse(CanonicalBaseModel):
    law: Law
    version: Version
    ingested_units: int
    ingested_references: int


class LawAggregateResponse(CanonicalBaseModel):
    law: Law
    versions: list[Version]


class VersionSelectionResponse(CanonicalBaseModel):
    law: Law
    selected_version: Version
    units: list[Unit]


class TextSearchResponse(CanonicalBaseModel):
    hits: list[dict[str, object]]


class GraphNeighborsResponse(CanonicalBaseModel):
    unit_id: str
    neighbors: list[dict[str, object]]


class MockDataIngestionResponse(CanonicalBaseModel):
    source_directory: str
    loaded_files: list[str]
    loaded_laws: list[str]
    ingested_units: int
    ingested_references: int


class AsOfQuery(CanonicalBaseModel):
    as_of: date = Field(alias="date")

    _parse_as_of = field_validator("as_of", mode="before")(parse_date_value)
