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

    assert len(cases) == 5
    assert cases[0]["caseType"] in {"criminal", "disciplinary", "other"}
    assert "progressPercent" in cases[0]
    assert "activeQuestionCount" in cases[0]
    assert metrics == {
        "totalCases": 5,
        "inProgressCases": 1,
        "completedCases": 1,
        "waitingCases": 2,
    }


def test_get_case_detail_hydrates_workflow_timeline_documents_and_questions() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/case-001")

    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "case-001"
    assert payload["attachmentProvided"] is True
    assert len(payload["documents"]) == 4
    assert len(payload["questions"]) == 1
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


def test_get_document_detail_includes_legal_basis_questions_and_navigation() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/case-001/documents/doc-002")

    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "doc-002"
    assert payload["caseId"] == "case-001"
    assert payload["legalBasis"][0]["lawName"] == "군형법"
    assert payload["previousDocumentId"] == "doc-001"
    assert payload["nextDocumentId"] == "doc-003"
    assert payload["questions"] == []


def test_create_case_returns_frontend_ready_case_detail() -> None:
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
    assert payload["documents"][0]["status"] == "completed"
    assert payload["documents"][1]["status"] == "generating"
    assert payload["workflowStages"][3]["status"] == "active"


def test_submit_question_answer_updates_case_status_and_document_history() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/questions/question-001/answer",
            json={"answer": "장비 상자 2개와 예비 부품 상자 1개가 외부 적재 구역으로 이동했고 현재는 임시 보관창고 C-1에 보관 중입니다."},
        )
        document_response = client.get("/api/cases/case-001/documents/doc-003")

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


def test_missing_case_returns_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases/unknown-case")

    assert response.status_code == 404
    assert "사건 정보를 찾을 수 없습니다." in response.json()["detail"]
