from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from graph import GraphStore
from schemas.common import ObservationContext
from schemas.corpus import CorpusBundle
from search.store import TextSearchStore
from storage import CorpusRepository, VectorStore
from storage.observability import get_logger, log_info

from ingestion.open_law_api import OpenLawApiClient, extract_law_name, extract_promulgated_at
from ingestion.transformers import CanonicalLawTransformer


logger = get_logger(__name__)


@dataclass
class IngestionService:
    api_client: OpenLawApiClient
    repository: CorpusRepository
    graph_store: GraphStore
    text_search_store: TextSearchStore
    vector_store: VectorStore
    transformer: CanonicalLawTransformer

    async def ingest_law(
        self,
        *,
        context: ObservationContext,
        law_id: str | None = None,
        mst: str | None = None,
        query: str | None = None,
    ) -> CorpusBundle:
        log_info(logger, "starting law ingestion", context, law_id=law_id or "", mst=mst or "", query=query or "")
        body_payload = await self.api_client.fetch_law_body(context=context, law_id=law_id, mst=mst)
        list_payload = await self.api_client.list_laws(
            context=context,
            query=query or law_id or extract_law_name(body_payload),
            display=20,
        )
        article_numbers = self.transformer.extract_article_numbers(body_payload)
        article_payloads = await asyncio.gather(
            *[
                self.api_client.fetch_law_article_unit(
                    context=context,
                    law_id=law_id,
                    mst=mst,
                    jo=article_number,
                )
                for article_number in article_numbers
            ]
        ) if article_numbers else []
        history_payload = await self.api_client.fetch_history_meta(
            context=context,
            law_name=extract_law_name(body_payload),
            promulgated_at=extract_promulgated_at(body_payload),
        )
        bundle = self.transformer.transform(
            list_payload=list_payload,
            body_payload=body_payload,
            article_payloads=article_payloads,
            history_payload=history_payload,
            context=context,
        )
        self._persist_bundle(bundle, context)
        return bundle

    def ingest_from_payloads(
        self,
        *,
        list_payload: Any,
        body_payload: Any,
        article_payloads: list[Any],
        history_payload: Any,
        context: ObservationContext,
    ) -> CorpusBundle:
        bundle = self.transformer.transform(
            list_payload=list_payload,
            body_payload=body_payload,
            article_payloads=article_payloads,
            history_payload=history_payload,
            context=context,
        )
        self._persist_bundle(bundle, context)
        return bundle

    def _persist_bundle(self, bundle: CorpusBundle, context: ObservationContext) -> None:
        self.repository.upsert_bundle(bundle, context)
        self.graph_store.upsert_units(bundle.units, context)
        self.graph_store.upsert_references(bundle.references, context)
        self.text_search_store.index_units(bundle.units, context)
        self.vector_store.upsert_units(bundle.units, context)
        log_info(
            logger,
            "completed law ingestion",
            context,
            law_id=bundle.law.official_law_id,
            version_count=len(bundle.versions),
            unit_count=len(bundle.units),
            reference_count=len(bundle.references),
        )
