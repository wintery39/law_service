from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

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
        "description": "사건 기본 정보와 관련 사실관계를 등록합니다.",
    },
    "attachment_registration": {
        "title": "첨부 자료 등록",
        "caption": "2단계",
        "description": "필요한 첨부 자료를 등록하고, 없으면 이 단계를 건너뜁니다.",
    },
    "information_request": {
        "title": "필요한 정보 요청",
        "caption": "3단계",
        "description": "LLM이 문서 작성을 위해 필요한 추가 정보를 요청합니다.",
    },
    "document_generation": {
        "title": "문서 생성",
        "caption": "4단계",
        "description": "최종적으로 필요한 문서 초안과 패키지를 생성합니다.",
    },
    "review_feedback": {
        "title": "문서 검토 및 유저 피드백",
        "caption": "5단계",
        "description": "생성된 문서를 검토하고 사용자 피드백을 반영해 재검토합니다.",
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


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


class FrontendCaseManagementService:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[2]
        self.mock_dir = self.root_dir / "frontend" / "src" / "mocks"
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

    def create_case(self, payload: CaseCreatePayload) -> CaseDetail:
        with self._lock:
            now = _utcnow_iso()
            case_id = f"case-{uuid4().hex[:8]}"
            documents = self._build_document_templates(payload, case_id, now)
            progress_percent = self._get_document_status_progress(documents)

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
                documentCount=len(documents),
            )
            detail = SeedCaseDetail(
                **summary.model_dump(),
                attachmentProvided=payload.attachmentProvided,
                attachmentSummary=payload.attachmentSummary,
                legalReviewSummary=(
                    "사건 등록 직후 생성된 기본 검토 메모입니다. 문서 초안이 보완되면 적용 조항과 위험 포인트가 자동으로 정리됩니다."
                ),
                urgencyNote="현재는 초기 등록 단계이며, 추가 입력이나 후속 자료가 들어오면 상태가 갱신됩니다.",
                timeline=[
                    SeedTimelineEvent(
                        id=f"{case_id}-timeline-003",
                        stageId="document_generation",
                        type="document_generated",
                        title="기본 문서 패키지 생성",
                        description=f"{len(documents)}개의 기본 문서가 사건 유형에 맞춰 생성되었습니다.",
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

            self._database["cases"].insert(0, summary)
            self._database["caseDetails"].insert(0, detail)
            self._database["documents"].extend(documents)
            return self._hydrate_case_detail(case_id)

    def get_documents_by_case_id(self, case_id: str) -> list[DocumentRecord]:
        with self._lock:
            self._ensure_case(case_id)
            return deepcopy(self._get_documents_for_case(case_id))

    def get_document_by_id(self, case_id: str, document_id: str) -> DocumentDetail:
        with self._lock:
            documents = self._get_documents_for_case(case_id)
            document = next((item for item in documents if item.id == document_id), None)
            if document is None:
                raise KeyError("문서 정보를 찾을 수 없습니다.")
            index = next(index for index, item in enumerate(documents) if item.id == document_id)
            return DocumentDetail(
                **document.model_dump(),
                legalBasis=[
                    deepcopy(item)
                    for item in self._database["legalBasis"]
                    if item.id in document.legalBasisIds
                ],
                questions=[
                    deepcopy(item)
                    for item in self._get_questions_for_case(case_id)
                    if item.documentId == document_id
                ],
                previousDocumentId=documents[index - 1].id if index > 0 else None,
                nextDocumentId=documents[index + 1].id if index < len(documents) - 1 else None,
            )

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
            return [deepcopy(item) for item in self._database["legalBasis"] if item.id in ids]

    def _load_seed_database(self) -> dict[str, list[object]]:
        if not self.mock_dir.exists():
            raise RuntimeError(f"frontend mock directory not found: {self.mock_dir}")

        return {
            "cases": self._load_json("cases.json", CaseSummary),
            "caseDetails": self._load_json("case-detail.json", SeedCaseDetail),
            "documents": self._load_json("documents.json", DocumentRecord),
            "questions": self._load_json("questions.json", QuestionRecord),
            "legalBasis": self._load_json("legal-basis.json", LegalBasisEntry),
        }

    def _load_json(self, filename: str, model_cls):
        path = self.mock_dir / filename
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
                detail=f"{case_detail.author} 작성자가 사건을 등록하고 발생 시점, 관련자, 사실관계를 입력했습니다.",
                status="completed",
                **WORKFLOW_STAGE_META["case_registration"],
            ),
            WorkflowStage(
                id="attachment_registration",
                detail=(
                    case_detail.attachmentSummary or "첨부 자료가 등록되어 이후 문서 생성에 활용됩니다."
                    if case_detail.attachmentProvided
                    else "첨부 자료 없이 진행하기로 선택해 이 단계를 건너뛰었습니다."
                ),
                status="completed" if case_detail.attachmentProvided else "skipped",
                **WORKFLOW_STAGE_META["attachment_registration"],
            ),
            WorkflowStage(
                id="information_request",
                detail=(
                    f"{len(open_questions)}건의 추가 정보 요청이 열려 있으며, "
                    f"{f'{documents_needing_input}개 문서가 답변을 기다리고 있습니다.' if documents_needing_input > 0 else '관련 문서가 답변을 기다리고 있습니다.'}"
                    if open_questions
                    else (
                        f"{len(answered_questions)}건의 요청 정보가 반영되어 문서 작성이 다시 진행 중입니다."
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
                    f"{len(case_detail.documents)}개의 문서가 모두 생성 완료되었습니다."
                    if documents_completed
                    else (
                        f"{len(case_detail.documents)}개 문서 중 {generating_documents}개 작성 중, "
                        f"{pending_documents}개 대기, {documents_needing_input}개 추가 정보 필요 상태입니다."
                    )
                ),
                status=(
                    "completed"
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
                    "문서 생성이 완료되면 검토와 피드백 반영 단계로 넘어갑니다."
                    if not documents_completed
                    else (
                        f"{open_reviews}건의 검토 요청이 열려 있으며, 사용자 피드백 반영이 필요합니다."
                        if open_reviews > 0
                        else (
                            f"{resolved_reviews}건의 검토 이력이 정리되었고 현재 열린 피드백은 없습니다."
                            if has_review_history
                            else "검토 요청 없이 문서 패키지가 마무리되었습니다."
                        )
                    )
                ),
                status="pending" if not documents_completed else "active" if open_reviews > 0 else "completed",
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
        now = _utcnow_iso()

        next_status = self._derive_case_status(progress_percent, documents, questions)
        summary.progressPercent = progress_percent
        summary.activeQuestionCount = open_question_count
        summary.documentCount = len(documents)
        summary.status = next_status
        summary.updatedAt = now

        detail.status = next_status
        detail.progressPercent = progress_percent
        detail.activeQuestionCount = open_question_count
        detail.documentCount = len(documents)
        detail.updatedAt = now

    def _hydrate_case_detail(self, case_id: str) -> CaseDetail:
        summary, detail = self._ensure_case(case_id)
        documents = [deepcopy(item) for item in self._get_documents_for_case(case_id)]
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

    def _build_document_templates(
        self,
        payload: CaseCreatePayload,
        case_id: str,
        created_at: str,
    ) -> list[DocumentRecord]:
        shared_templates: dict[str, list[dict[str, object]]] = {
            "criminal": [
                {
                    "title": "사건 접수 보고서",
                    "type": "intake_report",
                    "order": 1,
                    "status": "completed",
                    "description": "사건 등록 직후 접수 경위와 초동 조치를 정리하는 보고서입니다.",
                    "content": (
                        f"1. 접수 배경\n{payload.title} 사건이 등록되었으며, 작성자 {payload.author}가 초동 사실관계를 입력했습니다.\n\n"
                        f"2. 주요 사실\n{payload.summary}\n\n"
                        "3. 후속 계획\n상세 사실관계와 관련자 정보를 바탕으로 진술서 및 경위서를 단계적으로 생성합니다."
                    ),
                    "legalBasisIds": ["lb-002", "lb-007"],
                },
                {
                    "title": "사건경위서",
                    "type": "incident_report",
                    "order": 2,
                    "status": "generating",
                    "description": "현재 입력된 사실관계를 시간순으로 정리하는 사건경위서입니다.",
                    "content": (
                        f"1. 사건 개요\n{payload.details}\n\n"
                        f"2. 위치 및 관련자\n발생 장소는 {payload.location}이며, 관련자는 {', '.join(payload.relatedPersons)}입니다.\n\n"
                        "3. 현재 상태\n초기 문서 구조가 생성되었고, 추가 확인이 필요한 항목은 후속 질문으로 연결될 수 있습니다."
                    ),
                    "legalBasisIds": ["lb-002"],
                },
                {
                    "title": "법률 검토 메모",
                    "type": "legal_memo",
                    "order": 3,
                    "status": "pending",
                    "description": "기초 문서가 정리된 후 적용 법 조항과 검토 포인트를 요약하는 문서입니다.",
                    "content": (
                        "1. 검토 목적\n기초 문서 완성 이후 적용 조항과 추가 조사 필요성을 정리합니다.\n\n"
                        "2. 현재 상태\n세부 문서 생성 완료 전까지는 틀만 유지합니다."
                    ),
                    "legalBasisIds": ["lb-002"],
                },
            ],
            "disciplinary": [
                {
                    "title": "조사보고서",
                    "type": "investigation_report",
                    "order": 1,
                    "status": "completed",
                    "description": "징계 검토를 위한 사실관계 조사보고서입니다.",
                    "content": (
                        f"1. 사건 개요\n{payload.summary}\n\n"
                        "2. 조사 방향\n행위 사실, 반복성, 부대 영향도를 중심으로 검토합니다.\n\n"
                        f"3. 참고\n작성자 {payload.author}가 입력한 사실관계를 기준으로 초안이 생성되었습니다."
                    ),
                    "legalBasisIds": ["lb-003"],
                },
                {
                    "title": "징계 수준 검토표",
                    "type": "sanction_matrix",
                    "order": 2,
                    "status": "generating",
                    "description": "징계 수위 판단 요소를 정리하는 검토표입니다.",
                    "content": (
                        f"1. 평가 요소\n우선순위는 {payload.priority}이며, 사건 상세 사실관계를 기준으로 고의성과 영향도를 평가합니다.\n\n"
                        "2. 현재 상태\n보완 자료 수집 전 단계로, 평가 문구는 생성 중입니다."
                    ),
                    "legalBasisIds": ["lb-003", "lb-005"],
                },
                {
                    "title": "제출 전 최종 점검표",
                    "type": "final_checklist",
                    "order": 3,
                    "status": "pending",
                    "description": "문서 패키지 제출 전 누락 항목을 확인하는 체크리스트입니다.",
                    "content": (
                        "1. 점검 범위\n조사보고서, 검토표, 증빙자료 첨부 여부를 확인합니다.\n\n"
                        "2. 현재 상태\n문서 생성 흐름 초기 단계입니다."
                    ),
                    "legalBasisIds": ["lb-004"],
                },
            ],
            "other": [
                {
                    "title": "사실관계 확인 메모",
                    "type": "fact_memo",
                    "order": 1,
                    "status": "generating",
                    "description": "사실확인 중심의 초기 메모입니다.",
                    "content": (
                        f"1. 사건 배경\n{payload.summary}\n\n"
                        f"2. 상세 기록\n{payload.details}\n\n"
                        "3. 후속 조치\n관계부서 확인 후 통보 문안을 확정합니다."
                    ),
                    "legalBasisIds": ["lb-008"],
                },
                {
                    "title": "관계부서 통보서",
                    "type": "department_notice",
                    "order": 2,
                    "status": "pending",
                    "description": "관련 부서에 자료 회신을 요청하는 통보서입니다.",
                    "content": "1. 통보 목적\n확인 결과 회신 요청\n\n2. 현재 상태\n초안 생성 대기 중",
                    "legalBasisIds": ["lb-008"],
                },
                {
                    "title": "초동조치 체크리스트",
                    "type": "checklist",
                    "order": 3,
                    "status": "pending",
                    "description": "필수 확인 항목을 정리하는 체크리스트입니다.",
                    "content": "1. 점검 항목\n접수, 전달, 회신, 일정\n\n2. 현재 상태\n초안 생성 대기 중",
                    "legalBasisIds": ["lb-008"],
                },
            ],
        }

        templates = shared_templates[payload.caseType]
        results: list[DocumentRecord] = []
        for index, template in enumerate(templates, start=1):
            results.append(
                DocumentRecord(
                    id=f"{case_id}-doc-{index}",
                    caseId=case_id,
                    title=str(template["title"]),
                    type=str(template["type"]),
                    order=int(template["order"]),
                    status=str(template["status"]),
                    description=str(template["description"]),
                    content=str(template["content"]),
                    legalBasisIds=list(template["legalBasisIds"]),
                    versionHistory=[
                        DocumentVersion(
                            version="v0.1",
                            updatedAt=created_at,
                            note="사건 등록 직후 기본 초안 생성",
                        )
                    ],
                    reviewHistory=[],
                    updatedAt=created_at,
                )
            )
        return results
