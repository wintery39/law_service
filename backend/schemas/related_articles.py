from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field, field_validator

from schemas.common import CanonicalBaseModel, parse_date_value


class UserProfile(CanonicalBaseModel):
    role: str | None = None
    rank: str | None = None
    organization: str | None = None
    clearance_level: str | None = None


class CaseActor(CanonicalBaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None


class CaseAction(CanonicalBaseModel):
    verb: str
    description: str | None = None
    target: str | None = None


class CaseObject(CanonicalBaseModel):
    name: str
    category: str | None = None


class CaseTime(CanonicalBaseModel):
    mentioned_text: str | None = None
    as_of_date: date | None = None

    _parse_as_of = field_validator("as_of_date", mode="before")(parse_date_value)


class CasePlace(CanonicalBaseModel):
    name: str | None = None
    jurisdiction: str | None = None


class CaseIntent(CanonicalBaseModel):
    description: str | None = None
    level: str | None = None


class CaseDamage(CanonicalBaseModel):
    physical: str | None = None
    property: str | None = None
    disciplinary: str | None = None


class RelationshipInfo(CanonicalBaseModel):
    subject: str | None = None
    object: str | None = None
    relation: str | None = None


class StructuredCase(CanonicalBaseModel):
    session_id: str
    narrative: str
    jurisdiction: str = "kr"
    as_of_date: date | None = None
    user_profile: UserProfile | None = None
    actors: list[CaseActor] = Field(default_factory=list)
    actions: list[CaseAction] = Field(default_factory=list)
    objects: list[CaseObject] = Field(default_factory=list)
    time: CaseTime | None = None
    place: CasePlace | None = None
    intent: CaseIntent | None = None
    damage: CaseDamage | None = None
    relationships: list[RelationshipInfo] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    legal_terms: list[str] = Field(default_factory=list)
    keyphrases: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)

    _parse_as_of = field_validator("as_of_date", mode="before")(parse_date_value)


class DomainRoute(CanonicalBaseModel):
    labels: list[str]
    scores: dict[str, float]
    filter_hints: dict[str, Any] = Field(default_factory=dict)


class RelatedArticleCandidate(CanonicalBaseModel):
    internal_id: str
    law_name: str
    law_internal_id: str
    official_law_id: str
    unit_path: str
    snippet: str
    effective_at: date | None = None
    amended_at: date | None = None
    source_channels: list[str] = Field(default_factory=list)
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    coverage_score: float = 0.0
    rubric_score: float = 0.0
    risk_score: float = 0.0
    final_score: float = 0.0

    _parse_effective_at = field_validator("effective_at", mode="before")(parse_date_value)
    _parse_amended_at = field_validator("amended_at", mode="before")(parse_date_value)


class RelatedArticleRequest(CanonicalBaseModel):
    session_id: str
    user_text: str
    structured_case: StructuredCase | None = None
    as_of_date: date | None = None
    jurisdiction: str | None = None
    user_profile: UserProfile | None = None

    _parse_as_of = field_validator("as_of_date", mode="before")(parse_date_value)


class ClarifyResponse(CanonicalBaseModel):
    type: Literal["clarify"] = "clarify"
    questions: list[str]
    missing_slots: list[str]
    partial_structured_case: StructuredCase


class ResultResponse(CanonicalBaseModel):
    type: Literal["result"] = "result"
    structured_case: StructuredCase
    route: DomainRoute
    candidates: list[RelatedArticleCandidate]
    final: list[RelatedArticleCandidate]
    debug: dict[str, Any] = Field(default_factory=dict)


RelatedArticleResponse = ClarifyResponse | ResultResponse
