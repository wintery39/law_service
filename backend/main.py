from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
import json
from pathlib import Path
from uuid import uuid4

from case_management import (
    CaseWorkflowService,
    CaseCreatePayload,
    CaseDetail,
    CaseSummary,
    DashboardMetrics,
    DocumentDetail,
    DocumentRecord,
    LegalBasisEntry,
    QuestionAnswerPayload,
    QuestionRecord,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from documents import (
    DocumentGenerationService,
    DocumentGenerationSettings,
    EvidenceCollector,
    GeminiDocumentGenerator,
    GeminiGenerationSettings,
    InProcessRelatedArticlesClient,
    build_document_stream_error_event,
)
from graph import InMemoryGraphStore
from ingestion import (
    CanonicalLawTransformer,
    IngestionService,
    MockDataIngestionService,
    OpenLawApiClient,
    OpenLawApiSettings,
)
from schemas import (
    CaseDocumentGenerationRequest,
    ClarifyResponse,
    DocumentGenerationResponse,
    GraphNeighborsResponse,
    IngestLawRequest,
    IngestLawResponse,
    LawAggregateResponse,
    MockDataIngestionResponse,
    ObservationContext,
    RelatedArticleRequest,
    ResultResponse,
    TextSearchResponse,
    VersionSelectionResponse,
    build_document_generation_request,
)
from search import InMemoryTextSearchStore, RelatedArticleFinderService, RelatedArticleFinderSettings
from storage import InMemoryCorpusRepository, InMemoryVectorStore


class ServiceContainer:
    def __init__(self) -> None:
        self.repository = InMemoryCorpusRepository()
        self.graph_store = InMemoryGraphStore()
        self.text_search_store = InMemoryTextSearchStore()
        self.vector_store = InMemoryVectorStore()
        self.case_management_service = CaseWorkflowService()
        self.mock_data_ingestion_service = MockDataIngestionService(
            repository=self.repository,
            graph_store=self.graph_store,
            text_search_store=self.text_search_store,
            vector_store=self.vector_store,
            mock_data_dir=Path(__file__).resolve().parent / "mock_data",
        )
        self.mock_data_report = self.mock_data_ingestion_service.ingest_directory(
            ObservationContext(
                request_id="bootstrap-mock-data",
                corpus_version="mock-data",
                ingestion_run_id="bootstrap-mock-data",
            )
        )
        self.api_client = OpenLawApiClient(settings=OpenLawApiSettings())
        self.transformer = CanonicalLawTransformer()
        self.ingestion_service = IngestionService(
            api_client=self.api_client,
            repository=self.repository,
            graph_store=self.graph_store,
            text_search_store=self.text_search_store,
            vector_store=self.vector_store,
            transformer=self.transformer,
        )
        self.related_article_service = RelatedArticleFinderService(
            repository=self.repository,
            graph_store=self.graph_store,
            text_search_store=self.text_search_store,
            vector_store=self.vector_store,
            settings=RelatedArticleFinderSettings(),
        )
        self.document_generation_service = DocumentGenerationService(
            evidence_collector=EvidenceCollector(
                related_articles_client=InProcessRelatedArticlesClient(self.related_article_service),
                repository=self.repository,
                text_search_store=self.text_search_store,
            ),
            gemini_generator=GeminiDocumentGenerator(settings=GeminiGenerationSettings()),
            settings=DocumentGenerationSettings(),
        )

    async def aclose(self) -> None:
        await self.api_client.aclose()
        closer = getattr(self.document_generation_service, "aclose", None)
        if closer is not None:
            await closer()


container = ServiceContainer()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await container.aclose()


app = FastAPI(title="Law Corpus Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid4().hex)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


def build_context(
    request: Request,
    x_corpus_version: str | None = Header(default=None),
    x_ingestion_run_id: str | None = Header(default=None),
) -> ObservationContext:
    return ObservationContext(
        request_id=getattr(request.state, "request_id", uuid4().hex),
        corpus_version=x_corpus_version or "v1",
        ingestion_run_id=x_ingestion_run_id or f"ing-{uuid4().hex}",
    )


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "entity_counts": container.repository.count_entities(),
        "mock_data": container.mock_data_report.model_dump(mode="json"),
    }


@app.get("/api/cases", response_model=list[CaseSummary])
async def list_cases() -> list[CaseSummary]:
    return container.case_management_service.get_cases()


@app.get("/api/cases/metrics", response_model=DashboardMetrics)
async def get_case_metrics() -> DashboardMetrics:
    return container.case_management_service.get_case_metrics()


@app.get("/api/cases/{case_id}", response_model=CaseDetail)
async def get_case_detail(case_id: str) -> CaseDetail:
    try:
        return container.case_management_service.get_case_by_id(case_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/cases", response_model=CaseDetail, status_code=201)
async def create_case(payload: CaseCreatePayload) -> CaseDetail:
    try:
        return container.case_management_service.create_case(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/cases/{case_id}/documents", response_model=list[DocumentRecord])
async def get_case_documents(case_id: str) -> list[DocumentRecord]:
    try:
        return container.case_management_service.get_documents_by_case_id(case_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/cases/{case_id}/documents/{document_id}", response_model=DocumentDetail)
async def get_document_detail(case_id: str, document_id: str) -> DocumentDetail:
    try:
        return container.case_management_service.get_document_by_id(case_id, document_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/cases/{case_id}/questions", response_model=list[QuestionRecord])
async def get_case_questions(case_id: str) -> list[QuestionRecord]:
    try:
        return container.case_management_service.get_questions_by_case_id(case_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/cases/{case_id}/questions/open", response_model=list[QuestionRecord])
async def get_open_questions(case_id: str) -> list[QuestionRecord]:
    try:
        return container.case_management_service.get_open_questions(case_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/questions/{question_id}/answer", response_model=CaseDetail)
async def answer_question(question_id: str, payload: QuestionAnswerPayload) -> CaseDetail:
    try:
        return container.case_management_service.submit_question_answer(question_id, payload.answer)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/legal-basis", response_model=list[LegalBasisEntry])
async def get_legal_basis(ids: list[str] = Query(default=[])) -> list[LegalBasisEntry]:
    return container.case_management_service.get_legal_basis_by_ids(ids)


@app.post("/ingestions/laws", response_model=IngestLawResponse)
async def ingest_law(
    payload: IngestLawRequest,
    context: ObservationContext = Depends(build_context),
) -> IngestLawResponse:
    try:
        bundle = await container.ingestion_service.ingest_law(
            context=context,
            law_id=payload.law_id,
            mst=payload.mst,
            query=payload.query,
        )
    except Exception as error:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=502, detail=str(error)) from error

    return IngestLawResponse(
        law=bundle.law,
        version=bundle.versions[0],
        ingested_units=len(bundle.units),
        ingested_references=len(bundle.references),
    )


@app.get("/ingestions/mock-data/status", response_model=MockDataIngestionResponse)
async def get_mock_data_status() -> MockDataIngestionResponse:
    return container.mock_data_report


@app.post("/ingestions/mock-data/load", response_model=MockDataIngestionResponse)
async def load_mock_data(context: ObservationContext = Depends(build_context)) -> MockDataIngestionResponse:
    container.mock_data_report = container.mock_data_ingestion_service.ingest_directory(context)
    return container.mock_data_report


@app.get("/laws/{official_law_id}", response_model=LawAggregateResponse)
async def get_law(
    official_law_id: str,
    context: ObservationContext = Depends(build_context),
) -> LawAggregateResponse:
    try:
        law = container.repository.get_law(official_law_id, context)
        versions = container.repository.list_versions(official_law_id, context)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return LawAggregateResponse(law=law, versions=versions)


@app.get("/laws/{official_law_id}/versions/as-of", response_model=VersionSelectionResponse)
async def get_law_version_as_of(
    official_law_id: str,
    as_of: date = Query(alias="date"),
    context: ObservationContext = Depends(build_context),
) -> VersionSelectionResponse:
    try:
        law = container.repository.get_law(official_law_id, context)
        version = container.repository.get_version_as_of(official_law_id, as_of, context)
    except (KeyError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    units = container.repository.get_units_for_version(version.id, context)
    return VersionSelectionResponse(law=law, selected_version=version, units=units)


@app.get("/search/text", response_model=TextSearchResponse)
async def search_text(
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    context: ObservationContext = Depends(build_context),
) -> TextSearchResponse:
    return TextSearchResponse(hits=container.text_search_store.search(q, limit, context))


@app.get("/graph/units/{unit_id}/neighbors", response_model=GraphNeighborsResponse)
async def get_neighbors(
    unit_id: str,
    context: ObservationContext = Depends(build_context),
) -> GraphNeighborsResponse:
    return GraphNeighborsResponse(unit_id=unit_id, neighbors=container.graph_store.neighbors(unit_id, context))


@app.post("/services/related-articles/find", response_model=ClarifyResponse | ResultResponse)
async def find_related_articles(
    payload: RelatedArticleRequest,
    context: ObservationContext = Depends(build_context),
) -> ClarifyResponse | ResultResponse:
    try:
        return await container.related_article_service.handle(payload, context)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/services/documents/generate", response_model=DocumentGenerationResponse)
async def generate_document(
    payload: CaseDocumentGenerationRequest,
    context: ObservationContext = Depends(build_context),
) -> DocumentGenerationResponse:
    try:
        request = build_document_generation_request(payload)
        return await container.document_generation_service.generate(request, context)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/services/documents/generate/stream")
async def stream_document_generation(
    payload: CaseDocumentGenerationRequest,
    context: ObservationContext = Depends(build_context),
) -> StreamingResponse:
    async def event_stream():
        try:
            request = build_document_generation_request(payload)
            async for event in container.document_generation_service.stream(request, context):
                body = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                yield f"event: {event.event}\ndata: {body}\n\n"
        except Exception as error:
            event = build_document_stream_error_event(error)
            body = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
            yield f"event: {event.event}\ndata: {body}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.websocket("/services/documents/generate/ws")
async def generate_document_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        payload = CaseDocumentGenerationRequest.model_validate(await websocket.receive_json())
    except WebSocketDisconnect:
        return
    except (ValidationError, ValueError, TypeError) as error:
        await websocket.send_json(build_document_stream_error_event(error).model_dump(mode="json"))
        await websocket.close(code=1008)
        return
    except Exception as error:
        await websocket.send_json(build_document_stream_error_event(error).model_dump(mode="json"))
        await websocket.close(code=1008)
        return

    context = ObservationContext(
        request_id=websocket.headers.get("x-request-id", uuid4().hex),
        corpus_version=websocket.headers.get("x-corpus-version", "v1"),
        ingestion_run_id=websocket.headers.get("x-ingestion-run-id", f"ing-{uuid4().hex}"),
    )
    request = build_document_generation_request(payload)
    try:
        async for event in container.document_generation_service.stream(request, context):
            await websocket.send_json(event.model_dump(mode="json"))
            if event.event == "error":
                await websocket.close(code=1011)
                return
        await websocket.close()
    except WebSocketDisconnect:
        return
    except Exception as error:
        try:
            await websocket.send_json(build_document_stream_error_event(error).model_dump(mode="json"))
        except Exception:
            pass
        await websocket.close(code=1011)
