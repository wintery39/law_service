from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from schemas.common import CanonicalBaseModel


CaseType = Literal["criminal", "disciplinary", "other"]
CaseStatus = Literal["draft", "in_progress", "waiting_for_input", "completed"]
DocumentStatus = Literal["pending", "generating", "needs_input", "completed"]
QuestionStatus = Literal["open", "answered"]
PriorityLevel = Literal["critical", "high", "medium", "low"]
WorkflowStageId = Literal[
    "case_registration",
    "attachment_registration",
    "information_request",
    "document_generation",
    "review_feedback",
]
WorkflowStageStatus = Literal["pending", "active", "completed", "skipped"]
TimelineEventType = Literal[
    "case_registered",
    "attachment_registered",
    "attachment_skipped",
    "information_requested",
    "information_received",
    "document_generated",
    "document_completed",
    "review_requested",
    "review_completed",
]
LegacyTimelineEventType = Literal[
    "case_created",
    "document_generated",
    "question_requested",
    "question_answered",
    "document_completed",
    "status_updated",
]


class WorkflowStage(CanonicalBaseModel):
    id: WorkflowStageId
    title: str
    caption: str
    description: str
    detail: str
    status: WorkflowStageStatus


class TimelineEvent(CanonicalBaseModel):
    id: str
    stageId: WorkflowStageId
    type: TimelineEventType
    title: str
    description: str
    occurredAt: str
    actor: str
    relatedDocumentId: str | None = None
    relatedQuestionId: str | None = None


class SeedTimelineEvent(CanonicalBaseModel):
    id: str
    title: str
    description: str
    occurredAt: str
    actor: str
    type: TimelineEventType | LegacyTimelineEventType
    stageId: WorkflowStageId | None = None
    relatedDocumentId: str | None = None
    relatedQuestionId: str | None = None


class DocumentVersion(CanonicalBaseModel):
    version: str
    updatedAt: str
    note: str


class DocumentReviewHistory(CanonicalBaseModel):
    id: str
    title: str
    description: str
    createdAt: str
    status: Literal["open", "resolved"]


class DocumentRecord(CanonicalBaseModel):
    id: str
    caseId: str
    title: str
    type: str
    order: int
    status: DocumentStatus
    description: str
    content: str
    legalBasisIds: list[str]
    versionHistory: list[DocumentVersion]
    reviewHistory: list[DocumentReviewHistory]
    updatedAt: str


class QuestionRecord(CanonicalBaseModel):
    id: str
    caseId: str
    documentId: str
    title: str
    prompt: str
    reason: str
    status: QuestionStatus
    answer: str | None
    createdAt: str
    answeredAt: str | None
    guidance: str


class LegalBasisEntry(CanonicalBaseModel):
    id: str
    lawName: str
    article: str
    summary: str
    rationale: str
    relatedDocumentIds: list[str]


class CaseSummary(CanonicalBaseModel):
    id: str
    title: str
    caseType: CaseType
    status: CaseStatus
    occurredAt: str
    location: str
    author: str
    relatedPersons: list[str]
    summary: str
    details: str
    priority: PriorityLevel
    createdAt: str
    updatedAt: str
    progressPercent: int
    activeQuestionCount: int
    documentCount: int


class SeedCaseDetail(CaseSummary):
    attachmentProvided: bool
    attachmentSummary: str = ""
    legalReviewSummary: str
    urgencyNote: str
    timeline: list[SeedTimelineEvent]
    documents: list[object] = Field(default_factory=list)
    questions: list[object] = Field(default_factory=list)


class CaseDetail(CaseSummary):
    attachmentProvided: bool
    attachmentSummary: str
    legalReviewSummary: str
    urgencyNote: str
    workflowStages: list[WorkflowStage]
    timeline: list[TimelineEvent]
    documents: list[DocumentRecord]
    questions: list[QuestionRecord]


class CaseCreatePayload(CanonicalBaseModel):
    title: str
    caseType: CaseType
    occurredAt: str
    location: str
    author: str
    relatedPersons: list[str]
    summary: str
    details: str
    attachmentProvided: bool
    attachmentSummary: str
    priority: PriorityLevel

    @field_validator("title", "location", "author", "summary", "details", mode="after")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("field must not be blank")
        return text

    @field_validator("attachmentSummary", mode="after")
    @classmethod
    def _strip_attachment_summary(cls, value: str) -> str:
        return value.strip()

    @field_validator("relatedPersons", mode="after")
    @classmethod
    def _validate_related_persons(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("relatedPersons must contain at least one person")
        return normalized


class DocumentDetail(DocumentRecord):
    legalBasis: list[LegalBasisEntry]
    questions: list[QuestionRecord]
    previousDocumentId: str | None = None
    nextDocumentId: str | None = None


class DashboardMetrics(CanonicalBaseModel):
    totalCases: int
    inProgressCases: int
    completedCases: int
    waitingCases: int


class QuestionAnswerPayload(CanonicalBaseModel):
    answer: str

    @field_validator("answer", mode="after")
    @classmethod
    def _strip_answer(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("answer must not be blank")
        return text
