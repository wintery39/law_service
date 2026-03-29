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
from schemas import DocumentGenerationRequest, DocumentIntent
from tests.test_related_article_service import build_context, seed_related_article_fixture


def build_document_service() -> DocumentGenerationService:
    fixture = seed_related_article_fixture()
    return DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        settings=DocumentGenerationSettings(),
    )


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


def test_generate_document_endpoint_accepts_frontend_case_payload() -> None:
    fixture = seed_related_article_fixture()
    document_service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        settings=DocumentGenerationSettings(),
    )
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
    document_service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        settings=DocumentGenerationSettings(),
    )
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
