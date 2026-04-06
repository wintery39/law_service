from __future__ import annotations

from datetime import date
import json

import pytest
from fastapi.testclient import TestClient
import httpx
from starlette.websockets import WebSocketDisconnect

from documents import (
    DocumentGenerationService,
    DocumentGenerationSettings,
    EvidenceCollector,
    GeminiDocumentGenerator,
    GeminiGenerationSettings,
    InProcessRelatedArticlesClient,
)
from main import app, container
from schemas import DocumentConstraints, DocumentGenerationRequest, DocumentIntent
from tests.fake_gemini import build_fake_document_service
from tests.test_related_article_service import build_context, seed_related_article_fixture


def build_document_service() -> DocumentGenerationService:
    fixture = seed_related_article_fixture()
    return build_fake_document_service(fixture.service, fixture.repository, fixture.text_search_store)


async def test_generate_fact_summary_document() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-fact-summary",
            user_intent=DocumentIntent(doc_type="사실관계 정리서"),
            user_text="행정청이 민원인에게 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
            as_of_date=date(2024, 3, 1),
            jurisdiction="kr",
        ),
        build_context(),
    )

    section_ids = [section.section_id for section in response.draft.sections]
    assert response.draft.doc_type == "fact_summary"
    assert response.draft.title == "사실관계 정리서"
    assert section_ids == ["issue_summary", "chronology", "legal_points", "open_points"]
    assert response.evidence_report.totals_by_type["law"] >= 1
    assert response.evidence_report.totals_by_type["form"] == 1
    assert "law:" in response.evidence_report.used_evidence_ids[0] or response.evidence_report.used_evidence_ids
    assert any(section.citations for section in response.draft.sections[:3])


async def test_generate_fact_finding_report_prompt_profile_uses_specialized_sections() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-fact-finding-report",
            user_intent=DocumentIntent(doc_type="fact_summary"),
            user_text="창고 출입기록과 CCTV 확인 결과 장비 상자 이동 정황이 확인되었고 승인 여부는 추가 확인이 필요합니다.",
            as_of_date=date(2024, 3, 1),
            jurisdiction="kr",
            constraints=DocumentConstraints(prompt_profile="fact_finding_report"),
        ),
        build_context(),
    )

    section_ids = [section.section_id for section in response.draft.sections]
    assert response.draft.doc_type == "fact_summary"
    assert response.draft.title == "사실결과조사보고"
    assert section_ids == [
        "overview",
        "subject_profile",
        "allegations",
        "findings",
        "evidence_summary",
        "mitigating_aggravating",
        "integrated_opinion",
        "recommendation",
        "attachments",
    ]
    subject_profile = next(section for section in response.draft.sections if section.section_id == "subject_profile")
    assert "- 소속:" in subject_profile.text
    assert "- 사건명:" in subject_profile.text


async def test_generate_attendance_notice_prompt_profile_uses_specialized_sections() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-attendance-notice",
            user_intent=DocumentIntent(doc_type="fact_summary"),
            user_text=(
                "사건 제목: 창고 자산 반출 의혹 조사\n"
                "사건 유형: 징계\n"
                "발생 일시: 2026-03-19T09:00:00+00:00\n"
                "발생 장소: 제3보급대대 창고동\n"
                "작성자: 대위 홍길동\n"
                "관련자: 병장 최민수\n"
                "사건 개요: 정식 승인 없이 장비 상자가 이동한 정황이 확인되었습니다.\n"
                "상세 사실관계: 창고 출입기록과 CCTV 확인 결과 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다.\n"
            ),
            as_of_date=date(2026, 3, 19),
            jurisdiction="kr",
            constraints=DocumentConstraints(prompt_profile="attendance_notice"),
        ),
        build_context(),
    )

    section_ids = [section.section_id for section in response.draft.sections]
    assert response.draft.doc_type == "fact_summary"
    assert response.draft.title == "출석통지서"
    assert section_ids == [
        "personal_info",
        "appearance_reason",
        "appearance_datetime",
        "appearance_location",
        "notes",
        "notice_statement",
        "sender",
        "recipient",
        "appendix",
    ]
    personal_info = next(section for section in response.draft.sections if section.section_id == "personal_info")
    notes = next(section for section in response.draft.sections if section.section_id == "notes")
    assert "- 성명: 최민수" in personal_info.text
    assert "- 직위(직급): 병장" in personal_info.text
    assert "진술권 포기서를 제출할 수 있음" in notes.text


async def test_generate_committee_reference_prompt_profile_uses_specialized_sections() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-committee-reference",
            user_intent=DocumentIntent(doc_type="disciplinary_opinion"),
            user_text=(
                "사건 제목: 창고 자산 반출 의혹 조사\n"
                "사건 유형: 징계\n"
                "발생 일시: 2026-03-19T09:00:00+00:00\n"
                "발생 장소: 제3보급대대 창고동\n"
                "작성자: 대위 홍길동\n"
                "관련자: 병장 최민수\n"
                "사건 개요: 정식 승인 없이 장비 상자가 이동한 정황이 확인되었습니다.\n"
                "상세 사실관계: 창고 출입기록과 CCTV 확인 결과 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다. 관련자 진술과 재물 관리대장 사이에 차이가 있어 추가 확인이 진행 중입니다.\n"
                "첨부자료 요약: CCTV 캡처본과 창고 출입기록이 첨부되었습니다.\n"
            ),
            as_of_date=date(2026, 3, 19),
            jurisdiction="kr",
            constraints=DocumentConstraints(prompt_profile="committee_reference"),
        ),
        build_context(),
    )

    section_ids = [section.section_id for section in response.draft.sections]
    assert response.draft.doc_type == "disciplinary_opinion"
    assert response.draft.title == "징계위원회 참고자료"
    assert section_ids == [
        "case_overview",
        "subject_profile",
        "fact_summary",
        "issues",
        "evidence_summary",
        "statements",
        "mitigating_aggravating",
        "applicable_rules",
        "judgment_points",
        "attachments",
    ]
    case_overview = next(section for section in response.draft.sections if section.section_id == "case_overview")
    judgment_points = next(section for section in response.draft.sections if section.section_id == "judgment_points")
    assert case_overview.text.startswith("- 사건명:")
    assert "\n- 심의 일시:" in case_overview.text
    assert "- 추가 확인 필요 사항:" in judgment_points.text


async def test_generate_disciplinary_resolution_prompt_profile_uses_specialized_sections() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-disciplinary-resolution",
            user_intent=DocumentIntent(doc_type="disciplinary_opinion"),
            user_text=(
                "사건 제목: 창고 자산 반출 의혹 조사\n"
                "사건 유형: 징계\n"
                "발생 일시: 2026-03-19T09:00:00+00:00\n"
                "발생 장소: 제3보급대대 창고동\n"
                "작성자: 대위 홍길동\n"
                "관련자: 병장 최민수\n"
                "사건 개요: 정식 승인 없이 장비 상자가 이동한 정황이 확인되었습니다.\n"
                "상세 사실관계: 창고 출입기록과 CCTV 확인 결과 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다. 관련자 진술과 재물 관리대장 사이에 차이가 있어 추가 확인이 진행 중입니다.\n"
                "첨부자료 요약: CCTV 캡처본과 창고 출입기록이 첨부되었습니다.\n"
            ),
            as_of_date=date(2026, 3, 19),
            jurisdiction="kr",
            constraints=DocumentConstraints(prompt_profile="disciplinary_resolution"),
        ),
        build_context(),
    )

    section_ids = [section.section_id for section in response.draft.sections]
    assert response.draft.doc_type == "disciplinary_opinion"
    assert response.draft.title == "징계의결서"
    assert section_ids == [
        "subject_profile",
        "decision_order",
        "reasoning",
        "decision_date",
        "committee_name",
        "committee_members",
    ]
    subject_profile = next(section for section in response.draft.sections if section.section_id == "subject_profile")
    reasoning = next(section for section in response.draft.sections if section.section_id == "reasoning")
    assert "- 소속:" in subject_profile.text
    assert "- 직위(직급):" in subject_profile.text
    assert "가. 인정되는 사실" in reasoning.text
    assert "다. 적용 규정" in reasoning.text
    assert "- 비위의 정도:" in reasoning.text


async def test_generate_disciplinary_resolution_parses_name_first_related_person() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-disciplinary-resolution-name-first",
            user_intent=DocumentIntent(doc_type="disciplinary_opinion"),
            user_text=(
                "사건 제목: 창고 자산 반출 의혹 조사\n"
                "사건 유형: 징계\n"
                "발생 일시: 2026-03-19T09:00:00+00:00\n"
                "발생 장소: 제3보급대대 창고동\n"
                "작성자: 대위 홍길동\n"
                "관련자: 최민수 병장\n"
                "사건 개요: 정식 승인 없이 장비 상자가 이동한 정황이 확인되었습니다.\n"
                "상세 사실관계: 창고 출입기록과 CCTV 확인 결과 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다.\n"
            ),
            as_of_date=date(2026, 3, 19),
            jurisdiction="kr",
            constraints=DocumentConstraints(prompt_profile="disciplinary_resolution"),
        ),
        build_context(),
    )

    subject_profile = next(section for section in response.draft.sections if section.section_id == "subject_profile")
    assert "- 직위(직급): 병장" in subject_profile.text
    assert "- 성명: 최민수" in subject_profile.text


async def test_generate_disciplinary_opinion_document() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-disciplinary",
            user_intent=DocumentIntent(doc_type="징계 의견서"),
            user_text="지휘관의 명령을 거부한 병사에 대한 징계 의견서가 필요합니다.",
            as_of_date=date(2024, 3, 1),
            jurisdiction="kr",
        ),
        build_context(),
    )

    section_by_id = {section.section_id: section for section in response.draft.sections}
    assert response.draft.doc_type == "disciplinary_opinion"
    assert response.evidence_report.totals_by_type["regulation"] >= 1
    assert response.evidence_report.totals_by_type["form"] == 1
    assert "applicable_rules" in section_by_id
    assert section_by_id["applicable_rules"].citations
    assert "징계" in response.draft.compiled_text


async def test_generate_defense_draft_document() -> None:
    service = build_document_service()
    response = await service.generate(
        DocumentGenerationRequest(
            session_id="doc-defense",
            user_intent=DocumentIntent(doc_type="항변서 초안"),
            user_text="병사가 생활관에서 폭행했다는 신고가 있었지만 피해자 진술이 일치하지 않습니다.",
            as_of_date=date(2024, 3, 1),
            jurisdiction="kr",
        ),
        build_context(),
    )

    section_by_id = {section.section_id: section for section in response.draft.sections}
    assert response.draft.doc_type == "defense_draft"
    assert response.evidence_report.totals_by_type["case"] >= 1
    assert response.evidence_report.totals_by_type["form"] == 1
    assert "arguments" in section_by_id
    assert section_by_id["arguments"].citations
    assert any(warning.patch is not None for warning in response.warnings) or response.warnings == []


async def test_generate_document_uses_gemini_when_configured() -> None:
    fixture = seed_related_article_fixture()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        assert request.headers["x-goog-api-key"] == "test-gemini-key"

        payload = json.loads(request.content.decode("utf-8"))
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["responseJsonSchema"]["properties"]["sections"]["minItems"] == 4

        generated = {
            "sections": [
                {
                    "section_id": "violation_summary",
                    "text": "확인된 자료에 따르면 지휘 명령 거부 정황이 존재하며 복무질서에 직접적인 영향이 있었다는 점이 우선 검토 대상입니다. 현재 단계에서는 관련 보고와 진술을 대조해 위반행위의 구체적 범위를 확정할 필요가 있습니다.",
                    "open_issues": ["거부 경위 추가 확인"],
                },
                {
                    "section_id": "applicable_rules",
                    "text": "군 복무규율과 징계 관련 기준을 중심으로 적용 가능 규정을 정리할 수 있습니다. 특히 명령 이행 의무와 지휘체계 유지 필요성이 핵심 검토 포인트입니다.",
                    "open_issues": [],
                },
                {
                    "section_id": "mitigation_aggravation",
                    "text": "반복성 여부와 상관 지휘체계에 미친 영향은 불리한 요소가 될 수 있습니다. 반면 경위 설명과 사후 태도는 정상참작 요소로 별도 확인이 필요합니다.",
                    "open_issues": ["반성 여부 확인"],
                },
                {
                    "section_id": "opinion",
                    "text": "현재 자료만으로도 징계 검토 필요성은 충분히 제기됩니다. 다만 최종 양정 판단 전에는 당시 명령의 구체성과 후속 조치 여부를 보강 조사하는 것이 적절합니다.",
                    "open_issues": [],
                },
            ]
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}]},
        )

    service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        gemini_generator=GeminiDocumentGenerator(
            settings=GeminiGenerationSettings(
                api_key="test-gemini-key",
                model_name="gemini-test",
                base_url="https://gemini.example.test/v1beta",
            ),
            transport=httpx.MockTransport(handler),
        ),
        settings=DocumentGenerationSettings(),
    )

    try:
        response = await service.generate(
            DocumentGenerationRequest(
                session_id="doc-gemini",
                user_intent=DocumentIntent(doc_type="징계 의견서"),
                user_text="지휘관의 명령을 거부한 병사에 대한 징계 의견서가 필요합니다.",
                as_of_date=date(2024, 3, 1),
                jurisdiction="kr",
            ),
            build_context(),
        )
    finally:
        await service.aclose()

    assert response.draft.doc_type == "disciplinary_opinion"
    assert response.draft.sections[0].section_id == "violation_summary"
    assert response.draft.sections[0].text.startswith("확인된 자료에 따르면")
    assert response.draft.sections[0].citations
    assert "징계 검토 필요성은 충분히 제기됩니다." in response.draft.compiled_text


async def test_generate_fact_finding_report_retries_invalid_json_and_normalizes_bullets() -> None:
    fixture = seed_related_article_fixture()
    responses = [
        httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": '{"sections":[{"section_id":"overview","text":"잘린 응답","open_issues":[]}'
                                }
                            ]
                        },
                    }
                ]
            },
        ),
        httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "sections": [
                                                {
                                                    "section_id": "overview",
                                                    "text": "제목: 사실결과조사보고\n본 조사는 현재 확보된 자료를 기준으로 장비 상자 이동 정황의 사실관계를 정리하기 위해 작성한다.",
                                                    "open_issues": ["사건 개시 일자"],
                                                },
                                                {
                                                    "section_id": "subject_profile",
                                                    "text": "2. 징계혐의자 인적사항\n- 소속: 자료상 명확하지 않음- 직위/직급: 병장- 성명: 최민수- 사건명: 창고 자산 반출 의혹 조사",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "allegations",
                                                    "text": "- 혐의사실 1: 2026-03-19 09:00경 창고에서 장비 상자 이동 정황이 확인되었다.- 혐의사실 2: 승인 여부는 자료상 명확하지 않다.",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "findings",
                                                    "text": "- 인정되는 사실: CCTV와 출입기록상 이동 정황이 확인된다.- 다툼이 있는 사항: 이동 경위와 승인 여부 진술이 일치하지 않는다.- 확인되지 않은 사항: 행위자 특정은 확인되지 않음.",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "evidence_summary",
                                                    "text": "출력 형식\n- 증거 1: CCTV 캡처본- 증거 2: 창고 출입기록- 각 증거로 확인되는 내용: 이동 시점과 출입 정황이 확인된다.",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "mitigating_aggravating",
                                                    "text": "- 유리한 정상: 자료상 명확하지 않음- 불리한 정상: 승인 여부가 미확정 상태다.",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "integrated_opinion",
                                                    "text": "현재 자료에 따르면 이동 정황은 확인되나 승인 여부는 추가 확인이 필요하다.",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "recommendation",
                                                    "text": "- 징계의결 요구 여부 또는 추가 조사 필요 여부: 승인 기록과 관련자 진술을 추가 확인할 필요가 있다.",
                                                    "open_issues": [],
                                                },
                                                {
                                                    "section_id": "attachments",
                                                    "text": "- CCTV 캡처본- 창고 출입기록",
                                                    "open_issues": [],
                                                },
                                            ]
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        ),
    ]
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        call_count += 1
        return responses[call_count - 1]

    service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        gemini_generator=GeminiDocumentGenerator(
            settings=GeminiGenerationSettings(
                api_key="test-gemini-key",
                model_name="gemini-test",
                base_url="https://gemini.example.test/v1beta",
            ),
            transport=httpx.MockTransport(handler),
        ),
        settings=DocumentGenerationSettings(generation_provider="gemini"),
    )

    try:
        response = await service.generate(
            DocumentGenerationRequest(
                session_id="doc-fact-finding-gemini",
                user_intent=DocumentIntent(doc_type="fact_summary"),
                user_text="창고 출입기록과 CCTV 확인 결과 장비 상자 이동 정황이 확인되었고 승인 여부는 추가 확인이 필요합니다.",
                as_of_date=date(2024, 3, 1),
                jurisdiction="kr",
                constraints=DocumentConstraints(prompt_profile="fact_finding_report"),
            ),
            build_context(),
        )
    finally:
        await service.aclose()

    assert call_count == 2
    subject_profile = next(section for section in response.draft.sections if section.section_id == "subject_profile")
    allegations = next(section for section in response.draft.sections if section.section_id == "allegations")
    evidence_summary = next(section for section in response.draft.sections if section.section_id == "evidence_summary")
    overview = next(section for section in response.draft.sections if section.section_id == "overview")
    assert not overview.text.startswith("제목:")
    assert subject_profile.text == (
        "- 소속: 자료상 명확하지 않음\n"
        "- 직위/직급: 병장\n"
        "- 성명: 최민수\n"
        "- 사건명: 창고 자산 반출 의혹 조사"
    )
    assert "2. 징계혐의자 인적사항" not in subject_profile.text
    assert "\n- 혐의사실 2:" in allegations.text
    assert "출력 형식" not in evidence_summary.text
    assert "\n- 각 증거로 확인되는 내용:" in evidence_summary.text


async def test_generate_fact_finding_report_fails_when_required_section_is_empty_after_normalization() -> None:
    fixture = seed_related_article_fixture()

    generated = {
        "sections": [
            {
                "section_id": "overview",
                "text": "본 조사는 현재 확보된 자료를 기준으로 장비 상자 이동 정황의 사실관계를 정리하기 위해 작성한다.",
                "open_issues": [],
            },
            {
                "section_id": "subject_profile",
                "text": "제목: 사실결과조사보고\n출력 형식\n추가 필요 정보",
                "open_issues": [],
            },
            {
                "section_id": "allegations",
                "text": "- 혐의사실 1: 2026-03-19 09:00경 창고에서 장비 상자 이동 정황이 확인되었다.\n- 혐의사실 2: 승인 여부는 자료상 명확하지 않다.",
                "open_issues": [],
            },
            {
                "section_id": "findings",
                "text": "- 인정되는 사실: CCTV와 출입기록상 이동 정황이 확인된다.\n- 다툼이 있는 사항: 이동 경위와 승인 여부 진술이 일치하지 않는다.\n- 확인되지 않은 사항: 행위자 특정은 확인되지 않음.",
                "open_issues": [],
            },
            {
                "section_id": "evidence_summary",
                "text": "- 증거 1: CCTV 캡처본\n- 증거 2: 창고 출입기록\n- 각 증거로 확인되는 내용: 이동 시점과 출입 정황이 확인된다.",
                "open_issues": [],
            },
            {
                "section_id": "mitigating_aggravating",
                "text": "- 유리한 정상: 자료상 명확하지 않음\n- 불리한 정상: 승인 여부가 미확정 상태다.",
                "open_issues": [],
            },
            {
                "section_id": "integrated_opinion",
                "text": "현재 자료에 따르면 이동 정황은 확인되나 승인 여부는 추가 확인이 필요하다.",
                "open_issues": [],
            },
            {
                "section_id": "recommendation",
                "text": "- 징계의결 요구 여부 또는 추가 조사 필요 여부: 승인 기록과 관련자 진술을 추가 확인할 필요가 있다.",
                "open_issues": [],
            },
            {
                "section_id": "attachments",
                "text": "- CCTV 캡처본\n- 창고 출입기록",
                "open_issues": [],
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}]},
        )

    service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        gemini_generator=GeminiDocumentGenerator(
            settings=GeminiGenerationSettings(
                api_key="test-gemini-key",
                model_name="gemini-test",
                base_url="https://gemini.example.test/v1beta",
            ),
            transport=httpx.MockTransport(handler),
        ),
        settings=DocumentGenerationSettings(generation_provider="gemini"),
    )

    try:
        with pytest.raises(RuntimeError, match="빈 섹션: subject_profile"):
            await service.generate(
                DocumentGenerationRequest(
                    session_id="doc-fact-finding-empty-section",
                    user_intent=DocumentIntent(doc_type="fact_summary"),
                    user_text=(
                        "사건 제목: 창고 자산 반출 의혹 조사\n"
                        "발생 일시: 2026-03-19T09:00:00+00:00\n"
                        "발생 장소: 제3보급대대 창고동\n"
                        "관련자: 병장 최민수\n"
                        "사건 개요: 장비 상자 이동 정황이 확인되었다.\n"
                        "상세 사실관계: 창고 출입기록과 CCTV 확인 결과 장비 상자 이동 정황이 확인되었다.\n"
                    ),
                    as_of_date=date(2026, 3, 19),
                    jurisdiction="kr",
                    constraints=DocumentConstraints(prompt_profile="fact_finding_report"),
                ),
                build_context(),
            )
    finally:
        await service.aclose()


def test_generate_document_endpoint_accepts_frontend_case_payload() -> None:
    fixture = seed_related_article_fixture()
    document_service = build_fake_document_service(fixture.service, fixture.repository, fixture.text_search_store)
    original_service = container.document_generation_service
    container.document_generation_service = document_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/services/documents/generate",
                headers={
                    "x-request-id": "req-doc-generate",
                    "x-corpus-version": "gold-v1",
                    "x-ingestion-run-id": "ing-doc-generate",
                },
                json={
                    "title": "창고 자산 반출 의혹 조사",
                    "caseType": "disciplinary",
                    "occurredAt": "2026-03-19T09:00:00Z",
                    "location": "제3보급대대 창고동",
                    "author": "대위 홍길동",
                    "relatedPersons": ["병장 최민수", "중사 이영호"],
                    "summary": "정식 승인 없이 장비 상자가 외부 적재 구역으로 이동한 정황이 확인되었습니다.",
                    "details": "창고 출입기록과 CCTV 확인 결과, 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다. 관련자 진술과 재물 관리대장 사이에 차이가 있어 추가 확인이 진행 중입니다.",
                },
            )
    finally:
        container.document_generation_service = original_service

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"]["doc_type"] == "disciplinary_opinion"
    assert payload["draft"]["title"] == "징계 의견서"
    assert payload["evidence_report"]["totals_by_type"]["form"] == 1


def test_document_generation_stream_endpoint() -> None:
    fixture = seed_related_article_fixture()
    document_service = build_fake_document_service(fixture.service, fixture.repository, fixture.text_search_store)
    original_service = container.document_generation_service
    container.document_generation_service = document_service

    try:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/services/documents/generate/stream",
                headers={
                    "x-request-id": "req-doc-stream",
                    "x-corpus-version": "gold-v1",
                    "x-ingestion-run-id": "ing-doc-stream",
                },
                json={
                    "title": "근무지 이탈 초기 검토",
                    "caseType": "disciplinary",
                    "occurredAt": "2026-03-19T09:00:00Z",
                    "location": "생활관",
                    "author": "중위 김수현",
                    "relatedPersons": ["병장 최민수"],
                    "summary": "상관 허가 없이 생활관을 이탈한 정황이 접수되었습니다.",
                    "details": "병사가 상관 허가 없이 생활관을 이탈했고 당시 근무 교대 시간이 겹쳐 복무 공백 우려가 있었다는 보고가 접수되었습니다.",
                },
            ) as response:
                lines = [line for line in response.iter_lines() if line]
    finally:
        container.document_generation_service = original_service

    assert response.status_code == 200
    assert any(line == "event: start" for line in lines)
    assert any(line == "event: section" for line in lines)
    assert any(line == "event: complete" for line in lines)
    assert any("징계 의견서" in line for line in lines if line.startswith("data: "))


def test_document_generation_stream_endpoint_emits_error_event() -> None:
    class FailingStreamService:
        async def stream(self, payload, context):
            if False:
                yield None
            raise RuntimeError("forced stream failure")

    original_service = container.document_generation_service
    container.document_generation_service = FailingStreamService()

    try:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/services/documents/generate/stream",
                json={
                    "title": "에러 재현용 사건",
                    "caseType": "disciplinary",
                    "occurredAt": "2026-03-19T09:00:00Z",
                    "location": "생활관",
                    "author": "중위 김수현",
                    "relatedPersons": ["병장 최민수"],
                    "summary": "상관 허가 없이 생활관을 이탈한 정황이 접수되었습니다.",
                    "details": "병사가 상관 허가 없이 생활관을 이탈했고 당시 근무 교대 시간이 겹쳐 복무 공백 우려가 있었다는 보고가 접수되었습니다.",
                },
            ) as response:
                lines = [line for line in response.iter_lines() if line]
    finally:
        container.document_generation_service = original_service

    assert response.status_code == 200
    assert any(line == "event: error" for line in lines)
    assert any("forced stream failure" in line for line in lines if line.startswith("data: "))


def test_document_generation_websocket_returns_error_event_for_invalid_payload() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/services/documents/generate/ws") as websocket:
            websocket.send_json({"session_id": "doc-websocket-invalid"})

            event = websocket.receive_json()

            assert event["event"] == "error"
            assert event["data"]["error_type"] == "ValidationError"

            with pytest.raises(WebSocketDisconnect):
                websocket.receive_json()
