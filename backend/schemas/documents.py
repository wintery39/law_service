from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator

from schemas.common import CanonicalBaseModel, parse_date_value
from schemas.related_articles import CaseActor, CasePlace, CaseTime, StructuredCase


DOC_TYPE_ALIASES = {
    "사실관계 정리서": "fact_summary",
    "fact_summary": "fact_summary",
    "징계 의견서": "disciplinary_opinion",
    "disciplinary_opinion": "disciplinary_opinion",
    "항변서 초안": "defense_draft",
    "defense_draft": "defense_draft",
}
CASE_TYPE_ALIASES = {
    "criminal": "criminal",
    "형사": "criminal",
    "disciplinary": "disciplinary",
    "징계": "disciplinary",
    "other": "other",
    "기타": "other",
}
CASE_TYPE_LABELS = {
    "criminal": "형사",
    "disciplinary": "징계",
    "other": "기타",
}
AUTO_DOC_TYPE_BY_CASE_TYPE = {
    "criminal": "fact_summary",
    "disciplinary": "disciplinary_opinion",
    "other": "fact_summary",
}
DEFENSE_HINTS = ("항변", "소명", "반박", "억울", "진술이 일치하지", "오인")
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


class EvidenceType(StrEnum):
    LAW = "law"
    CASE = "case"
    REGULATION = "regulation"
    FORM = "form"


class DocumentIntent(CanonicalBaseModel):
    doc_type: Literal["fact_summary", "disciplinary_opinion", "defense_draft"]
    objective: str | None = None
    audience: str | None = None

    @field_validator("doc_type", mode="before")
    @classmethod
    def _normalize_doc_type(cls, value: str) -> str:
        key = str(value).strip()
        if key not in DOC_TYPE_ALIASES:
            raise ValueError("unsupported doc_type")
        return DOC_TYPE_ALIASES[key]


class DocumentConstraints(CanonicalBaseModel):
    tone: str = "formal"
    max_length: int | None = None
    required_sections: list[str] = Field(default_factory=list)
    prohibited_phrases: list[str] = Field(default_factory=list)
    extra_instructions: list[str] = Field(default_factory=list)
    enable_plan_retrieval_loop: bool = True


class EvidenceItem(CanonicalBaseModel):
    evidence_id: str
    evidence_type: EvidenceType
    title: str
    summary: str
    snippet: str
    citation_label: str
    keywords: list[str] = Field(default_factory=list)
    source_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = 0.0


class EvidencePack(CanonicalBaseModel):
    structured_case: StructuredCase
    route_labels: list[str] = Field(default_factory=list)
    laws: list[EvidenceItem] = Field(default_factory=list)
    cases: list[EvidenceItem] = Field(default_factory=list)
    regulations: list[EvidenceItem] = Field(default_factory=list)
    forms: list[EvidenceItem] = Field(default_factory=list)
    source_debug: dict[str, Any] = Field(default_factory=dict)

    def all_items(self) -> list[EvidenceItem]:
        return [*self.laws, *self.cases, *self.regulations, *self.forms]


class SectionPlan(CanonicalBaseModel):
    section_id: str
    title: str
    purpose: str
    keyphrases: list[str] = Field(default_factory=list)
    required_evidence_types: list[EvidenceType] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    prohibited_phrases: list[str] = Field(default_factory=list)


class DocumentPlan(CanonicalBaseModel):
    doc_type: Literal["fact_summary", "disciplinary_opinion", "defense_draft"]
    title: str
    schema_version: str = "v1"
    sections: list[SectionPlan]
    additional_retrieval_keywords: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SectionDraft(CanonicalBaseModel):
    section_id: str
    title: str
    text: str
    citations: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)


class DocumentDraft(CanonicalBaseModel):
    doc_type: Literal["fact_summary", "disciplinary_opinion", "defense_draft"]
    title: str
    sections: list[SectionDraft]
    compiled_text: str


class DraftPatch(CanonicalBaseModel):
    section_id: str
    issue_code: str
    instruction: str
    target_excerpt: str | None = None
    replacement_text: str


class DraftWarning(CanonicalBaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    section_id: str | None = None
    patch: DraftPatch | None = None


class EvidenceReport(CanonicalBaseModel):
    totals_by_type: dict[str, int]
    used_evidence_ids: list[str] = Field(default_factory=list)
    unused_evidence_ids: list[str] = Field(default_factory=list)
    section_coverage: dict[str, list[str]] = Field(default_factory=dict)
    source_mode: Literal["clarify", "result"] = "result"


class DocumentGenerationRequest(CanonicalBaseModel):
    session_id: str
    user_intent: DocumentIntent
    user_text: str
    structured_case: StructuredCase | None = None
    as_of_date: date | None = None
    jurisdiction: str = "kr"
    constraints: DocumentConstraints = Field(default_factory=DocumentConstraints)

    _parse_as_of = field_validator("as_of_date", mode="before")(parse_date_value)


class CaseDocumentGenerationRequest(CanonicalBaseModel):
    title: str
    case_type: Literal["criminal", "disciplinary", "other"] = Field(alias="caseType")
    occurred_at: datetime = Field(alias="occurredAt")
    location: str
    author: str
    related_persons: list[str] = Field(alias="relatedPersons")
    summary: str
    details: str

    @field_validator("case_type", mode="before")
    @classmethod
    def _normalize_case_type(cls, value: str) -> str:
        key = str(value).strip()
        if key not in CASE_TYPE_ALIASES:
            raise ValueError("unsupported caseType")
        return CASE_TYPE_ALIASES[key]

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _parse_occurred_at(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)

    @field_validator("related_persons", mode="before")
    @classmethod
    def _normalize_related_persons(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            items = value.split(",")
        else:
            items = value
        normalized = [str(item).strip() for item in items if str(item).strip()]
        if not normalized:
            raise ValueError("relatedPersons must contain at least one person")
        return normalized


class DocumentGenerationResponse(CanonicalBaseModel):
    draft: DocumentDraft
    checklist_missing_info: list[str] = Field(default_factory=list)
    evidence_report: EvidenceReport
    warnings: list[DraftWarning] = Field(default_factory=list)


class DocumentStreamEvent(CanonicalBaseModel):
    event: Literal["start", "evidence", "plan", "section", "evaluation", "complete", "error"]
    data: dict[str, Any] = Field(default_factory=dict)


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _build_case_narrative(payload: CaseDocumentGenerationRequest) -> str:
    return "\n".join(
        [
            f"사건 제목: {payload.title}",
            f"사건 유형: {CASE_TYPE_LABELS[payload.case_type]}",
            f"발생 일시: {payload.occurred_at.isoformat()}",
            f"발생 장소: {payload.location}",
            f"작성자: {payload.author}",
            f"관련자: {', '.join(payload.related_persons)}",
            f"사건 개요: {payload.summary}",
            f"상세 사실관계: {payload.details}",
        ]
    )


def _infer_doc_type(payload: CaseDocumentGenerationRequest, narrative: str) -> str:
    if payload.case_type == "disciplinary":
        return "disciplinary_opinion"
    if any(hint in narrative for hint in DEFENSE_HINTS):
        return "defense_draft"
    return AUTO_DOC_TYPE_BY_CASE_TYPE[payload.case_type]


def build_document_generation_request(payload: CaseDocumentGenerationRequest) -> DocumentGenerationRequest:
    session_id = f"doc-{uuid4().hex}"
    narrative = _build_case_narrative(payload)
    actor_descriptions = [f"작성자 {payload.author}", *payload.related_persons]
    keyphrases = _unique_strings(
        [
            payload.title,
            CASE_TYPE_LABELS[payload.case_type],
            payload.location,
            payload.author,
            *payload.related_persons,
            *TOKEN_RE.findall(payload.summary),
            *TOKEN_RE.findall(payload.details),
        ]
    )[:20]
    structured_case = StructuredCase(
        session_id=session_id,
        narrative=narrative,
        jurisdiction="kr",
        as_of_date=payload.occurred_at.date(),
        actors=[CaseActor(name=None, role=None, description=description) for description in actor_descriptions],
        actions=[],
        objects=[],
        time=CaseTime(mentioned_text=payload.occurred_at.isoformat(), as_of_date=payload.occurred_at.date()),
        place=CasePlace(name=payload.location, jurisdiction="kr"),
        intent=None,
        damage=None,
        relationships=[],
        roles=["작성자", "관련자"],
        legal_terms=[CASE_TYPE_LABELS[payload.case_type], payload.case_type],
        keyphrases=keyphrases,
        missing_slots=[],
    )
    return DocumentGenerationRequest(
        session_id=session_id,
        user_intent=DocumentIntent(doc_type=_infer_doc_type(payload, narrative)),
        user_text=narrative,
        structured_case=structured_case,
        as_of_date=payload.occurred_at.date(),
        jurisdiction="kr",
        constraints=DocumentConstraints(),
    )
