from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from schemas import (
    DocumentConstraints,
    DocumentGenerationResponse,
    DocumentIntent,
    EvidencePack,
    StructuredCase,
)
from schemas.common import CanonicalBaseModel, parse_date_value


class EvalGoldCase(CanonicalBaseModel):
    case_id: str
    user_text: str
    as_of_date: date | None = None
    gold_article_ids: list[str]
    allowed_law_groups: list[str] = Field(default_factory=list)
    jurisdiction: str = "kr"
    doc_type: Literal["fact_summary", "disciplinary_opinion", "defense_draft"] | None = None
    structured_case: StructuredCase | None = None
    constraints: DocumentConstraints = Field(default_factory=DocumentConstraints)
    expected_claim_keyphrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _parse_as_of = field_validator("as_of_date", mode="before")(parse_date_value)

    @field_validator("doc_type", mode="before")
    @classmethod
    def _normalize_doc_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return DocumentIntent(doc_type=value).doc_type

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        data = dict(payload)
        if "gold_article_ids" not in data:
            if "answer_article_ids" in data:
                data["gold_article_ids"] = data["answer_article_ids"]
            elif "gold_ids" in data:
                data["gold_article_ids"] = data["gold_ids"]
        if "allowed_law_groups" not in data:
            if "allowed_law_families" in data:
                data["allowed_law_groups"] = data["allowed_law_families"]
            elif "law_groups" in data:
                data["allowed_law_groups"] = data["law_groups"]
        return data


class RetrievalExperimentSummary(CanonicalBaseModel):
    experiment: str
    case_count: int
    metrics: dict[str, float] = Field(default_factory=dict)


class RetrievalCaseResult(CanonicalBaseModel):
    case_id: str
    experiment: str
    metrics: dict[str, float] = Field(default_factory=dict)
    retrieved_ids: list[str] = Field(default_factory=list)
    gold_ids: list[str] = Field(default_factory=list)
    failure_tags: list[str] = Field(default_factory=list)
    stage: Literal["structuring", "retrieval", "post_filter"] = "retrieval"
    debug: dict[str, Any] = Field(default_factory=dict)


class RetrievalEvaluationReport(CanonicalBaseModel):
    summaries: list[RetrievalExperimentSummary]
    case_results: list[RetrievalCaseResult]


class GenerationCaseResult(CanonicalBaseModel):
    case_id: str
    doc_type: str
    metrics: dict[str, float] = Field(default_factory=dict)
    failure_tags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)


class GenerationEvaluationReport(CanonicalBaseModel):
    summary: dict[str, float] = Field(default_factory=dict)
    case_results: list[GenerationCaseResult]


class SafetyCaseResult(CanonicalBaseModel):
    case_id: str
    doc_type: str
    metrics: dict[str, float] = Field(default_factory=dict)
    failure_tags: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)


class SafetyEvaluationReport(CanonicalBaseModel):
    summary: dict[str, float] = Field(default_factory=dict)
    case_results: list[SafetyCaseResult]


class FailureCase(CanonicalBaseModel):
    evaluation_type: Literal["retrieval", "generation", "safety"]
    case_id: str
    experiment: str
    stage: str
    reason_tags: list[str] = Field(default_factory=list)
    score: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class RetrievalThreshold(CanonicalBaseModel):
    experiment: str
    min_metrics: dict[str, float] = Field(default_factory=dict)


class GenerationThreshold(CanonicalBaseModel):
    min_citation_coverage: float | None = None
    min_citation_correctness: float | None = None
    max_unsupported_claim_count: float | None = None
    min_judge_groundedness: float | None = None


class SafetyThreshold(CanonicalBaseModel):
    max_definitive_phrase_count: float | None = None
    max_forbidden_phrase_count: float | None = None
    max_missing_info_without_disclosure: float | None = None
    max_warning_error_count: float | None = None


class EvaluationThresholds(CanonicalBaseModel):
    retrieval: list[RetrievalThreshold] = Field(default_factory=list)
    generation: GenerationThreshold = Field(default_factory=GenerationThreshold)
    safety: SafetyThreshold = Field(default_factory=SafetyThreshold)


class QualityGateResult(CanonicalBaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


class EvaluationReport(CanonicalBaseModel):
    retrieval: RetrievalEvaluationReport
    generation: GenerationEvaluationReport
    safety: SafetyEvaluationReport
    top_failures: list[FailureCase] = Field(default_factory=list)
    quality_gate: QualityGateResult = Field(default_factory=lambda: QualityGateResult(passed=True))


@dataclass
class GenerationArtifact:
    gold_case: EvalGoldCase
    response: DocumentGenerationResponse
    evidence_pack: EvidencePack
