from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph import GraphStore
from schemas.common import ObservationContext
from schemas.related_articles import (
    ClarifyResponse,
    DomainRoute,
    RelatedArticleRequest,
    RelatedArticleResponse,
    ResultResponse,
)
from search.evaluation import RetrievalEvaluator
from search.retrieval import RetrievalPipeline
from search.routing import DomainRouter
from search.store import TextSearchStore
from search.structuring import StructuredCaseService, build_clarification_questions, detect_missing_slots
from storage import CorpusRepository, VectorStore


@dataclass
class RelatedArticleFinderSettings:
    operational_mode: bool = False
    debug_sample_rate: float = 1.0
    top_k: int = 8
    top_n: int = 5


class RelatedArticleFinderService:
    def __init__(
        self,
        repository: CorpusRepository,
        graph_store: GraphStore,
        text_search_store: TextSearchStore,
        vector_store: VectorStore,
        *,
        structuring_service: StructuredCaseService | None = None,
        router: DomainRouter | None = None,
        evaluator: RetrievalEvaluator | None = None,
        settings: RelatedArticleFinderSettings | None = None,
    ) -> None:
        self.repository = repository
        self.graph_store = graph_store
        self.text_search_store = text_search_store
        self.vector_store = vector_store
        self.structuring_service = structuring_service or StructuredCaseService()
        self.router = router or DomainRouter()
        self.retrieval_pipeline = RetrievalPipeline(
            repository=repository,
            graph_store=graph_store,
            text_search_store=text_search_store,
            vector_store=vector_store,
        )
        self.evaluator = evaluator or RetrievalEvaluator(repository=repository)
        self.settings = settings or RelatedArticleFinderSettings()

    async def handle(
        self,
        request: RelatedArticleRequest,
        context: ObservationContext,
    ) -> RelatedArticleResponse:
        structured_case, structure_debug = await self.structuring_service.structure(request, context)
        structured_case.missing_slots = detect_missing_slots(structured_case)

        critical_missing = [slot for slot in structured_case.missing_slots if slot in {"actors", "actions", "objects"}]
        if critical_missing or len(structured_case.missing_slots) >= 4:
            return ClarifyResponse(
                questions=build_clarification_questions(structured_case.missing_slots),
                missing_slots=structured_case.missing_slots,
                partial_structured_case=structured_case,
            )

        route: DomainRoute = self.router.classify(structured_case)
        retrieved, retrieval_debug = self.retrieval_pipeline.retrieve(
            structured_case,
            route,
            context,
            top_k=self.settings.top_k,
        )
        candidates, final, evaluation_debug = self.evaluator.evaluate(
            structured_case,
            route,
            retrieved,
            context,
            top_n=self.settings.top_n,
        )

        debug = {
            "structure": structure_debug,
            "retrieval": retrieval_debug,
            "evaluation": evaluation_debug,
        }
        if self.settings.operational_mode:
            debug = self._mask_debug(debug)

        return ResultResponse(
            structured_case=structured_case,
            route=route,
            candidates=candidates,
            final=final,
            debug=debug,
        )

    def _mask_debug(self, debug: dict[str, Any]) -> dict[str, Any]:
        return {
            "sampled": self.settings.debug_sample_rate >= 1.0,
            "structure": {"schema_attempts": debug.get("structure", {}).get("schema_attempts", [])},
            "retrieval": {"query_terms": debug.get("retrieval", {}).get("query_terms", [])[:5]},
            "evaluation": {"filtered_out_count": len(debug.get("evaluation", {}).get("filtered_out", []))},
        }
