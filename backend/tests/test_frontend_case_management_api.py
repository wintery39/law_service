from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app, container


@pytest.fixture(autouse=True)
def reset_case_management_service() -> None:
    container.case_management_service.reset()
    yield
    container.case_management_service.reset()


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
    assert len(payload["documents"]) == 4
    assert len(payload["questions"]) == 1
    assert payload["questions"][0]["status"] == "open"
    assert payload["workflowStages"][0]["id"] == "case_registration"
    assert payload["workflowStages"][1]["status"] == "completed"
    assert payload["workflowStages"][2]["status"] == "active"
    assert payload["timeline"][0]["stageId"] in {
        "information_request",
        "document_generation",
        "review_feedback",
        "attachment_registration",
        "case_registration",
    }


def test_get_document_detail_includes_mock_data_legal_basis_questions_and_navigation() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/case-005/documents/doc-019")

    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "doc-019"
    assert payload["caseId"] == "case-005"
    assert payload["legalBasis"][0]["lawName"] == "군인 징계령 시행규칙"
    assert payload["legalBasis"][0]["article"] in {"제2조", "제3조", "별표 1", "별표 2"}
    assert payload["previousDocumentId"] == "doc-018"
    assert payload["nextDocumentId"] == "doc-020"
    assert payload["questions"][0]["id"] == "question-005-001"


def test_create_disciplinary_case_returns_frontend_ready_case_detail() -> None:
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
    assert payload["documentCount"] == 3
    assert payload["documents"][0]["title"] == "조사보고서"
    assert payload["documents"][0]["status"] == "completed"
    assert payload["documents"][1]["title"] == "징계 수준 검토표"
    assert payload["documents"][1]["status"] == "generating"
    assert payload["documents"][2]["title"] == "제출 전 최종 점검표"
    assert payload["documents"][0]["legalBasisIds"]
    assert payload["workflowStages"][3]["status"] == "active"


def test_documents_list_resolves_legal_basis_ids_for_created_case() -> None:
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
    assert len(documents) == 3
    assert all(document["legalBasisIds"] for document in documents)
    assert documents[0]["title"] == "조사보고서"
    assert documents[0]["legalBasisIds"][0].startswith("mdr-")


def test_submit_question_answer_updates_case_status_document_history_and_content() -> None:
    answer = "재발 방지 교육은 2026년 3월 21일 전 부서원을 대상으로 실시하고, 외부 장비 연결은 사전 승인 체크리스트를 통과한 경우에만 허용하며, 지휘관은 주간 점검 결과를 직접 확인하기로 했습니다."

    with TestClient(app) as client:
        response = client.post(
            "/api/questions/question-005-001/answer",
            json={"answer": answer},
        )
        document_response = client.get("/api/cases/case-005/documents/doc-019")

    assert response.status_code == 200
    assert document_response.status_code == 200

    payload = response.json()
    document_payload = document_response.json()

    assert payload["status"] == "in_progress"
    assert payload["activeQuestionCount"] == 0
    assert payload["questions"][0]["status"] == "answered"
    assert document_payload["status"] == "generating"
    assert document_payload["versionHistory"][0]["note"] == "추가 질문 답변이 반영되어 초안이 갱신되었습니다."
    assert document_payload["reviewHistory"][0]["status"] == "resolved"
    assert answer in document_payload["content"]


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


def test_answering_same_question_twice_returns_validation_error() -> None:
    with TestClient(app) as client:
        first_response = client.post(
            "/api/questions/question-005-001/answer",
            json={"answer": "재발 방지 교육 일정을 반영했습니다."},
        )
        second_response = client.post(
            "/api/questions/question-005-001/answer",
            json={"answer": "동일 질문에 다시 답변합니다."},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 422
    assert "이미 답변이 제출된 질문" in second_response.json()["detail"]


def test_legal_basis_endpoint_returns_mock_data_catalog_entries() -> None:
    with TestClient(app) as client:
        response = client.get("/api/legal-basis", params=[("ids", "mdr-art-006"), ("ids", "mdr-form-001")])

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["mdr-art-006", "mdr-form-001"]
    assert payload[0]["lawName"] == "군인 징계령 시행규칙"
    assert payload[1]["article"] == "별지 제2호의2서식"


def test_missing_case_returns_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/unknown-case")

    assert response.status_code == 404
    assert "사건 정보를 찾을 수 없습니다." in response.json()["detail"]
