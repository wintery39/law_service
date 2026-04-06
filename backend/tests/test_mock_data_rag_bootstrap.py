from __future__ import annotations

from fastapi.testclient import TestClient

from main import app, container
from schemas import CaseDocumentGenerationRequest, ObservationContext, build_document_generation_request
from tests.fake_gemini import build_fake_document_service


def test_mock_data_status_endpoint_reports_loaded_demo_corpus() -> None:
    with TestClient(app) as client:
        response = client.get("/ingestions/mock-data/status")

    assert response.status_code == 200
    payload = response.json()
    assert "military_discipline_rule_demo.json" in payload["loaded_files"]
    assert "군인 징계령 시행규칙" in payload["loaded_laws"]
    assert payload["ingested_units"] >= 16
    assert payload["ingested_references"] >= 1


def test_search_text_uses_mock_data_synonym_enrichment() -> None:
    with TestClient(app) as client:
        response = client.get("/search/text", params={"q": "갑질", "limit": 5})

    assert response.status_code == 200
    hits = response.json()["hits"]
    assert hits
    assert any("우월적 지위" in hit["snippet"] or "품위유지" in hit["snippet"] for hit in hits)


def test_related_articles_can_retrieve_mock_data_corpus() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/services/related-articles/find",
            json={
                "session_id": "mock-dataset-related-articles",
                "user_text": "병사가 생활관에서 상관의 명령을 거부해 징계가 문제입니다.",
                "as_of_date": "2026-03-01",
                "jurisdiction": "kr",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "result"
    assert payload["final"]
    assert any(item["law_name"] == "군인 징계령 시행규칙" for item in payload["final"])


async def test_document_generation_collects_mock_data_as_evidence() -> None:
    request = build_document_generation_request(
        CaseDocumentGenerationRequest(
            title="생활관 명령 거부 징계 검토",
            caseType="disciplinary",
            occurredAt="2026-03-20T10:00:00Z",
            location="생활관",
            author="중위 김수현",
            relatedPersons=["병사 김민준", "상관 이도현"],
            summary="병사가 상관의 정당한 명령을 거부해 징계 검토가 필요한 사안입니다.",
            details="생활관에서 병사가 상관의 정당한 명령을 거부했고 복무질서에 영향을 줄 수 있다는 보고가 접수되었습니다.",
        )
    )

    service = build_fake_document_service(
        container.related_article_service,
        container.repository,
        container.text_search_store,
    )

    try:
        response, evidence_pack = await service.generate_with_artifacts(
            request,
            ObservationContext(
                request_id="mock-data-doc-generation",
                corpus_version="mock-data",
                ingestion_run_id="mock-data-doc-generation",
            ),
        )
    finally:
        await service.aclose()

    assert response.evidence_report.totals_by_type["regulation"] >= 1 or response.evidence_report.totals_by_type["law"] >= 1
    assert any(item.title.startswith("군인 징계령 시행규칙") for item in evidence_pack.laws + evidence_pack.regulations)
