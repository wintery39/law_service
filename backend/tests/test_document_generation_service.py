from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from documents import DocumentGenerationService, DocumentGenerationSettings, EvidenceCollector, InProcessRelatedArticlesClient
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
                    "session_id": "doc-stream",
                    "user_intent": {"doc_type": "징계 의견서"},
                    "user_text": "병사가 상관 허가 없이 근무지를 이탈했습니다.",
                    "as_of_date": "2024-03-01",
                    "jurisdiction": "kr",
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
