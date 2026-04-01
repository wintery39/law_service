from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING
from uuid import uuid4

from case_management.legal_basis import DisciplinaryLegalBasisCatalog
from documents.generator import COMMON_RANK_TOKENS
from case_management.schemas import (
    CaseCreatePayload,
    CaseDetail,
    CaseStatus,
    CaseSummary,
    DashboardMetrics,
    DocumentDetail,
    DocumentRecord,
    DocumentReviewHistory,
    DocumentStatus,
    DocumentVersion,
    LegalBasisEntry,
    LegacyTimelineEventType,
    QuestionRecord,
    SeedCaseDetail,
    SeedTimelineEvent,
    TimelineEvent,
    WorkflowStage,
    WorkflowStageId,
)
from schemas import (
    CaseDocumentGenerationRequest,
    DocumentGenerationResponse,
    DocumentIntent,
    ObservationContext,
    build_document_generation_request,
)

if TYPE_CHECKING:
    from documents.service import DocumentGenerationService


DOCUMENT_STATUS_SCORE: dict[DocumentStatus, int] = {
    "pending": 18,
    "generating": 58,
    "needs_input": 46,
    "completed": 100,
}
WORKFLOW_STAGE_META: dict[WorkflowStageId, dict[str, str]] = {
    "case_registration": {
        "title": "새 사건 등록",
        "caption": "1단계",
        "description": "프론트 입력을 받아 사건 메타데이터와 사실관계를 수집하고 내부 파이프라인 입력으로 정리합니다.",
    },
    "attachment_registration": {
        "title": "첨부 자료 등록",
        "caption": "2단계",
        "description": "검색과 문서 생성에 사용할 첨부 근거를 연결하고 evidence pack 후보를 확보합니다.",
    },
    "information_request": {
        "title": "필요한 정보 요청",
        "caption": "3단계",
        "description": "사실관계 구조화와 초안 검수 결과 누락 슬롯이 있으면 추가 질문을 생성합니다.",
    },
    "document_generation": {
        "title": "문서 생성",
        "caption": "4단계",
        "description": "관련 조항 파이프라인과 문서 생성 파이프라인을 순차 실행해 초안과 패키지를 만듭니다.",
    },
    "review_feedback": {
        "title": "문서 검토 및 유저 피드백",
        "caption": "5단계",
        "description": "Draft evaluator와 사용자 피드백을 반영해 적법성, 정합성, 최신성을 다시 점검합니다.",
    },
}
LEGACY_TIMELINE_TYPE_MAP: dict[LegacyTimelineEventType, tuple[str, WorkflowStageId]] = {
    "case_created": ("case_registered", "case_registration"),
    "document_generated": ("document_generated", "document_generation"),
    "question_requested": ("information_requested", "information_request"),
    "question_answered": ("information_received", "information_request"),
    "document_completed": ("document_completed", "document_generation"),
    "status_updated": ("review_completed", "review_feedback"),
}
TIMELINE_STAGE_MAP = {
    "case_registered": "case_registration",
    "attachment_registered": "attachment_registration",
    "attachment_skipped": "attachment_registration",
    "information_requested": "information_request",
    "information_received": "information_request",
    "document_generated": "document_generation",
    "document_completed": "document_generation",
    "review_requested": "review_feedback",
    "review_completed": "review_feedback",
}
DISCIPLINARY_DOCUMENT_CATALOG: list[dict[str, object]] = [
    {
        "title": "사실결과조사보고",
        "type": "fact_finding_report",
        "order": 1,
    },
    {
        "title": "출석통지서",
        "type": "attendance_notice",
        "order": 2,
    },
    {
        "title": "위원회 참고 자료",
        "type": "committee_reference",
        "order": 3,
    },
    {
        "title": "징계의결서/처분서",
        "type": "disciplinary_resolution",
        "order": 4,
    },
]
DOCUMENT_TITLE_BY_TYPE = {str(item["type"]): str(item["title"]) for item in DISCIPLINARY_DOCUMENT_CATALOG}
STRUCTURED_RENDER_PROMPT_PROFILES = {
    "fact_finding_report",
    "committee_reference",
    "attendance_notice",
    "disciplinary_resolution",
}


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _split_related_person_identity(raw_value: str | None) -> tuple[str, str]:
    if not raw_value:
        return "자료상 명확하지 않음", "자료상 명확하지 않음"

    parts = raw_value.split()
    if len(parts) < 2:
        return raw_value, "자료상 명확하지 않음"

    first_token = parts[0]
    last_token = parts[-1]
    if first_token in COMMON_RANK_TOKENS and last_token not in COMMON_RANK_TOKENS:
        return " ".join(parts[1:]), first_token
    if last_token in COMMON_RANK_TOKENS and first_token not in COMMON_RANK_TOKENS:
        return " ".join(parts[:-1]), last_token
    return raw_value, "자료상 명확하지 않음"


@dataclass(slots=True)
class CaseDocumentGenerationArtifacts:
    responses: dict[str, DocumentGenerationResponse]
    failures: dict[str, str]


class CaseWorkflowService:
    def __init__(
        self,
        root_dir: Path | None = None,
        document_generation_service: DocumentGenerationService | None = None,
    ) -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[2]
        self.seed_dir = self.root_dir / "backend" / "case_management" / "seed"
        self.legal_basis_catalog = DisciplinaryLegalBasisCatalog(root_dir=self.root_dir)
        self.document_generation_service = document_generation_service
        self._lock = RLock()
        self._seed_database = self._load_seed_database()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._database = deepcopy(self._seed_database)

    def get_cases(self) -> list[CaseSummary]:
        with self._lock:
            return sorted(
                deepcopy(self._database["cases"]),
                key=lambda item: _parse_iso_datetime(item.updatedAt),
                reverse=True,
            )

    def get_case_metrics(self) -> DashboardMetrics:
        with self._lock:
            cases: list[CaseSummary] = self._database["cases"]
            return DashboardMetrics(
                totalCases=len(cases),
                inProgressCases=sum(item.status == "in_progress" for item in cases),
                completedCases=sum(item.status == "completed" for item in cases),
                waitingCases=sum(item.status == "waiting_for_input" for item in cases),
            )

    def get_case_by_id(self, case_id: str) -> CaseDetail:
        with self._lock:
            return self._hydrate_case_detail(case_id)

    async def create_case(self, payload: CaseCreatePayload) -> CaseDetail:
        if payload.caseType != "disciplinary":
            raise ValueError("현재 backend 1차 범위는 disciplinary 사건만 지원합니다.")

        now = _utcnow_iso()
        case_id = f"case-{uuid4().hex[:8]}"
        generation_artifacts = await self._generate_initial_document_artifacts(payload, case_id)
        documents = self._build_document_templates(payload, case_id, now, generation_artifacts)
        progress_percent = self._get_document_status_progress(documents)
        generated_count = len(generation_artifacts.responses)

        summary = CaseSummary(
            id=case_id,
            title=payload.title,
            caseType=payload.caseType,
            status=self._derive_case_status(progress_percent, documents, []),
            occurredAt=payload.occurredAt,
            location=payload.location,
            author=payload.author,
            relatedPersons=payload.relatedPersons,
            summary=payload.summary,
            details=payload.details,
            priority=payload.priority,
            createdAt=now,
            updatedAt=now,
            progressPercent=progress_percent,
            activeQuestionCount=0,
            openReviewCount=0,
            documentCount=len(documents),
        )
        detail = SeedCaseDetail(
            **summary.model_dump(),
            attachmentProvided=payload.attachmentProvided,
            attachmentSummary=payload.attachmentSummary,
            legalReviewSummary=self._build_legal_review_summary(generation_artifacts),
            urgencyNote="현재는 초기 등록 단계이며, 추가 입력이나 후속 자료가 들어오면 상태가 갱신됩니다.",
            timeline=[
                SeedTimelineEvent(
                    id=f"{case_id}-timeline-003",
                    stageId="document_generation",
                    type="document_generated",
                    title="기본 문서 패키지 생성",
                    description=(
                        f"관련 조항 검색과 grounded generation을 거쳐 {generated_count}개의 핵심 초안과 "
                        f"{len(documents)}개의 기본 문서 패키지가 생성되었습니다."
                        if generated_count > 0
                        else f"{len(documents)}개의 기본 문서가 사건 유형에 맞춰 생성되었습니다."
                    ),
                    occurredAt=now,
                    actor="LawFlow 시스템",
                ),
                SeedTimelineEvent(
                    id=f"{case_id}-timeline-002",
                    stageId="attachment_registration",
                    type="attachment_registered" if payload.attachmentProvided else "attachment_skipped",
                    title="첨부 자료 등록" if payload.attachmentProvided else "첨부 자료 생략",
                    description=(
                        payload.attachmentSummary or "첨부 자료가 등록되어 문서 생성 기준 자료로 연결되었습니다."
                        if payload.attachmentProvided
                        else "첨부 자료 없이 다음 단계로 넘어가도록 설정했습니다."
                    ),
                    occurredAt=now,
                    actor=payload.author,
                ),
                SeedTimelineEvent(
                    id=f"{case_id}-timeline-001",
                    stageId="case_registration",
                    type="case_registered",
                    title="사건 등록",
                    description=f"{payload.title} 사건이 신규 등록되었습니다.",
                    occurredAt=now,
                    actor=payload.author,
                ),
            ],
        )

        with self._lock:
            self._database["cases"].insert(0, summary)
            self._database["caseDetails"].insert(0, detail)
            self._database["documents"].extend(documents)
            return self._hydrate_case_detail(case_id)

    def get_documents_by_case_id(self, case_id: str) -> list[DocumentRecord]:
        with self._lock:
            self._ensure_case(case_id)
            documents = [deepcopy(item) for item in self._get_documents_for_case(case_id)]
            for document in documents:
                document.legalBasisIds = self.legal_basis_catalog.resolve_ids_for_document(document)
            return documents

    def get_document_by_id(self, case_id: str, document_id: str) -> DocumentDetail:
        with self._lock:
            documents = self._get_documents_for_case(case_id)
            document = next((item for item in documents if item.id == document_id), None)
            if document is None:
                raise KeyError("문서 정보를 찾을 수 없습니다.")
            index = next(index for index, item in enumerate(documents) if item.id == document_id)
            legal_basis_ids = self.legal_basis_catalog.resolve_ids_for_document(document)
            document_payload = document.model_dump()
            document_payload["legalBasisIds"] = legal_basis_ids
            return DocumentDetail(
                **document_payload,
                legalBasis=self.legal_basis_catalog.list_entries(legal_basis_ids, document=document),
                questions=[
                    deepcopy(item)
                    for item in self._get_questions_for_case(case_id)
                    if item.documentId == document_id
                ],
                previousDocumentId=documents[index - 1].id if index > 0 else None,
                nextDocumentId=documents[index + 1].id if index < len(documents) - 1 else None,
            )

    def submit_document_review(self, case_id: str, document_id: str, title: str, description: str) -> DocumentDetail:
        with self._lock:
            self._ensure_case(case_id)
            document = next(
                (
                    item
                    for item in self._database["documents"]
                    if item.caseId == case_id and item.id == document_id
                ),
                None,
            )
            if document is None:
                raise KeyError("문서 정보를 찾을 수 없습니다.")

            normalized_title = title.strip()
            normalized_description = description.strip()
            if not normalized_title or not normalized_description:
                raise ValueError("피드백 제목과 내용을 입력해 주세요.")

            now = _utcnow_iso()
            document.reviewHistory.insert(
                0,
                DocumentReviewHistory(
                    id=f"{document.id}-review-{int(datetime.now(tz=UTC).timestamp() * 1000)}",
                    title=normalized_title,
                    description=normalized_description,
                    createdAt=now,
                    status="open",
                ),
            )
            if document.status != "needs_input":
                document.status = "generating"
            document.updatedAt = now

            self._append_timeline_event(
                case_id,
                SeedTimelineEvent(
                    id=f"{case_id}-timeline-{int(datetime.now(tz=UTC).timestamp() * 1000)}",
                    stageId="review_feedback",
                    type="review_requested",
                    title="문서 피드백 등록",
                    description=f"{document.title} 문서에 대한 사용자 피드백이 등록되었습니다.",
                    occurredAt=now,
                    actor="사용자",
                    relatedDocumentId=document_id,
                ),
            )
            self._sync_case_summary(case_id)
            return self.get_document_by_id(case_id, document_id)

    def resolve_document_review(self, case_id: str, document_id: str, review_id: str) -> DocumentDetail:
        with self._lock:
            self._ensure_case(case_id)
            document = next(
                (
                    item
                    for item in self._database["documents"]
                    if item.caseId == case_id and item.id == document_id
                ),
                None,
            )
            if document is None:
                raise KeyError("문서 정보를 찾을 수 없습니다.")

            review = next((item for item in document.reviewHistory if item.id == review_id), None)
            if review is None:
                raise KeyError("피드백 정보를 찾을 수 없습니다.")
            if review.status == "resolved":
                raise ValueError("이미 반영 완료된 피드백입니다.")

            now = _utcnow_iso()
            review.status = "resolved"
            has_remaining_open_reviews = any(item.status == "open" for item in document.reviewHistory)
            has_open_questions = any(
                item.status == "open"
                for item in self._get_questions_for_case(case_id)
                if item.documentId == document_id
            )

            document.status = (
                "needs_input"
                if has_open_questions
                else "generating" if has_remaining_open_reviews else "completed"
            )
            document.updatedAt = now
            document.versionHistory.insert(
                0,
                DocumentVersion(
                    version=f"v{len(document.versionHistory) + 1}.0",
                    updatedAt=now,
                    note=f"{review.title} 피드백을 반영해 문서를 수정했습니다.",
                ),
            )

            self._append_timeline_event(
                case_id,
                SeedTimelineEvent(
                    id=f"{case_id}-timeline-{int(datetime.now(tz=UTC).timestamp() * 1000)}",
                    stageId="review_feedback",
                    type="review_completed",
                    title="문서 피드백 반영 완료",
                    description=f"{document.title} 문서에 대한 사용자 피드백이 반영되었습니다.",
                    occurredAt=now,
                    actor="문서 생성 엔진",
                    relatedDocumentId=document_id,
                ),
            )
            self._sync_case_summary(case_id)
            return self.get_document_by_id(case_id, document_id)

    def get_questions_by_case_id(self, case_id: str) -> list[QuestionRecord]:
        with self._lock:
            self._ensure_case(case_id)
            return deepcopy(self._get_questions_for_case(case_id))

    def get_open_questions(self, case_id: str) -> list[QuestionRecord]:
        with self._lock:
            self._ensure_case(case_id)
            return [deepcopy(item) for item in self._get_questions_for_case(case_id) if item.status == "open"]

    def submit_question_answer(self, question_id: str, answer: str) -> CaseDetail:
        with self._lock:
            question = next((item for item in self._database["questions"] if item.id == question_id), None)
            if question is None:
                raise KeyError("질문 정보를 찾을 수 없습니다.")
            if question.status == "answered":
                raise ValueError("이미 답변이 제출된 질문입니다.")

            now = _utcnow_iso()
            question.status = "answered"
            question.answer = answer
            question.answeredAt = now

            document = next((item for item in self._database["documents"] if item.id == question.documentId), None)
            if document is not None:
                document.status = "generating" if document.status == "needs_input" else document.status
                document.updatedAt = now
                document.versionHistory.insert(
                    0,
                    DocumentVersion(
                        version=f"v{len(document.versionHistory) + 1}.0",
                        updatedAt=now,
                        note="추가 질문 답변이 반영되어 초안이 갱신되었습니다.",
                    ),
                )
                document.reviewHistory.insert(
                    0,
                    DocumentReviewHistory(
                        id=f"{document.id}-review-{int(datetime.now(tz=UTC).timestamp() * 1000)}",
                        title="질문 답변 반영",
                        description="사용자 입력을 반영해 문서 상태를 갱신했습니다.",
                        createdAt=now,
                        status="resolved",
                    ),
                )

            self._append_timeline_event(
                question.caseId,
                SeedTimelineEvent(
                    id=f"{question.caseId}-timeline-{int(datetime.now(tz=UTC).timestamp() * 1000)}",
                    stageId="information_request",
                    type="information_received",
                    title="추가 질문 답변 반영",
                    description=f"{question.title}에 대한 답변이 제출되어 문서 초안이 갱신되었습니다.",
                    occurredAt=now,
                    actor="사용자",
                    relatedQuestionId=question.id,
                    relatedDocumentId=question.documentId,
                ),
            )
            self._sync_case_summary(question.caseId)
            return self._hydrate_case_detail(question.caseId)

    def get_legal_basis_by_ids(self, ids: list[str]) -> list[LegalBasisEntry]:
        with self._lock:
            return self.legal_basis_catalog.list_entries(ids)

    def _load_seed_database(self) -> dict[str, list[object]]:
        if not self.seed_dir.exists():
            raise RuntimeError(f"case management seed directory not found: {self.seed_dir}")

        return {
            "cases": self._load_json("cases.json", CaseSummary),
            "caseDetails": self._load_json("case-detail.json", SeedCaseDetail),
            "documents": self._load_json("documents.json", DocumentRecord),
            "questions": self._load_json("questions.json", QuestionRecord),
        }

    def _load_json(self, filename: str, model_cls):
        path = self.seed_dir / filename
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        return [model_cls.model_validate(item) for item in raw_items]

    def _ensure_case(self, case_id: str) -> tuple[CaseSummary, SeedCaseDetail]:
        summary = next((item for item in self._database["cases"] if item.id == case_id), None)
        detail = next((item for item in self._database["caseDetails"] if item.id == case_id), None)
        if summary is None or detail is None:
            raise KeyError("사건 정보를 찾을 수 없습니다.")
        return summary, detail

    def _get_documents_for_case(self, case_id: str) -> list[DocumentRecord]:
        return sorted(
            [item for item in self._database["documents"] if item.caseId == case_id],
            key=lambda item: item.order,
        )

    def _get_questions_for_case(self, case_id: str) -> list[QuestionRecord]:
        return sorted(
            [item for item in self._database["questions"] if item.caseId == case_id],
            key=lambda item: _parse_iso_datetime(item.createdAt),
            reverse=True,
        )

    def _get_document_status_progress(self, documents: list[DocumentRecord]) -> int:
        if not documents:
            return 0
        total = sum(DOCUMENT_STATUS_SCORE[item.status] for item in documents)
        return round(total / len(documents))

    def _get_attachment_summary(self, detail: SeedCaseDetail) -> str:
        if not detail.attachmentProvided:
            return ""
        return detail.attachmentSummary.strip() or "첨부 자료가 등록되어 문서 생성과 검토 단계의 기준 자료로 연결되었습니다."

    def _normalize_timeline_event(self, event: SeedTimelineEvent) -> TimelineEvent:
        if event.stageId:
            return TimelineEvent(**event.model_dump())

        if event.type in LEGACY_TIMELINE_TYPE_MAP:
            normalized_type, stage_id = LEGACY_TIMELINE_TYPE_MAP[event.type]
        else:
            normalized_type = event.type
            stage_id = TIMELINE_STAGE_MAP[normalized_type]

        payload = event.model_dump()
        payload["type"] = normalized_type
        payload["stageId"] = stage_id
        return TimelineEvent(**payload)

    def _build_attachment_timeline_event(self, detail: SeedCaseDetail) -> TimelineEvent:
        return TimelineEvent(
            id=f"{detail.id}-timeline-attachment",
            stageId="attachment_registration",
            type="attachment_registered" if detail.attachmentProvided else "attachment_skipped",
            title="첨부 자료 등록" if detail.attachmentProvided else "첨부 자료 생략",
            description=(
                self._get_attachment_summary(detail)
                if detail.attachmentProvided
                else "첨부 자료 없이 다음 단계로 진행하도록 설정했습니다."
            ),
            occurredAt=detail.createdAt,
            actor=detail.author,
        )

    def _normalize_timeline(self, detail: SeedCaseDetail, documents: list[DocumentRecord]) -> list[TimelineEvent]:
        events = [self._normalize_timeline_event(item) for item in detail.timeline]

        if not any(item.stageId == "attachment_registration" for item in events):
            events.append(self._build_attachment_timeline_event(detail))

        if (
            documents
            and all(document.status == "completed" for document in documents)
            and not any(item.stageId == "review_feedback" for item in events)
        ):
            events.append(
                TimelineEvent(
                    id=f"{detail.id}-timeline-review",
                    stageId="review_feedback",
                    type="review_completed",
                    title="문서 검토 완료",
                    description="최종 문서 검토가 끝나 사건 패키지가 완료 상태로 정리되었습니다.",
                    occurredAt=detail.updatedAt,
                    actor="LawFlow 시스템",
                )
            )

        return sorted(events, key=lambda item: _parse_iso_datetime(item.occurredAt), reverse=True)

    def _build_workflow_stages(self, case_detail: CaseDetail) -> list[WorkflowStage]:
        documents_completed = bool(case_detail.documents) and all(
            document.status == "completed" for document in case_detail.documents
        )
        drafts_prepared = bool(case_detail.documents) and all(
            document.status != "pending" for document in case_detail.documents
        )
        open_questions = [item for item in case_detail.questions if item.status == "open"]
        answered_questions = [item for item in case_detail.questions if item.status == "answered"]
        documents_needing_input = sum(document.status == "needs_input" for document in case_detail.documents)
        generating_documents = sum(document.status == "generating" for document in case_detail.documents)
        pending_documents = sum(document.status == "pending" for document in case_detail.documents)
        review_items = [review for document in case_detail.documents for review in document.reviewHistory]
        open_reviews = sum(item.status == "open" for item in review_items)
        resolved_reviews = sum(item.status == "resolved" for item in review_items)
        has_review_history = bool(review_items)

        return [
            WorkflowStage(
                id="case_registration",
                detail=(
                    f"{case_detail.author} 작성자가 사건을 등록했고, 입력된 사건 정보는 "
                    "내부 관련 조항 검색의 사실관계 구조화 단계로 바로 전달됩니다."
                ),
                status="completed",
                **WORKFLOW_STAGE_META["case_registration"],
            ),
            WorkflowStage(
                id="attachment_registration",
                detail=(
                    case_detail.attachmentSummary
                    or "첨부 자료가 등록되어 Graph RAG 보조 검색과 문서 evidence pack 구성에 함께 사용됩니다."
                    if case_detail.attachmentProvided
                    else "첨부 자료 없이 진행하기로 선택해 이 단계를 건너뛰었고, 부족한 정보는 후속 질문 단계에서 보완합니다."
                ),
                status="completed" if case_detail.attachmentProvided else "skipped",
                **WORKFLOW_STAGE_META["attachment_registration"],
            ),
            WorkflowStage(
                id="information_request",
                detail=(
                    f"{len(open_questions)}건의 추가 정보 요청이 열려 있으며, "
                    f"{f'{documents_needing_input}개 문서가 답변을 기다리고 있습니다.' if documents_needing_input > 0 else '관련 문서가 답변을 기다리고 있습니다.'} "
                    "행위자, 행위, 대상, 시점, 장소 같은 누락 슬롯을 보완하는 단계입니다."
                    if open_questions
                    else (
                        f"{len(answered_questions)}건의 요청 정보가 반영되어 문서 작성이 다시 진행 중입니다. "
                        "보완된 입력은 retrieval evaluator와 draft evaluator에 함께 반영됩니다."
                        if answered_questions
                        else "현재까지 추가 정보 요청 없이 문서 생성이 진행되고 있습니다."
                    )
                ),
                status=(
                    "active"
                    if open_questions or documents_needing_input > 0
                    else "completed" if answered_questions else "skipped"
                ),
                **WORKFLOW_STAGE_META["information_request"],
            ),
            WorkflowStage(
                id="document_generation",
                detail=(
                    f"{len(case_detail.documents)}개 문서 초안이 준비되었고, 현재 {open_reviews}건의 피드백 반영이 진행 중입니다. "
                    "내부적으로는 사실관계 구조화 → 법체계 라우팅 → Graph RAG + 보조 검색 → Retrieval Evaluator 이후 "
                    "근거 수집 → 문단 계획 → 섹션별 생성이 순차 실행됩니다."
                    if open_reviews > 0 and drafts_prepared
                    else (
                        f"{len(case_detail.documents)}개의 문서가 모두 생성 완료되었습니다. "
                        "관련 조항 파이프라인과 문서 생성 파이프라인이 모두 완료된 상태입니다."
                        if documents_completed
                        else (
                            f"{len(case_detail.documents)}개 문서 중 {generating_documents}개 작성 중, "
                            f"{pending_documents}개 대기, {documents_needing_input}개 추가 정보 필요 상태입니다. "
                            "관련 조항 검색 결과를 바탕으로 문서 계획과 섹션 생성이 진행 중입니다."
                        )
                    )
                ),
                status=(
                    "completed"
                    if open_reviews > 0 and drafts_prepared
                    else "completed"
                    if documents_completed
                    else "pending"
                    if not case_detail.documents or open_questions or documents_needing_input > 0
                    else "active"
                ),
                **WORKFLOW_STAGE_META["document_generation"],
            ),
            WorkflowStage(
                id="review_feedback",
                detail=(
                    f"{open_reviews}건의 검토 요청이 열려 있으며, 사용자 피드백 반영이 필요합니다. "
                    "이 단계에서는 draft evaluator 경고와 사용자 수정 요청을 함께 처리합니다."
                    if open_reviews > 0
                    else "문서 생성이 완료되면 검토와 피드백 반영 단계로 넘어갑니다."
                    if not documents_completed and not has_review_history
                    else (
                        f"{resolved_reviews}건의 검토 이력이 정리되었고 현재 열린 피드백은 없습니다. "
                        "형식 완전성, 근거 정합성, 내부 일관성 검사가 반영된 상태입니다."
                        if has_review_history
                        else "검토 요청 없이 문서 패키지가 마무리되었습니다."
                    )
                ),
                status=(
                    "active"
                    if open_reviews > 0
                    else "pending" if not documents_completed and not has_review_history else "completed"
                ),
                **WORKFLOW_STAGE_META["review_feedback"],
            ),
        ]

    def _derive_case_status(
        self,
        progress_percent: int,
        documents: list[DocumentRecord],
        questions: list[QuestionRecord],
    ) -> CaseStatus:
        has_documents = bool(documents)
        all_completed = has_documents and all(document.status == "completed" for document in documents)
        open_questions = sum(question.status == "open" for question in questions)
        open_reviews = sum(
            review.status == "open"
            for document in documents
            for review in document.reviewHistory
        )

        if all_completed and open_reviews == 0:
            return "completed"
        if open_questions > 0:
            return "waiting_for_input"
        if progress_percent <= 24:
            return "draft"
        return "in_progress"

    def _sync_case_summary(self, case_id: str) -> None:
        summary, detail = self._ensure_case(case_id)
        documents = self._get_documents_for_case(case_id)
        questions = self._get_questions_for_case(case_id)
        progress_percent = self._get_document_status_progress(documents)
        open_question_count = sum(question.status == "open" for question in questions)
        open_review_count = sum(
            review.status == "open"
            for document in documents
            for review in document.reviewHistory
        )
        now = _utcnow_iso()

        next_status = self._derive_case_status(progress_percent, documents, questions)
        summary.progressPercent = progress_percent
        summary.activeQuestionCount = open_question_count
        summary.openReviewCount = open_review_count
        summary.documentCount = len(documents)
        summary.status = next_status
        summary.updatedAt = now

        detail.status = next_status
        detail.progressPercent = progress_percent
        detail.activeQuestionCount = open_question_count
        detail.openReviewCount = open_review_count
        detail.documentCount = len(documents)
        detail.updatedAt = now

    def _hydrate_case_detail(self, case_id: str) -> CaseDetail:
        summary, detail = self._ensure_case(case_id)
        documents = [deepcopy(item) for item in self._get_documents_for_case(case_id)]
        for document in documents:
            document.legalBasisIds = self.legal_basis_catalog.resolve_ids_for_document(document)
        questions = [deepcopy(item) for item in self._get_questions_for_case(case_id)]

        hydrated = CaseDetail(
            **summary.model_dump(),
            attachmentProvided=detail.attachmentProvided,
            attachmentSummary=self._get_attachment_summary(detail),
            legalReviewSummary=detail.legalReviewSummary,
            urgencyNote=detail.urgencyNote,
            workflowStages=[],
            timeline=self._normalize_timeline(detail, documents),
            documents=documents,
            questions=questions,
        )
        hydrated.workflowStages = self._build_workflow_stages(hydrated)
        return hydrated

    def _append_timeline_event(self, case_id: str, event: SeedTimelineEvent) -> None:
        _, detail = self._ensure_case(case_id)
        detail.timeline.insert(0, event)

    async def _generate_initial_document_artifacts(
        self,
        payload: CaseCreatePayload,
        case_id: str,
    ) -> CaseDocumentGenerationArtifacts:
        if self.document_generation_service is None:
            return CaseDocumentGenerationArtifacts(responses={}, failures={})

        specs = [
            (
                "fact_finding_report",
                "fact_summary",
                "fact_finding_report",
                [
                    "사실결과조사보고 형식으로 작성하라.",
                    "확인된 사실, 검토 쟁점, 추가 확인 필요사항이 드러나도록 정리하라.",
                ],
            ),
            (
                "attendance_notice",
                "fact_summary",
                "attendance_notice",
                [
                    "출석통지서 형식으로 작성하라.",
                    "수신자 인적사항, 출석 요구 사유, 출석 일시·장소, 절차적 권리 안내가 빠지지 않도록 정리하라.",
                ],
            ),
            (
                "committee_reference",
                "disciplinary_opinion",
                "committee_reference",
                [
                    "위원회 참고 자료 형식으로 작성하라.",
                    "적용 규정, 징계 판단 포인트, 추가 조사 필요성이 드러나도록 정리하라.",
                ],
            ),
            (
                "disciplinary_resolution",
                "disciplinary_opinion",
                "disciplinary_resolution",
                [
                    "징계의결서 형식으로 작성하라.",
                    "의결주문과 이유 부분이 논리 구조를 유지하도록 정리하라.",
                ],
            ),
        ]
        results = await asyncio.gather(
            *[
                self._generate_pipeline_document(
                    payload,
                    case_id,
                    document_type,
                    pipeline_doc_type,
                    prompt_profile,
                    instructions,
                )
                for document_type, pipeline_doc_type, prompt_profile, instructions in specs
            ],
            return_exceptions=True,
        )

        responses: dict[str, DocumentGenerationResponse] = {}
        failures: dict[str, str] = {}
        for (document_type, _, _, _), result in zip(specs, results):
            if isinstance(result, Exception):
                failures[document_type] = str(result).strip() or type(result).__name__
                continue
            responses[document_type] = result
        return CaseDocumentGenerationArtifacts(responses=responses, failures=failures)

    async def _generate_pipeline_document(
        self,
        payload: CaseCreatePayload,
        case_id: str,
        document_type: str,
        pipeline_doc_type: str,
        prompt_profile: str | None,
        extra_instructions: list[str],
    ) -> DocumentGenerationResponse:
        if self.document_generation_service is None:
            raise RuntimeError("document generation service is not configured")

        request = self._build_pipeline_request(payload, pipeline_doc_type, prompt_profile, extra_instructions)
        context = ObservationContext(
            request_id=f"{case_id}-{document_type}",
            corpus_version="v1",
            ingestion_run_id=f"case-create-{case_id}",
        )
        return await self.document_generation_service.generate(request, context)

    def _build_pipeline_request(
        self,
        payload: CaseCreatePayload,
        pipeline_doc_type: str,
        prompt_profile: str | None,
        extra_instructions: list[str],
    ):
        generation_payload = CaseDocumentGenerationRequest(
            title=payload.title,
            caseType=payload.caseType,
            occurredAt=payload.occurredAt,
            location=payload.location,
            author=payload.author,
            relatedPersons=payload.relatedPersons,
            summary=payload.summary,
            details=payload.details,
        )
        request = build_document_generation_request(generation_payload)
        attachment_instruction = (
            f"첨부자료 요약: {payload.attachmentSummary}"
            if payload.attachmentProvided and payload.attachmentSummary
            else None
        )
        supplemental_lines: list[str] = []
        if attachment_instruction:
            supplemental_lines.append(attachment_instruction)
        if prompt_profile == "disciplinary_resolution":
            recognized_fact = payload.details.strip() or payload.summary.strip() or "자료상 명확하지 않음"
            supplemental_lines.extend(
                [
                    "최종 의결결론: 자료상 명확하지 않음",
                    f"인정 사실: {recognized_fact}",
                    "의결일자: 자료상 명확하지 않음",
                    "징계위원회명: 자료상 명확하지 않음",
                    "위원장 및 위원 표시: 자료상 명확하지 않음",
                ]
            )
        supplemental_text = "\n".join(supplemental_lines)
        narrative_suffix = f"\n{supplemental_text}" if supplemental_text else ""
        structured_case = request.structured_case
        if structured_case is not None and narrative_suffix:
            structured_case = structured_case.model_copy(
                update={"narrative": f"{structured_case.narrative}{narrative_suffix}"}
            )

        constraints = request.constraints.model_copy(
            update={
                "extra_instructions": [
                    *request.constraints.extra_instructions,
                    *extra_instructions,
                    *([attachment_instruction] if attachment_instruction else []),
                ],
                "prompt_profile": prompt_profile,
            }
        )
        return request.model_copy(
            update={
                "user_intent": DocumentIntent(doc_type=pipeline_doc_type),
                "user_text": f"{request.user_text}{narrative_suffix}" if narrative_suffix else request.user_text,
                "structured_case": structured_case,
                "constraints": constraints,
            }
        )

    def _build_legal_review_summary(self, artifacts: CaseDocumentGenerationArtifacts) -> str:
        if not artifacts.responses:
            return (
                "사건 등록 직후 생성된 기본 검토 메모입니다. 문서 초안이 보완되면 적용 조항과 위험 포인트가 자동으로 정리됩니다."
            )

        parts: list[str] = []
        for document_type, label in (
            ("fact_finding_report", "사실결과조사보고"),
            ("committee_reference", "위원회 참고 자료"),
        ):
            response = artifacts.responses.get(document_type)
            if response is None:
                continue
            totals = response.evidence_report.totals_by_type
            evidence_total = sum(totals.values())
            parts.append(
                f"{label} 초안은 근거 {evidence_total}건(법령 {totals.get('law', 0)}, 규정 {totals.get('regulation', 0)}, "
                f"판단례 {totals.get('case', 0)}, 서식 {totals.get('form', 0)})을 바탕으로 생성되었습니다."
            )

        warning_count = sum(len(response.warnings) for response in artifacts.responses.values())
        if warning_count > 0:
            parts.append(f"draft evaluator 경고 {warning_count}건이 함께 정리되었습니다.")

        missing_items: list[str] = []
        for response in artifacts.responses.values():
            for item in response.checklist_missing_info:
                if item not in missing_items:
                    missing_items.append(item)
        if missing_items:
            parts.append(f"추가 확인 필요사항: {', '.join(missing_items[:3])}.")

        if artifacts.failures:
            failed_titles = [DOCUMENT_TITLE_BY_TYPE.get(document_type, document_type) for document_type in artifacts.failures]
            parts.append(f"일부 문서는 생성 실패로 입력 보존용 템플릿을 사용했습니다: {', '.join(failed_titles)}.")

        return " ".join(parts)

    def _render_generated_document_content(
        self,
        payload: CaseCreatePayload,
        response: DocumentGenerationResponse,
        *,
        prompt_profile: str | None = None,
    ) -> str:
        blocks: list[str] = []
        if prompt_profile in STRUCTURED_RENDER_PROMPT_PROFILES:
            additional_needed_info: list[str] = []
            for item in response.checklist_missing_info:
                if item not in additional_needed_info:
                    additional_needed_info.append(item)
            for section in response.draft.sections:
                for item in section.open_issues:
                    if item not in additional_needed_info:
                        additional_needed_info.append(item)
            if prompt_profile == "attendance_notice":
                blocks.append("제목: 출석통지서")
            if prompt_profile == "committee_reference":
                blocks.append(f"제목: {response.draft.title}")
            if prompt_profile == "disciplinary_resolution":
                blocks.append("제목: 징계의결서")
            if additional_needed_info:
                if prompt_profile == "fact_finding_report":
                    checklist = "\n".join(f"- {item}" for item in additional_needed_info[:5])
                    blocks.append(f"추가 필요 정보\n{checklist}")
                if prompt_profile == "attendance_notice":
                    checklist = "\n".join(f"- {item}" for item in additional_needed_info[:5])
                    blocks.append(f"누락정보\n{checklist}")
                if prompt_profile == "disciplinary_resolution":
                    checklist = "\n".join(f"- {item}" for item in additional_needed_info[:5])
                    blocks.append(f"누락정보\n{checklist}")

        for index, section in enumerate(response.draft.sections, start=1):
            section_lines = [section.text]
            if prompt_profile not in STRUCTURED_RENDER_PROMPT_PROFILES and section.open_issues:
                section_lines.append(f"추가 이슈: {', '.join(section.open_issues)}")
            if prompt_profile == "attendance_notice" and section.section_id == "appendix":
                blocks.append(f"[별첨]\n" + "\n".join(section_lines))
                continue
            blocks.append(f"{index}. {section.title}\n" + "\n".join(section_lines))

        if prompt_profile in STRUCTURED_RENDER_PROMPT_PROFILES:
            return "\n\n".join(blocks)

        next_index = len(blocks) + 1
        if response.checklist_missing_info:
            checklist = "\n".join(f"- {item}" for item in response.checklist_missing_info[:5])
            blocks.append(f"{next_index}. 추가 확인 필요\n{checklist}")
            next_index += 1
        if response.warnings:
            warnings = "\n".join(f"- {warning.message}" for warning in response.warnings[:5])
            blocks.append(f"{next_index}. 검토 메모\n{warnings}")
            next_index += 1

        attachment_text = payload.attachmentSummary if payload.attachmentProvided else "없음"
        blocks.append(
            f"{next_index}. 사건 메타데이터\n"
            f"사건 제목: {payload.title}\n"
            f"발생 일시: {payload.occurredAt}\n"
            f"발생 장소: {payload.location}\n"
            f"작성자: {payload.author}\n"
            f"관련자: {', '.join(payload.relatedPersons)}\n"
            f"첨부자료 요약: {attachment_text}"
        )
        return "\n\n".join(blocks)

    def _build_document_templates(
        self,
        payload: CaseCreatePayload,
        case_id: str,
        created_at: str,
        generation_artifacts: CaseDocumentGenerationArtifacts | None = None,
    ) -> list[DocumentRecord]:
        generation_artifacts = generation_artifacts or CaseDocumentGenerationArtifacts(responses={}, failures={})
        related_people = ", ".join(payload.relatedPersons)
        attachment_text = payload.attachmentSummary if payload.attachmentProvided else "없음"
        primary_person = payload.relatedPersons[0] if payload.relatedPersons else None
        primary_name, primary_rank = _split_related_person_identity(primary_person)

        templates: list[dict[str, object]] = []
        for item in DISCIPLINARY_DOCUMENT_CATALOG:
            if item["type"] == "fact_finding_report":
                generated = generation_artifacts.responses.get("fact_finding_report")
                templates.append(
                    {
                        **item,
                        "status": "completed",
                        "legalBasisIds": ["lb-003", "lb-005"],
                        "description": (
                            "관련 조항 검색 결과를 반영해 확인된 사실관계와 1차 조사 의견을 정리한 문서입니다."
                            if generated is not None
                            else "확인된 사실관계와 1차 조사 의견을 정리한 문서입니다."
                        ),
                        "content": self._render_generated_document_content(
                            payload,
                            generated,
                            prompt_profile="fact_finding_report",
                        )
                        if generated is not None
                        else (
                            f"1. 사용자 입력 사건 개요\n{payload.summary}\n\n"
                            f"2. 사용자 입력 상세 사실관계\n{payload.details}\n\n"
                            "3. 사용자 입력 메타데이터\n"
                            f"사건 제목: {payload.title}\n"
                            f"발생 일시: {payload.occurredAt}\n"
                            f"발생 장소: {payload.location}\n"
                            f"작성자: {payload.author}\n"
                            f"관련자: {related_people}\n"
                            f"첨부자료 요약: {attachment_text}"
                        ),
                        "versionNote": (
                            "관련 조항 검색과 grounded generation을 거쳐 조사보고 초안을 생성했습니다."
                            if generated is not None
                            else "사건 등록 직후 필수 문서 초안이 완성되었습니다."
                        ),
                    }
                )
            elif item["type"] == "attendance_notice":
                generated = generation_artifacts.responses.get("attendance_notice")
                templates.append(
                    {
                        **item,
                        "status": "completed",
                        "legalBasisIds": ["lb-004"],
                        "description": (
                            "징계위원회 출석 요구 사유와 절차적 권리 안내를 반영한 통지서입니다."
                            if generated is not None
                            else "위원회 출석 일정과 소명 기회를 안내하는 통지서입니다."
                        ),
                        "content": self._render_generated_document_content(
                            payload,
                            generated,
                            prompt_profile="attendance_notice",
                        )
                        if generated is not None
                        else (
                            "제목: 출석통지서\n\n"
                            "누락정보\n"
                            "- 출석 일시\n"
                            "- 출석 장소\n"
                            "- 징계위원회명\n"
                            "- 통지일\n"
                            "- 대상자 주소\n\n"
                            "1. 인적사항\n"
                            f"- 성명: {primary_name}\n"
                            "- 소속: 자료상 명확하지 않음\n"
                            f"- 직위(직급): {primary_rank}\n"
                            "- 주소: 자료상 명확하지 않음\n\n"
                            "2. 출석 이유\n"
                            f"{payload.summary}\n\n"
                            "3. 출석 일시\n"
                            "- 자료상 명확하지 않음\n\n"
                            "4. 출석 장소\n"
                            "- 자료상 명확하지 않음\n\n"
                            "5. 유의사항\n"
                            "- 출석하여 진술하기를 원하지 않는 경우 진술권 포기서를 제출할 수 있음\n"
                            "- 서면진술을 원할 경우 지정 기한까지 진술서를 제출할 수 있음\n"
                            "- 정당한 사유 없이 불출석하고 서면진술도 없으면 진술 의사가 없는 것으로 보고 처리될 수 있음\n"
                            "- 필요 시 소명자료 또는 증빙자료를 제출할 수 있음\n\n"
                            "6. 통지 문구\n"
                            "- 관련 규정에 따라 위와 같이 귀하의 출석을 통지합니다.\n\n"
                            "7. 발신\n"
                            "- 통지일: 자료상 명확하지 않음\n"
                            "- 징계위원회명: 자료상 명확하지 않음\n"
                            "- 위원회 청인 또는 직인 표시\n\n"
                            "8. 수신\n"
                            "- 귀하\n\n"
                            "[별첨]\n"
                            "- 필요 시 진술권 포기서 양식"
                        ),
                        "versionNote": (
                            "관련 조항 검색과 grounded generation을 거쳐 출석통지서 초안을 생성했습니다."
                            if generated is not None
                            else "사건 등록 직후 필수 문서 초안이 완성되었습니다."
                        ),
                    }
                )
            elif item["type"] == "committee_reference":
                generated = generation_artifacts.responses.get("committee_reference")
                templates.append(
                    {
                        **item,
                        "status": "generating",
                        "legalBasisIds": ["lb-003", "lb-005"],
                        "description": (
                            "위원회가 사실관계와 적용 규정을 빠르게 파악할 수 있도록 관련 근거를 반영한 참고 자료입니다."
                            if generated is not None
                            else "위원회가 사실관계와 쟁점을 빠르게 파악할 수 있도록 정리한 참고 자료입니다."
                        ),
                        "content": self._render_generated_document_content(
                            payload,
                            generated,
                            prompt_profile="committee_reference",
                        )
                        if generated is not None
                        else (
                            "제목: 징계위원회 참고자료\n\n"
                            "1. 사건 개요\n"
                            f"- 사건명: {payload.title}\n"
                            "- 심의 일시: 자료상 명확하지 않음\n"
                            f"- 심의 대상자: {payload.relatedPersons[0] if payload.relatedPersons else '자료상 명확하지 않음'}\n"
                            f"- 사건 요약: {payload.summary}\n\n"
                            "2. 심의대상자 인적사항\n"
                            "- 소속: 자료상 명확하지 않음\n"
                            f"- 직위/직급: {primary_rank}\n"
                            f"- 성명: {primary_name}\n\n"
                            "3. 징계혐의 사실 요약\n"
                            f"- 사실관계 1: {payload.details}\n"
                            "- 사실관계 2: 관련자 진술과 기록자료는 추가 확인이 필요함\n"
                            "- 사실관계 3: 세부 경위와 행위 주체는 자료상 명확하지 않음\n\n"
                            "4. 주요 쟁점\n"
                            "- 쟁점 1: 승인 절차 준수 여부 및 관련 규정 위반 성립 여부\n"
                            "- 쟁점 2: 관련자 진술과 기록자료의 일치 여부\n"
                            "- 쟁점 3: 행위 주체와 구체적 경위 특정 여부\n\n"
                            "5. 증거자료 요약\n"
                            f"- 증거 1: {attachment_text} - 사건 관련 자료로 검토 필요\n"
                            "- 증거 2: 자료상 명확하지 않음\n"
                            "- 증거 3: 자료상 명확하지 않음\n\n"
                            "6. 당사자 진술 및 소명 요지\n"
                            "- 대상자 진술 요지: 자료상 명확하지 않음\n"
                            "- 참고인/관계인 진술 요지: 자료상 명확하지 않음\n"
                            "- 다툼이 있는 부분: 관련자 진술과 기록자료 대조 필요\n\n"
                            "7. 정상참작 사항\n"
                            "- 유리한 정상: 자료상 명확하지 않음\n"
                            "- 불리한 정상: 승인 여부와 경위가 명확히 확인되지 않아 추가 검토가 필요함\n\n"
                            "8. 적용 가능 규정\n"
                            "- 관련 법령/규정: 자료상 명확하지 않음\n"
                            "- 검토 포인트: 승인 절차 준수 여부, 관련 규정 위반 성립 여부, 행위의 반복성 및 조직 영향\n\n"
                            "9. 위원회 판단 포인트\n"
                            "- 사실인정 포인트: 이동 정황 및 승인 여부 확인\n"
                            "- 양정 판단 포인트: 위반 정도, 행위자의 역할, 조직 영향\n"
                            "- 추가 확인 필요 사항: 심의 일시, 대상자 진술, 참고인 진술\n\n"
                            "10. 첨부자료 목록\n"
                            f"- {attachment_text}"
                        ),
                        "versionNote": (
                            "관련 조항 검색과 grounded generation을 거쳐 위원회 참고 자료 초안을 생성했습니다."
                            if generated is not None
                            else "사건 등록 직후 기본 초안이 생성되었습니다."
                        ),
                    }
                )
            elif item["type"] == "disciplinary_resolution":
                generated = generation_artifacts.responses.get("disciplinary_resolution")
                templates.append(
                    {
                        **item,
                        "status": "pending",
                        "legalBasisIds": ["lb-003", "lb-004", "lb-005"],
                        "description": (
                            "최종 의결 입력 전 단계에서 의결서 형식과 판단 구조를 정리한 초안입니다."
                            if generated is not None
                            else "위원회 의결 결과와 처분 방향을 반영하는 최종 문서입니다."
                        ),
                        "content": self._render_generated_document_content(
                            payload,
                            generated,
                            prompt_profile="disciplinary_resolution",
                        )
                        if generated is not None
                        else (
                            "제목: 징계의결서\n\n"
                            "누락정보\n"
                            "- 최종 의결결론\n"
                            "- 의결일자\n"
                            "- 징계위원회명\n"
                            "- 위원장 및 위원 표시\n"
                            "- 정상참작 또는 가중사유\n\n"
                            "1. 징계혐의자 인적사항\n"
                            "- 소속: 자료상 명확하지 않음\n"
                            f"- 직위(직급): {primary_rank}\n"
                            f"- 성명: {primary_name}\n\n"
                            "2. 의결주문\n"
                            "- 자료상 명확하지 않음\n\n"
                            "3. 이유\n"
                            "가. 인정되는 사실\n"
                            f"{payload.details}\n"
                            "나. 증거의 판단\n"
                            f"{attachment_text} 등 제출자료를 종합해 사실관계를 검토할 필요가 있음.\n"
                            "다. 적용 규정\n"
                            "자료상 명확하지 않음.\n"
                            "라. 양정 판단\n"
                            "- 비위의 정도: 자료상 명확하지 않음.\n"
                            "- 고의/과실: 자료상 명확하지 않음.\n"
                            "- 조직 영향: 자료상 명확하지 않음.\n"
                            "- 유리한 정상: 자료상 명확하지 않음.\n"
                            "- 불리한 정상: 자료상 명확하지 않음.\n\n"
                            "4. 의결일자\n"
                            "- 의결일자: 자료상 명확하지 않음\n\n"
                            "5. 징계위원회명\n"
                            "- 징계위원회명: 자료상 명확하지 않음\n\n"
                            "6. 위원장 및 위원 표시\n"
                            "- 위원장 및 위원 표시: 자료상 명확하지 않음"
                        ),
                        "versionNote": (
                            "관련 조항 검색과 grounded generation을 거쳐 징계의결서 초안 구조를 생성했습니다."
                            if generated is not None
                            else "사건 등록 직후 기본 초안이 생성되었습니다."
                        ),
                    }
                )
            else:
                templates.append(
                    {
                        **item,
                        "status": "pending",
                        "legalBasisIds": ["lb-003", "lb-004", "lb-005"],
                        "description": "위원회 의결 결과와 처분 방향을 반영하는 최종 문서입니다.",
                        "content": (
                            f"1. 사용자 입력 사건명\n{payload.title}\n\n"
                            f"2. 사용자 입력 사건 개요\n{payload.summary}\n\n"
                            f"3. 사용자 입력 상세 사실관계\n{payload.details}\n\n"
                            "4. 현재 상태\n최종 의결 결과는 아직 비어 있으며, 위 내용은 사용자 입력 원문 보존용 초안입니다."
                        ),
                        "versionNote": "사건 등록 직후 기본 초안이 생성되었습니다.",
                    }
                )

        results: list[DocumentRecord] = []
        for index, template in enumerate(templates, start=1):
            status = str(template["status"])
            draft_document = DocumentRecord(
                id=f"{case_id}-doc-{index}",
                caseId=case_id,
                title=str(template["title"]),
                type=str(template["type"]),
                order=int(template["order"]),
                status=status,
                description=str(template["description"]),
                content=str(template["content"]),
                legalBasisIds=list(template["legalBasisIds"]),
                versionHistory=[
                    DocumentVersion(
                        version="v1.0" if status == "completed" else "v0.1",
                        updatedAt=created_at,
                        note=str(template.get("versionNote"))
                        or (
                            "사건 등록 직후 필수 문서 초안이 완성되었습니다."
                            if status == "completed"
                            else "사건 등록 직후 기본 초안이 생성되었습니다."
                        ),
                    )
                ],
                reviewHistory=[],
                updatedAt=created_at,
            )
            draft_document.legalBasisIds = self.legal_basis_catalog.resolve_ids_for_document(draft_document)
            results.append(draft_document)
        return results
