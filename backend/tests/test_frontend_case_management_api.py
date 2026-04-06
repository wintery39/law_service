from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app, container
from schemas import DocumentGenerationResponse


class StubCaseDocumentGenerationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def generate(self, request, context) -> DocumentGenerationResponse:
        del context
        self.calls.append((request.user_intent.doc_type, request.constraints.prompt_profile))

        profile = request.constraints.prompt_profile
        instructions = "\n".join(request.constraints.extra_instructions)
        if profile == "fact_finding_report":
            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "fact_summary",
                        "title": "사실결과조사보고",
                        "sections": [
                            {
                                "section_id": "overview",
                                "title": "개요",
                                "text": "본 보고서는 창고 자산 반출 의혹 조사 사건의 사실관계를 정리한 초안입니다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "findings",
                                "title": "조사 결과",
                                "text": "- CCTV와 출입기록을 바탕으로 승인 없는 이동 정황이 확인되었습니다.\n- 추가 면담이 필요한 쟁점은 별도 표시했습니다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                        ],
                        "compiled_text": "개요\n본 보고서는 창고 자산 반출 의혹 조사 사건의 사실관계를 정리한 초안입니다.",
                    },
                    "checklist_missing_info": [],
                    "evidence_report": {
                        "totals_by_type": {"law": 1, "case": 0, "regulation": 1, "form": 0},
                        "used_evidence_ids": ["law:fact-001"],
                        "unused_evidence_ids": [],
                        "section_coverage": {"overview": ["law:fact-001"]},
                        "source_mode": "result",
                    },
                    "warnings": [],
                }
            )

        if profile == "attendance_notice":
            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "fact_summary",
                        "title": "출석통지서",
                        "sections": [
                            {
                                "section_id": "personal_info",
                                "title": "인적사항",
                                "text": "- 성명: 최민수\n- 소속: 자료상 명확하지 않음\n- 직위(직급): 병장\n- 주소: 자료상 명확하지 않음",
                                "citations": ["form:attendance-notice-template"],
                                "open_issues": ["출석 일시", "출석 장소", "징계위원회명"],
                            },
                            {
                                "section_id": "appearance_reason",
                                "title": "출석 이유",
                                "text": "창고 장비 이동 정황 확인으로 위원회 출석이 필요합니다.",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                        ],
                        "compiled_text": "출석통지서\n인적사항\n- 성명: 최민수",
                    },
                    "checklist_missing_info": ["출석 일시", "출석 장소", "징계위원회명"],
                    "evidence_report": {
                        "totals_by_type": {"law": 0, "case": 0, "regulation": 1, "form": 1},
                        "used_evidence_ids": ["form:attendance-notice-template"],
                        "unused_evidence_ids": [],
                        "section_coverage": {"personal_info": ["form:attendance-notice-template"]},
                        "source_mode": "result",
                    },
                    "warnings": [],
                }
            )

        if profile == "committee_reference":
            prevention_plan_text = (
                "- 교육 일정: 자료상 명확하지 않음\n"
                "- 절차 개선 담당자: 자료상 명확하지 않음\n"
                "- 지휘관 확인 의견: 자료상 명확하지 않음"
            )
            prevention_plan_open_issues = ["재발 방지 계획", "지휘관 확인 의견"]
            if "재발 방지 교육 일정과 책임 부서" in instructions:
                prevention_plan_text = (
                    "- 교육 일정: 2026년 3월 22일 09시 정보보호통제실 교육\n"
                    "- 절차 개선 담당자: 정보보호통제실 운영장교\n"
                    "- 지휘관 확인 의견: 자료상 명확하지 않음"
                )
                prevention_plan_open_issues = ["지휘관 확인 의견"]

            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "disciplinary_opinion",
                        "title": "징계위원회 참고자료",
                        "sections": [
                            {
                                "section_id": "case_overview",
                                "title": "사건 개요",
                                "text": "- 사건명: 보안수칙 위반 관련 징계 검토\n- 심의 일시: 자료상 명확하지 않음",
                                "citations": ["form:committee-reference-template"],
                                "open_issues": ["심의 일시"],
                            },
                            {
                                "section_id": "prevention_plan",
                                "title": "재발 방지 계획",
                                "text": prevention_plan_text,
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": prevention_plan_open_issues,
                            },
                        ],
                        "compiled_text": "징계위원회 참고자료\n사건 개요\n- 사건명: 보안수칙 위반 관련 징계 검토",
                    },
                    "checklist_missing_info": ["심의 일시", *prevention_plan_open_issues],
                    "evidence_report": {
                        "totals_by_type": {"law": 0, "case": 1, "regulation": 1, "form": 1},
                        "used_evidence_ids": ["regulation:discipline-guideline"],
                        "unused_evidence_ids": [],
                        "section_coverage": {"case_overview": ["form:committee-reference-template"]},
                        "source_mode": "result",
                    },
                    "warnings": [],
                }
            )

        if profile == "disciplinary_resolution":
            decision_order_text = "- 자료상 명확하지 않음"
            decision_order_open_issues = ["최종 의결결론"]
            reasoning_text = "위원회 참고 자료 보완 결과에 따라 양정 판단을 정리합니다."
            reasoning_open_issues = ["의결일자", "징계위원회명"]

            if "재발 방지 교육 일정과 책임 부서를 위원회 자료에 반영합니다." in instructions:
                reasoning_text = (
                    "위원회 참고 자료에 반영된 재발 방지 계획에 따라 2026년 3월 22일 교육 일정과 "
                    "정보보호통제실 운영장교 책임 하의 절차 개선 조치를 확인했습니다."
                )
            if "최종 처분 집행 일정과 통보 대상을 문안에 더 분명하게 적어 주세요." in instructions:
                decision_order_text = (
                    "- 감봉 1월 처분을 의결하고, 2026년 3월 24일부터 집행하며 "
                    "인사처와 급여담당부서에 결과를 통보합니다."
                )
                decision_order_open_issues = []

            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "disciplinary_opinion",
                        "title": "징계의결서",
                        "sections": [
                            {
                                "section_id": "decision_order",
                                "title": "의결주문",
                                "text": decision_order_text,
                                "citations": ["form:disciplinary-resolution-template"],
                                "open_issues": decision_order_open_issues,
                            },
                            {
                                "section_id": "reasoning",
                                "title": "이유",
                                "text": reasoning_text,
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": reasoning_open_issues,
                            },
                        ],
                        "compiled_text": "징계의결서\n의결주문\n- 자료상 명확하지 않음",
                    },
                    "checklist_missing_info": [*decision_order_open_issues, *reasoning_open_issues],
                    "evidence_report": {
                        "totals_by_type": {"law": 0, "case": 1, "regulation": 1, "form": 1},
                        "used_evidence_ids": ["regulation:discipline-guideline"],
                        "unused_evidence_ids": [],
                        "section_coverage": {"reasoning": ["regulation:discipline-guideline"]},
                        "source_mode": "result",
                    },
                    "warnings": [],
                }
            )

        raise AssertionError(f"unexpected prompt_profile: {profile}")


class FailingCaseDocumentGenerationService:
    async def generate(self, request, context) -> DocumentGenerationResponse:
        del request, context
        raise RuntimeError("generation failed")


@pytest.fixture(autouse=True)
def reset_case_management_service() -> None:
    container.case_management_service.reset()
    yield
    container.case_management_service.reset()


@pytest.fixture
def stub_case_document_generation_service() -> StubCaseDocumentGenerationService:
    stub = StubCaseDocumentGenerationService()
    original_service = container.case_management_service.document_generation_service
    container.case_management_service.document_generation_service = stub
    yield stub
    container.case_management_service.document_generation_service = original_service


def test_list_cases_and_metrics_follow_frontend_contract() -> None:
    with TestClient(app) as client:
        cases_response = client.get("/api/cases")
        metrics_response = client.get("/api/cases/metrics")

    assert cases_response.status_code == 200
    assert metrics_response.status_code == 200

    cases = cases_response.json()
    metrics = metrics_response.json()

    assert len(cases) == 2
    assert {item["caseType"] for item in cases} == {"disciplinary"}
    assert "progressPercent" in cases[0]
    assert "activeQuestionCount" in cases[0]
    assert "openReviewCount" in cases[0]
    assert metrics == {
        "totalCases": 2,
        "inProgressCases": 0,
        "completedCases": 1,
        "waitingCases": 1,
    }


def test_get_case_detail_hydrates_workflow_timeline_documents_and_questions() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/case-005")

    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "case-005"
    assert payload["attachmentProvided"] is True
    assert payload["openReviewCount"] == 1
    assert len(payload["documents"]) == 4
    assert len(payload["questions"]) == 1
    assert payload["questions"][0]["status"] == "open"
    assert payload["documents"][0]["approvedBody"]["compiledText"] == payload["documents"][0]["content"]
    assert payload["workflowStages"][0]["id"] == "case_registration"
    assert payload["workflowStages"][1]["status"] == "completed"
    assert payload["workflowStages"][2]["status"] == "active"
    assert payload["workflowStages"][3]["status"] == "pending"
    assert payload["workflowStages"][4]["status"] == "active"


def test_get_document_detail_includes_change_set_fields_questions_and_navigation() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/case-005/documents/doc-019")

    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "doc-019"
    assert payload["caseId"] == "case-005"
    assert payload["title"] == "위원회 참고 자료"
    assert payload["legalBasis"][0]["id"] == "lb-003"
    assert payload["approvedBody"]["compiledText"] == payload["content"]
    assert payload["activeChangeSet"] is None
    assert payload["changeSetHistory"] == []
    assert payload["changeSetHistorySummary"] == []
    assert payload["previousDocumentId"] == "doc-018"
    assert payload["nextDocumentId"] == "doc-020"
    assert payload["questions"][0]["id"] == "question-005"


def test_create_disciplinary_case_applies_initial_generated_drafts_without_approval(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/cases",
            json={
                "title": "창고 자산 반출 의혹 조사",
                "caseType": "disciplinary",
                "occurredAt": "2026-03-19T09:00:00.000Z",
                "location": "제3보급대대 창고동",
                "author": "대위 홍길동",
                "relatedPersons": ["병장 최민수", "중사 이영호"],
                "summary": "정식 승인 없이 장비 상자가 외부 적재 구역으로 이동한 정황이 확인되었습니다.",
                "details": "창고 출입기록과 CCTV 확인 결과, 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다. 관련자 진술과 재물 관리대장 사이에 차이가 있어 추가 확인이 진행 중입니다.",
                "attachmentProvided": True,
                "attachmentSummary": "CCTV 캡처본과 창고 출입기록이 첨부되었습니다.",
                "priority": "high",
            },
        )

    assert response.status_code == 201
    payload = response.json()

    assert payload["caseType"] == "disciplinary"
    assert payload["status"] == "waiting_for_input"
    assert payload["documentCount"] == 4
    assert payload["activeQuestionCount"] == 3
    assert payload["workflowStages"][2]["status"] == "active"
    assert payload["workflowStages"][3]["status"] == "pending"
    assert payload["workflowStages"][4]["status"] == "pending"

    assert payload["documents"][0]["title"] == "사실결과조사보고"
    assert payload["documents"][0]["status"] == "completed"
    assert payload["documents"][0]["content"].startswith("1. 개요")
    assert payload["documents"][0]["activeChangeSet"] is None
    assert payload["documents"][0]["versionHistory"][0]["version"] == "v1.0"

    assert payload["documents"][1]["status"] == "needs_input"
    assert payload["documents"][1]["activeChangeSet"] is None
    assert payload["documents"][2]["status"] == "needs_input"
    assert payload["documents"][2]["activeChangeSet"] is None
    assert payload["documents"][3]["status"] == "needs_input"
    assert payload["documents"][3]["activeChangeSet"] is None
    assert len(payload["questions"]) == 3
    assert set(stub_case_document_generation_service.calls) == {
        ("fact_summary", "fact_finding_report"),
        ("fact_summary", "attendance_notice"),
        ("disciplinary_opinion", "committee_reference"),
        ("disciplinary_opinion", "disciplinary_resolution"),
    }


def test_documents_list_resolves_legal_basis_ids_for_created_case(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/cases",
            json={
                "title": "보안점검 절차 위반 검토",
                "caseType": "disciplinary",
                "occurredAt": "2026-03-21T09:00:00.000Z",
                "location": "정보보호통제실",
                "author": "대위 김민수",
                "relatedPersons": ["중사 박정훈"],
                "summary": "보안점검 절차를 생략한 정황이 확인되었습니다.",
                "details": "외부 장비 연결 전 승인 체크를 생략한 사실이 확인되어 징계 검토가 필요합니다.",
                "attachmentProvided": True,
                "attachmentSummary": "점검 로그와 승인 기록 캡처를 첨부했습니다.",
                "priority": "high",
            },
        )
        case_id = create_response.json()["id"]
        documents_response = client.get(f"/api/cases/{case_id}/documents")

    assert create_response.status_code == 201
    assert documents_response.status_code == 200

    documents = documents_response.json()
    assert len(documents) == 4
    assert all(document["legalBasisIds"] for document in documents)
    assert documents[0]["title"] == "사실결과조사보고"
    assert documents[0]["activeChangeSet"] is None
    assert set(stub_case_document_generation_service.calls) == {
        ("fact_summary", "fact_finding_report"),
        ("fact_summary", "attendance_notice"),
        ("disciplinary_opinion", "committee_reference"),
        ("disciplinary_opinion", "disciplinary_resolution"),
    }


def test_apply_document_change_set_updates_official_content_and_history(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    with TestClient(app) as client:
        review_response = client.post(
            "/api/cases/case-005/documents/doc-020/reviews",
            json={
                "title": "위원회 의결 문안 보완",
                "description": "최종 처분 집행 일정과 통보 대상을 문안에 더 분명하게 적어 주세요.",
            },
        )
        review_payload = review_response.json()
        change_set = review_payload["activeChangeSet"]
        response = client.post(
            f"/api/cases/case-005/documents/doc-020/change-sets/{change_set['id']}/apply",
            json={
                "approvedPatchIds": [change_set["patches"][0]["id"]],
                "rejectedPatchIds": [],
            },
        )

    assert review_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] in {"completed", "needs_input"}
    assert payload["activeChangeSet"] is None
    assert payload["changeSetHistory"][0]["status"] == "applied"
    assert payload["changeSetHistorySummary"][0]["status"] == "applied"
    assert payload["versionHistory"][0]["version"] == "v1.0"
    assert "승인된 섹션 1건" in payload["versionHistory"][0]["note"]
    assert payload["approvedBody"]["compiledText"] == payload["content"]


def test_submit_document_review_creates_change_set_and_blocks_direct_resolve(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/cases/case-005/documents/doc-020/reviews",
            json={
                "title": "위원회 의결 문안 보완",
                "description": "최종 처분 집행 일정과 통보 대상을 문안에 더 분명하게 적어 주세요.",
            },
        )

        payload = response.json()
        review_id = payload["reviewHistory"][0]["id"]
        resolve_response = client.post(f"/api/cases/case-005/documents/doc-020/reviews/{review_id}/resolve")

    assert response.status_code == 200
    assert payload["status"] == "needs_input"
    assert payload["activeChangeSet"]["title"] == "위원회 의결 문안 보완 수정안"
    assert payload["activeChangeSet"]["relatedReviewId"] == review_id
    assert len(payload["activeChangeSet"]["patches"]) == 1
    assert payload["activeChangeSet"]["patches"][0]["sectionTitle"] == "의결주문"
    assert payload["activeChangeSet"]["patches"][0]["decision"] == "rejected"
    assert payload["reviewHistory"][0]["status"] == "open"
    assert resolve_response.status_code == 409
    assert "승인 대기 중인 수정안" in resolve_response.json()["detail"]


def test_submit_question_answer_creates_new_change_set_and_follow_up_question(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    answer = "재발 방지 교육 일정과 책임 부서를 위원회 자료에 반영합니다."

    with TestClient(app) as client:
        response = client.post(
            "/api/questions/question-005/answer",
            json={"answer": answer},
        )
        document_response = client.get("/api/cases/case-005/documents/doc-019")
        downstream_document_response = client.get("/api/cases/case-005/documents/doc-020")

    assert response.status_code == 200
    assert document_response.status_code == 200
    assert downstream_document_response.status_code == 200

    payload = response.json()
    document_payload = document_response.json()
    downstream_document_payload = downstream_document_response.json()

    assert payload["status"] == "waiting_for_input"
    assert payload["activeQuestionCount"] == 2
    assert any(item["status"] == "answered" and item["answer"] == answer for item in payload["questions"])
    assert document_payload["status"] == "needs_input"
    assert document_payload["activeChangeSet"]["title"] == "위원회 보고용 재발 방지 계획 확정 반영 수정안"
    assert document_payload["activeChangeSet"]["relatedQuestionId"] == "question-005"
    assert len(document_payload["activeChangeSet"]["patches"]) == 1
    assert document_payload["activeChangeSet"]["patches"][0]["sectionTitle"] == "재발 방지 계획"
    assert document_payload["activeChangeSet"]["patches"][0]["decision"] == "rejected"
    assert [item["status"] for item in document_payload["questions"]] == ["open", "answered"]
    assert downstream_document_payload["activeChangeSet"] is not None
    assert downstream_document_payload["activeChangeSet"]["relatedQuestionId"] == "question-005"
    assert len(downstream_document_payload["activeChangeSet"]["patches"]) == 1
    assert downstream_document_payload["activeChangeSet"]["patches"][0]["sectionTitle"] == "이유"
    assert downstream_document_payload["activeChangeSet"]["patches"][0]["decision"] == "rejected"
    assert any(item["status"] == "open" for item in downstream_document_payload["questions"])


def test_apply_review_feedback_change_set_resolves_linked_review(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    with TestClient(app) as client:
        review_response = client.post(
            "/api/cases/case-005/documents/doc-020/reviews",
            json={
                "title": "위원회 의결 문안 보완",
                "description": "최종 처분 집행 일정과 통보 대상을 문안에 더 분명하게 적어 주세요.",
            },
        )
        review_payload = review_response.json()
        change_set = review_payload["activeChangeSet"]
        apply_response = client.post(
            f"/api/cases/case-005/documents/doc-020/change-sets/{change_set['id']}/apply",
            json={
                "approvedPatchIds": [change_set["patches"][0]["id"]],
                "rejectedPatchIds": [],
            },
        )
        case_response = client.get("/api/cases/case-005")

    assert review_response.status_code == 200
    assert apply_response.status_code == 200
    assert case_response.status_code == 200

    payload = apply_response.json()
    case_payload = case_response.json()

    assert payload["reviewHistory"][0]["status"] == "resolved"
    assert case_payload["openReviewCount"] == 1


def test_create_case_returns_service_unavailable_when_initial_generation_fails() -> None:
    failing_service = FailingCaseDocumentGenerationService()
    original_service = container.case_management_service.document_generation_service
    container.case_management_service.document_generation_service = failing_service
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/cases",
                json={
                    "title": "Gemini 강제 생성 실패 확인",
                    "caseType": "disciplinary",
                    "occurredAt": "2026-03-19T09:00:00.000Z",
                    "location": "제3보급대대 창고동",
                    "author": "대위 홍길동",
                    "relatedPersons": ["병장 최민수"],
                    "summary": "초기 생성 실패 시 사건 생성 자체가 중단되어야 합니다.",
                    "details": "Gemini 생성 실패를 강제로 재현합니다.",
                    "attachmentProvided": True,
                    "attachmentSummary": "첨부자료 요약",
                    "priority": "high",
                },
            )
            cases_response = client.get("/api/cases")
    finally:
        container.case_management_service.document_generation_service = original_service

    assert response.status_code == 503
    assert "초기 문서 생성에 실패했습니다" in response.json()["detail"]
    assert len(cases_response.json()) == 2


def test_generation_failure_preserves_answer_and_review_request() -> None:
    failing_service = FailingCaseDocumentGenerationService()
    original_service = container.case_management_service.document_generation_service
    container.case_management_service.document_generation_service = failing_service
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            answer_response = client.post(
                "/api/questions/question-005/answer",
                json={"answer": "재발 방지 계획 답변"},
            )
            question_payload = client.get("/api/cases/case-005").json()["questions"][0]

            review_response = client.post(
                "/api/cases/case-005/documents/doc-020/reviews",
                json={
                    "title": "문구 보완",
                    "description": "최종 처분 집행 일정을 보완해 주세요.",
                },
            )
            document_payload = client.get("/api/cases/case-005/documents/doc-020").json()
    finally:
        container.case_management_service.document_generation_service = original_service

    assert answer_response.status_code == 503
    assert "Gemini 문서 수정안 생성에 실패했습니다" in answer_response.json()["detail"]
    assert question_payload["status"] == "answered"
    assert question_payload["answer"] == "재발 방지 계획 답변"

    assert review_response.status_code == 503
    assert "Gemini 문서 수정안 생성에 실패했습니다" in review_response.json()["detail"]
    assert document_payload["reviewHistory"][0]["title"] == "문구 보완"
    assert document_payload["reviewHistory"][0]["status"] == "open"
    assert document_payload["activeChangeSet"] is None


def test_create_case_rejects_non_disciplinary_case_type() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/cases",
            json={
                "title": "형사 사건 초안",
                "caseType": "criminal",
                "occurredAt": "2026-03-19T09:00:00.000Z",
                "location": "훈련장",
                "author": "중위 김수현",
                "relatedPersons": ["병장 최민수"],
                "summary": "형사 사건은 아직 1차 범위가 아닙니다.",
                "details": "disciplinary 범위만 먼저 지원합니다.",
                "attachmentProvided": False,
                "attachmentSummary": "",
                "priority": "medium",
            },
        )

    assert response.status_code == 422
    assert "disciplinary 사건만 지원" in response.json()["detail"]


def test_answering_same_question_twice_returns_validation_error(
    stub_case_document_generation_service: StubCaseDocumentGenerationService,
) -> None:
    with TestClient(app) as client:
        first_response = client.post(
            "/api/questions/question-005/answer",
            json={"answer": "재발 방지 교육 일정을 반영했습니다."},
        )
        second_response = client.post(
            "/api/questions/question-005/answer",
            json={"answer": "동일 질문에 다시 답변합니다."},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 422
    assert "이미 답변이 제출된 질문" in second_response.json()["detail"]


def test_legal_basis_endpoint_returns_mock_data_catalog_entries() -> None:
    with TestClient(app) as client:
        response = client.get("/api/legal-basis", params=[("ids", "lb-003"), ("ids", "lb-004")])

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["lb-003", "lb-004"]
    assert payload[0]["lawName"] == "군인 징계령"
    assert payload[1]["article"] == "제3조"


def test_missing_case_returns_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/unknown-case")

    assert response.status_code == 404
    assert "사건 정보를 찾을 수 없습니다." in response.json()["detail"]
