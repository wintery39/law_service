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

        if request.constraints.prompt_profile == "fact_finding_report":
            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "fact_summary",
                        "title": "사실결과조사보고",
                        "sections": [
                            {
                                "section_id": "overview",
                                "title": "개요",
                                "text": "본 보고서는 창고 자산 반출 의혹 조사 사건에 대한 사실관계와 관련 자료를 확인하기 위해 작성하였다. 현재까지 확인된 자료를 기준으로 사건 개요를 정리한다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "subject_profile",
                                "title": "징계혐의자 인적사항",
                                "text": "- 소속: 자료상 명확하지 않음\n- 직위/직급: 병장\n- 성명: 최민수\n- 사건명: 창고 자산 반출 의혹 조사",
                                "citations": ["form:fact-summary-template"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "allegations",
                                "title": "징계혐의사실",
                                "text": "- 혐의사실 1: 2026-03-19 09:00경 제3보급대대 창고동에서 정식 승인 없이 장비 상자 2개가 외부 적재 구역으로 이동한 정황이 확인되었다.\n- 혐의사실 2: 관련자 진술과 재물 관리대장 기록 사이에 차이가 있어 반출 절차 준수 여부가 쟁점으로 남아 있다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "findings",
                                "title": "사실조사 결과",
                                "text": "- 인정되는 사실: 창고 출입기록과 CCTV 확인 결과 장비 상자 이동 정황이 확인된다.\n- 다툼이 있는 사항: 이동 경위와 승인 여부에 관한 관련자 진술이 일치하지 않는다.\n- 확인되지 않은 사항: 소속 부서 세부 정보는 자료상 명확하지 않다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "evidence_summary",
                                "title": "증거요지",
                                "text": "- 증거 1: 창고 출입기록\n- 증거 2: CCTV 캡처본\n- 각 증거로 확인되는 내용: 장비 상자 이동 시점과 이동 정황이 기록상 확인된다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "mitigating_aggravating",
                                "title": "정상자료",
                                "text": "- 유리한 정상: 자료상 명확하지 않음\n- 불리한 정상: 승인 절차 준수 여부가 미확인 상태로 남아 있다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "integrated_opinion",
                                "title": "종합의견",
                                "text": "현재 자료에 따르면 장비 상자 이동 정황은 확인되나, 승인 여부와 경위에 관한 추가 확인이 필요하다. 따라서 확인된 자료 범위에서 사실관계를 정리하여 보고한다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "recommendation",
                                "title": "건의",
                                "text": "- 징계의결 요구 여부 또는 추가 조사 필요 여부: 관련자 진술과 승인 기록을 추가 확인한 뒤 징계의결 요구 여부를 검토할 필요가 있다.",
                                "citations": ["law:fact-001"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "attachments",
                                "title": "첨부자료 목록",
                                "text": "- CCTV 캡처본\n- 창고 출입기록",
                                "citations": ["form:fact-summary-template"],
                                "open_issues": [],
                            },
                        ],
                        "compiled_text": "개요\n본 보고서는 창고 자산 반출 의혹 조사 사건에 대한 사실관계와 관련 자료를 확인하기 위해 작성하였다.",
                    },
                    "checklist_missing_info": [],
                    "evidence_report": {
                        "totals_by_type": {"law": 1, "case": 0, "regulation": 1, "form": 1},
                        "used_evidence_ids": ["law:fact-001"],
                        "unused_evidence_ids": [],
                        "section_coverage": {"overview": ["law:fact-001"]},
                        "source_mode": "result",
                    },
                    "warnings": [],
                }
            )

        if request.constraints.prompt_profile == "attendance_notice":
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
                                "open_issues": ["출석 일시", "출석 장소", "징계위원회명", "통지일", "대상자 주소"],
                            },
                            {
                                "section_id": "appearance_reason",
                                "title": "출석 이유",
                                "text": "창고 출입기록과 CCTV 확인 결과 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다.",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "appearance_datetime",
                                "title": "출석 일시",
                                "text": "- 자료상 명확하지 않음",
                                "citations": ["form:attendance-notice-template"],
                                "open_issues": ["출석 일시"],
                            },
                            {
                                "section_id": "appearance_location",
                                "title": "출석 장소",
                                "text": "- 자료상 명확하지 않음",
                                "citations": ["form:attendance-notice-template"],
                                "open_issues": ["출석 장소"],
                            },
                            {
                                "section_id": "notes",
                                "title": "유의사항",
                                "text": "- 출석하여 진술하기를 원하지 않는 경우 진술권 포기서를 제출할 수 있음\n- 서면진술을 원할 경우 지정 기한까지 진술서를 제출할 수 있음\n- 정당한 사유 없이 불출석하고 서면진술도 없으면 진술 의사가 없는 것으로 보고 처리될 수 있음\n- 필요 시 소명자료 또는 증빙자료를 제출할 수 있음",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "notice_statement",
                                "title": "통지 문구",
                                "text": "- 관련 규정에 따라 위와 같이 귀하의 출석을 통지합니다.",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "sender",
                                "title": "발신",
                                "text": "- 통지일: 자료상 명확하지 않음\n- 징계위원회명: 자료상 명확하지 않음\n- 위원회 청인 또는 직인 표시",
                                "citations": ["form:attendance-notice-template"],
                                "open_issues": ["징계위원회명", "통지일"],
                            },
                            {
                                "section_id": "recipient",
                                "title": "수신",
                                "text": "- 귀하",
                                "citations": ["form:attendance-notice-template"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "appendix",
                                "title": "별첨",
                                "text": "- 필요 시 진술권 포기서 양식",
                                "citations": ["form:attendance-notice-template"],
                                "open_issues": [],
                            },
                        ],
                        "compiled_text": "출석통지서\n인적사항\n- 성명: 최민수",
                    },
                    "checklist_missing_info": ["출석 일시", "출석 장소", "징계위원회명", "통지일", "대상자 주소"],
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

        if request.constraints.prompt_profile == "committee_reference":
            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "disciplinary_opinion",
                        "title": "징계위원회 참고자료",
                        "sections": [
                            {
                                "section_id": "case_overview",
                                "title": "사건 개요",
                                "text": "- 사건명: 창고 자산 반출 의혹 조사\n- 심의 일시: 자료상 명확하지 않음\n- 심의 대상자: 병장 최민수\n- 사건 요약: 정식 승인 없이 장비 상자가 외부 적재 구역으로 이동한 정황이 확인되었습니다.",
                                "citations": ["form:committee-reference-template"],
                                "open_issues": ["심의 일시"],
                            },
                            {
                                "section_id": "subject_profile",
                                "title": "심의대상자 인적사항",
                                "text": "- 소속: 자료상 명확하지 않음\n- 직위/직급: 병장\n- 성명: 최민수",
                                "citations": ["form:committee-reference-template"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "fact_summary",
                                "title": "징계혐의 사실 요약",
                                "text": "- 사실관계 1: 2026-03-19 09:00경 제3보급대대 창고동에서 장비 상자 2개 이동 정황이 확인되었다.\n- 사실관계 2: 정식 반출 절차 준수 여부는 추가 확인이 필요하다.\n- 사실관계 3: 관련자 진술과 재물 관리대장 기록 사이에 차이가 있다.",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "issues",
                                "title": "주요 쟁점",
                                "text": "- 쟁점 1: 반출 승인 절차가 적법하게 진행되었는지 여부\n- 쟁점 2: 관련자 진술과 관리대장 기록이 일치하는지 여부\n- 쟁점 3: 실제 이동 행위자와 경위를 특정할 수 있는지 여부",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "evidence_summary",
                                "title": "증거자료 요약",
                                "text": "- 증거 1: CCTV 캡처본 - 장비 상자 이동 정황을 확인할 수 있음\n- 증거 2: 창고 출입기록 - 이동 시점과 출입 정황을 확인할 수 있음\n- 증거 3: 재물 관리대장 - 반출 절차 기록과의 대조가 필요함",
                                "citations": ["law:fact-001", "regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "statements",
                                "title": "당사자 진술 및 소명 요지",
                                "text": "- 대상자 진술 요지: 자료상 명확하지 않음\n- 참고인/관계인 진술 요지: 자료상 명확하지 않음\n- 다툼이 있는 부분: 관련자 진술과 재물 관리대장 기록 사이 차이",
                                "citations": ["case:disciplinary-reference"],
                                "open_issues": ["대상자 진술"],
                            },
                            {
                                "section_id": "mitigating_aggravating",
                                "title": "정상참작 사항",
                                "text": "- 유리한 정상: 자료상 명확하지 않음\n- 불리한 정상: 승인 절차 위반 여부가 해소되지 않았고 관련 자료가 상충함",
                                "citations": ["case:disciplinary-reference"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "applicable_rules",
                                "title": "적용 가능 규정",
                                "text": "- 관련 법령/규정: 군인 징계령, 군인 징계령 시행규칙\n- 검토 포인트: 승인 절차 준수 여부, 규정 위반 성립 여부, 양정 판단 시 조직 영향",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "judgment_points",
                                "title": "위원회 판단 포인트",
                                "text": "- 사실인정 포인트: 장비 상자 이동 정황과 승인 기록의 존재 여부\n- 양정 판단 포인트: 위반 정도, 행위자의 역할, 반복성 여부\n- 추가 확인 필요 사항: 심의 일시, 대상자 진술, 참고인 진술",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": ["심의 일시", "대상자 진술", "참고인 진술"],
                            },
                            {
                                "section_id": "attachments",
                                "title": "첨부자료 목록",
                                "text": "- CCTV 캡처본\n- 창고 출입기록\n- 재물 관리대장",
                                "citations": ["form:committee-reference-template"],
                                "open_issues": [],
                            },
                        ],
                        "compiled_text": "징계위원회 참고자료\n사건 개요\n- 사건명: 창고 자산 반출 의혹 조사",
                    },
                    "checklist_missing_info": ["심의 일시", "대상자 진술", "참고인 진술"],
                    "evidence_report": {
                        "totals_by_type": {"law": 1, "case": 1, "regulation": 2, "form": 1},
                        "used_evidence_ids": ["regulation:discipline-guideline"],
                        "unused_evidence_ids": [],
                        "section_coverage": {"case_overview": ["form:committee-reference-template"]},
                        "source_mode": "result",
                    },
                    "warnings": [],
                }
            )

        if request.constraints.prompt_profile == "disciplinary_resolution":
            return DocumentGenerationResponse.model_validate(
                {
                    "draft": {
                        "doc_type": "disciplinary_opinion",
                        "title": "징계의결서",
                        "sections": [
                            {
                                "section_id": "subject_profile",
                                "title": "징계혐의자 인적사항",
                                "text": "- 소속: 자료상 명확하지 않음\n- 직위(직급): 병장\n- 성명: 최민수",
                                "citations": ["form:disciplinary-resolution-template"],
                                "open_issues": [],
                            },
                            {
                                "section_id": "decision_order",
                                "title": "의결주문",
                                "text": "- 자료상 명확하지 않음",
                                "citations": ["form:disciplinary-resolution-template"],
                                "open_issues": ["최종 의결결론"],
                            },
                            {
                                "section_id": "reasoning",
                                "title": "이유",
                                "text": "가. 인정되는 사실\n창고 출입기록과 CCTV 확인 결과 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었다.\n나. 증거의 판단\nCCTV 캡처본과 창고 출입기록은 사실관계 판단의 기초자료로 볼 수 있다.\n다. 적용 규정\n군인 징계령 및 관련 내부규정을 검토할 필요가 있다.\n라. 양정 판단\n- 비위의 정도: 자료상 명확하지 않음.\n- 고의/과실: 자료상 명확하지 않음.\n- 조직 영향: 절차 위반이 조직 운영에 미친 영향을 추가 검토할 필요가 있다.\n- 유리한 정상: 자료상 명확하지 않음.\n- 불리한 정상: 관련자 진술과 기록자료 사이 차이가 있다.",
                                "citations": ["regulation:discipline-guideline"],
                                "open_issues": ["정상참작 또는 가중사유"],
                            },
                            {
                                "section_id": "decision_date",
                                "title": "의결일자",
                                "text": "- 의결일자: 자료상 명확하지 않음",
                                "citations": ["form:disciplinary-resolution-template"],
                                "open_issues": ["의결일자"],
                            },
                            {
                                "section_id": "committee_name",
                                "title": "징계위원회명",
                                "text": "- 징계위원회명: 자료상 명확하지 않음",
                                "citations": ["form:disciplinary-resolution-template"],
                                "open_issues": ["징계위원회명"],
                            },
                            {
                                "section_id": "committee_members",
                                "title": "위원장 및 위원 표시",
                                "text": "- 위원장 및 위원 표시: 자료상 명확하지 않음",
                                "citations": ["form:disciplinary-resolution-template"],
                                "open_issues": ["위원장 및 위원 표시"],
                            },
                        ],
                        "compiled_text": "징계의결서\n징계혐의자 인적사항\n- 소속: 자료상 명확하지 않음",
                    },
                    "checklist_missing_info": ["최종 의결결론", "의결일자", "징계위원회명", "위원장 및 위원 표시", "정상참작 또는 가중사유"],
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

        return DocumentGenerationResponse.model_validate(
            {
                "draft": {
                    "doc_type": "disciplinary_opinion",
                    "title": "징계 의견서",
                    "sections": [
                        {
                            "section_id": "violation_summary",
                            "title": "위반행위 요지",
                            "text": "stub disciplinary opinion 본문입니다. 위반행위 요지와 징계 검토 포인트를 정리했습니다.",
                            "citations": ["regulation:discipline-guideline"],
                            "open_issues": [],
                        },
                        {
                            "section_id": "applicable_rules",
                            "title": "적용 규정",
                            "text": "군인 징계령 시행규칙과 징계 양정 검토 기준을 근거로 적용 규정을 정리했습니다.",
                            "citations": ["regulation:discipline-guideline", "form:disciplinary-opinion-template"],
                            "open_issues": [],
                        },
                    ],
                    "compiled_text": "위반행위 요지\nstub disciplinary opinion 본문입니다.\n\n적용 규정\n군인 징계령 시행규칙과 징계 양정 검토 기준을 근거로 적용 규정을 정리했습니다.",
                },
                "checklist_missing_info": [],
                "evidence_report": {
                    "totals_by_type": {"law": 0, "case": 1, "regulation": 2, "form": 1},
                    "used_evidence_ids": ["regulation:discipline-guideline"],
                    "unused_evidence_ids": [],
                    "section_coverage": {"violation_summary": ["regulation:discipline-guideline"]},
                    "source_mode": "result",
                },
                "warnings": [
                    {
                        "code": "tone-check",
                        "severity": "warning",
                        "message": "최종 의결 전까지는 단정 표현을 피하는 것이 좋습니다.",
                        "section_id": "opinion",
                        "patch": None,
                    }
                ],
            }
        )


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
    assert payload["workflowStages"][0]["id"] == "case_registration"
    assert payload["workflowStages"][1]["status"] == "completed"
    assert payload["workflowStages"][2]["status"] == "active"
    assert payload["workflowStages"][3]["status"] == "completed"
    assert payload["workflowStages"][4]["status"] == "active"
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
    assert payload["title"] == "위원회 참고 자료"
    assert payload["legalBasis"][0]["id"] == "lb-003"
    assert payload["legalBasis"][0]["lawName"] == "군인 징계령"
    assert payload["legalBasis"][0]["article"] == "제9조"
    assert payload["previousDocumentId"] == "doc-018"
    assert payload["nextDocumentId"] == "doc-020"
    assert payload["questions"][0]["id"] == "question-005"


def test_create_disciplinary_case_returns_frontend_ready_case_detail(
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
    assert payload["documentCount"] == 4
    assert payload["openReviewCount"] == 0
    assert payload["documents"][0]["title"] == "사실결과조사보고"
    assert payload["documents"][0]["status"] == "completed"
    assert payload["documents"][0]["content"].startswith("1. 개요")
    assert "2. 징계혐의자 인적사항" in payload["documents"][0]["content"]
    assert "- 소속: 자료상 명확하지 않음" in payload["documents"][0]["content"]
    assert "8. 건의" in payload["documents"][0]["content"]
    assert payload["documents"][1]["title"] == "출석통지서"
    assert payload["documents"][1]["status"] == "completed"
    assert payload["documents"][1]["content"].startswith("제목: 출석통지서")
    assert "누락정보" in payload["documents"][1]["content"]
    assert "1. 인적사항" in payload["documents"][1]["content"]
    assert payload["documents"][2]["title"] == "위원회 참고 자료"
    assert payload["documents"][2]["status"] == "generating"
    assert payload["documents"][2]["content"].startswith("제목: 징계위원회 참고자료")
    assert "1. 사건 개요" in payload["documents"][2]["content"]
    assert "9. 위원회 판단 포인트" in payload["documents"][2]["content"]
    assert payload["documents"][3]["title"] == "징계의결서/처분서"
    assert payload["documents"][3]["status"] == "pending"
    assert payload["documents"][3]["content"].startswith("제목: 징계의결서")
    assert "2. 의결주문" in payload["documents"][3]["content"]
    assert "3. 이유" in payload["documents"][3]["content"]
    assert payload["documents"][0]["legalBasisIds"]
    assert payload["workflowStages"][3]["status"] == "active"
    assert payload["workflowStages"][4]["status"] == "pending"
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
    assert documents[0]["legalBasisIds"] == ["lb-003", "lb-005"]
    assert set(stub_case_document_generation_service.calls) == {
        ("fact_summary", "fact_finding_report"),
        ("fact_summary", "attendance_notice"),
        ("disciplinary_opinion", "committee_reference"),
        ("disciplinary_opinion", "disciplinary_resolution"),
    }


def test_submit_document_review_updates_document_and_case_review_counts() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/cases/case-005/documents/doc-020/reviews",
            json={
                "title": "위원회 의결 문안 보완",
                "description": "최종 처분 집행 일정과 통보 대상을 문안에 더 분명하게 적어 주세요.",
            },
        )
        case_response = client.get("/api/cases/case-005")

    assert response.status_code == 200
    assert case_response.status_code == 200

    payload = response.json()
    case_payload = case_response.json()

    assert payload["id"] == "doc-020"
    assert payload["status"] == "generating"
    assert payload["reviewHistory"][0]["status"] == "open"
    assert payload["reviewHistory"][0]["title"] == "위원회 의결 문안 보완"
    assert case_payload["openReviewCount"] == 2
    assert case_payload["workflowStages"][4]["status"] == "active"


def test_resolve_document_review_updates_status_version_and_timeline() -> None:
    with TestClient(app) as client:
        create_review_response = client.post(
            "/api/cases/case-005/documents/doc-020/reviews",
            json={
                "title": "위원회 의결 문안 보완",
                "description": "최종 처분 집행 일정과 통보 대상을 문안에 더 분명하게 적어 주세요.",
            },
        )
        review_id = create_review_response.json()["reviewHistory"][0]["id"]
        response = client.post(f"/api/cases/case-005/documents/doc-020/reviews/{review_id}/resolve")
        case_response = client.get("/api/cases/case-005")

    assert create_review_response.status_code == 200
    assert response.status_code == 200
    assert case_response.status_code == 200

    payload = response.json()
    case_payload = case_response.json()

    assert payload["status"] == "completed"
    assert payload["versionHistory"][0]["note"] == "위원회 의결 문안 보완 피드백을 반영해 문서를 수정했습니다."
    assert payload["reviewHistory"][0]["status"] == "resolved"
    assert case_payload["openReviewCount"] == 1


def test_submit_question_answer_updates_case_status_document_history_and_review_counts() -> None:
    answer = "재발 방지 교육은 2026년 3월 21일 전 부서원을 대상으로 실시하고, 외부 장비 연결은 사전 승인 체크리스트를 통과한 경우에만 허용하며, 지휘관은 주간 점검 결과를 직접 확인하기로 했습니다."

    with TestClient(app) as client:
        response = client.post(
            "/api/questions/question-005/answer",
            json={"answer": answer},
        )
        document_response = client.get("/api/cases/case-005/documents/doc-019")

    assert response.status_code == 200
    assert document_response.status_code == 200

    payload = response.json()
    document_payload = document_response.json()

    assert payload["status"] == "in_progress"
    assert payload["activeQuestionCount"] == 0
    assert payload["openReviewCount"] == 1
    assert payload["questions"][0]["status"] == "answered"
    assert payload["questions"][0]["answer"] == answer
    assert document_payload["status"] == "generating"
    assert document_payload["versionHistory"][0]["note"] == "추가 질문 답변이 반영되어 초안이 갱신되었습니다."
    assert document_payload["reviewHistory"][0]["status"] == "resolved"
    assert any(item["status"] == "open" for item in document_payload["reviewHistory"])


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
