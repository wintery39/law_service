from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
import json
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import StreamingResponse

from documents import DocumentGenerationService, DocumentGenerationSettings, EvidenceCollector, InProcessRelatedArticlesClient
from graph import InMemoryGraphStore
from ingestion import CanonicalLawTransformer, IngestionService, OpenLawApiClient, OpenLawApiSettings
from schemas import (
    ClarifyResponse,
    DocumentGenerationRequest,
    DocumentGenerationResponse,
    GraphNeighborsResponse,
    IngestLawRequest,
    IngestLawResponse,
    LawAggregateResponse,
    ObservationContext,
    RelatedArticleRequest,
    ResultResponse,
    TextSearchResponse,
    VersionSelectionResponse,
)
from search import InMemoryTextSearchStore, RelatedArticleFinderService, RelatedArticleFinderSettings
from storage import InMemoryCorpusRepository, InMemoryVectorStore


class ServiceContainer:
    def __init__(self) -> None:
        self.repository = InMemoryCorpusRepository()
        self.graph_store = InMemoryGraphStore()
        self.text_search_store = InMemoryTextSearchStore()
        self.vector_store = InMemoryVectorStore()
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
            settings=DocumentGenerationSettings(),
        )


container = ServiceContainer()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await container.api_client.aclose()


app = FastAPI(title="Law Corpus Backend", version="0.1.0", lifespan=lifespan)


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
    return {"status": "ok", "entity_counts": container.repository.count_entities()}


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
    payload: DocumentGenerationRequest,
    context: ObservationContext = Depends(build_context),
) -> DocumentGenerationResponse:
    try:
        return await container.document_generation_service.generate(payload, context)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/services/documents/generate/stream")
async def stream_document_generation(
    payload: DocumentGenerationRequest,
    context: ObservationContext = Depends(build_context),
) -> StreamingResponse:
    async def event_stream():
        async for event in container.document_generation_service.stream(payload, context):
            body = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
            yield f"event: {event.event}\ndata: {body}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.websocket("/services/documents/generate/ws")
async def generate_document_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    payload = DocumentGenerationRequest.model_validate(await websocket.receive_json())
    context = ObservationContext(
        request_id=websocket.headers.get("x-request-id", uuid4().hex),
        corpus_version=websocket.headers.get("x-corpus-version", "v1"),
        ingestion_run_id=websocket.headers.get("x-ingestion-run-id", f"ing-{uuid4().hex}"),
    )
    async for event in container.document_generation_service.stream(payload, context):
        await websocket.send_json(event.model_dump(mode="json"))
    await websocket.close()
