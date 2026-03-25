from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator

from schemas.common import CanonicalBaseModel, parse_date_value
from schemas.related_articles import StructuredCase


DOC_TYPE_ALIASES = {
    "사실관계 정리서": "fact_summary",
    "fact_summary": "fact_summary",
    "징계 의견서": "disciplinary_opinion",
    "disciplinary_opinion": "disciplinary_opinion",
    "항변서 초안": "defense_draft",
    "defense_draft": "defense_draft",
}


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


class DocumentGenerationResponse(CanonicalBaseModel):
    draft: DocumentDraft
    checklist_missing_info: list[str] = Field(default_factory=list)
    evidence_report: EvidenceReport
    warnings: list[DraftWarning] = Field(default_factory=list)


class DocumentStreamEvent(CanonicalBaseModel):
    event: Literal["start", "evidence", "plan", "section", "evaluation", "complete"]
    data: dict[str, Any] = Field(default_factory=dict)
