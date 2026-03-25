from schemas import ObservationContext
from graph import InMemoryGraphStore
from ingestion import CanonicalLawTransformer, IngestionService
from search import InMemoryTextSearchStore
from storage import InMemoryCorpusRepository, InMemoryVectorStore


class DummyApiClient:
    async def aclose(self) -> None:  # pragma: no cover - interface completeness
        return None


def sample_payloads() -> tuple[dict, dict, list[dict], dict]:
    list_payload = {
        "법령ID": "000001",
        "법령명한글": "테스트법",
        "소관부처명": "테스트부",
    }
    body_payload = {
        "법령ID": "000001",
        "법령명한글": "테스트법",
        "소관부처명": "테스트부",
        "법령구분명": "법률",
        "공포번호": "12345",
        "공포일자": "20240101",
        "시행일자": "20240115",
        "현행연혁코드": "curr",
        "조문번호": "000100",
    }
    article_payloads = [
        {
            "조문번호": "000100",
            "조문제목": "총칙",
            "조문내용": "다른 법률에 따른다. 제2조를 준용한다.",
            "항번호": "1",
            "항내용": "항 내용",
            "호번호": "1",
            "호내용": "호 내용",
            "목번호": "가",
            "목내용": "목 내용",
        },
        {
            "조문번호": "000200",
            "조문제목": "정의",
            "조문내용": "「형법」을 참조한다.",
        },
    ]
    history_payload = {"제개정구분명": "일부개정", "공포일자": "20240101"}
    return list_payload, body_payload, article_payloads, history_payload


def build_service() -> tuple[IngestionService, InMemoryCorpusRepository]:
    repository = InMemoryCorpusRepository()
    service = IngestionService(
        api_client=DummyApiClient(),  # type: ignore[arg-type]
        repository=repository,
        graph_store=InMemoryGraphStore(),
        text_search_store=InMemoryTextSearchStore(),
        vector_store=InMemoryVectorStore(),
        transformer=CanonicalLawTransformer(),
    )
    return service, repository


def test_reingestion_is_idempotent() -> None:
    service, repository = build_service()
    context = ObservationContext(request_id="req-idem", corpus_version="v1", ingestion_run_id="ing-1")
    list_payload, body_payload, article_payloads, history_payload = sample_payloads()

    service.ingest_from_payloads(
        list_payload=list_payload,
        body_payload=body_payload,
        article_payloads=article_payloads,
        history_payload=history_payload,
        context=context,
    )
    first_counts = repository.count_entities()

    service.ingest_from_payloads(
        list_payload=list_payload,
        body_payload=body_payload,
        article_payloads=article_payloads,
        history_payload=history_payload,
        context=context,
    )
    second_counts = repository.count_entities()

    assert first_counts == second_counts
    assert second_counts["laws"] == 1
    assert second_counts["versions"] == 1
    assert second_counts["units"] >= 2
