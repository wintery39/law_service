from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from graph import GraphStore
from schemas.common import ObservationContext
from schemas.related_articles import DomainRoute, StructuredCase
from search.store import TextSearchStore
from storage import CorpusRepository, VectorStore


def build_query_terms(structured_case: StructuredCase, route: DomainRoute) -> list[str]:
    _ = route
    terms = [
        *structured_case.legal_terms,
        *structured_case.keyphrases,
        *(actor.role for actor in structured_case.actors if actor.role),
        *(actor.description for actor in structured_case.actors if actor.description),
        *(action.verb for action in structured_case.actions),
        *(obj.name for obj in structured_case.objects),
        *((structured_case.place.name,) if structured_case.place and structured_case.place.name else ()),
    ]
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result


def build_opensearch_query(
    query_terms: list[str],
    route: DomainRoute,
    jurisdiction: str | None,
) -> dict[str, Any]:
    should_clauses = [{"match": {"body_text": {"query": term, "boost": 2.0}}} for term in query_terms]
    should_clauses.extend({"match": {"heading": {"query": term, "boost": 1.5}}} for term in query_terms)
    filter_clauses: list[dict[str, Any]] = []
    if jurisdiction:
        filter_clauses.append({"term": {"jurisdiction": jurisdiction}})
    if route.labels:
        filter_clauses.append({"terms": {"route_hints": route.labels}})
    return {
        "query": {
            "bool": {
                "must": [{"multi_match": {"query": " ".join(query_terms), "fields": ["heading^2", "body_text"]}}],
                "should": should_clauses,
                "filter": filter_clauses,
            }
        },
        "size": 20,
    }


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[dict[str, Any]]],
    k: int = 60,
) -> dict[str, dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    for channel, items in ranked_lists.items():
        for index, item in enumerate(items, start=1):
            unit_id = str(item["unit_id"])
            entry = fused.setdefault(unit_id, {"unit_id": unit_id, "rrf_score": 0.0, "source_channels": []})
            entry["rrf_score"] += 1.0 / (k + index)
            if channel not in entry["source_channels"]:
                entry["source_channels"].append(channel)
    return fused


class RetrievalPipeline:
    def __init__(
        self,
        repository: CorpusRepository,
        graph_store: GraphStore,
        text_search_store: TextSearchStore,
        vector_store: VectorStore,
    ) -> None:
        self.repository = repository
        self.graph_store = graph_store
        self.text_search_store = text_search_store
        self.vector_store = vector_store

    def retrieve(
        self,
        structured_case: StructuredCase,
        route: DomainRoute,
        context: ObservationContext,
        *,
        top_k: int = 8,
        graph_hops: int = 2,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        query_terms = build_query_terms(structured_case, route)
        combined_query = " ".join(query_terms)

        text_hits = self.text_search_store.search(combined_query, top_k, context)
        vector_hits_raw = self.vector_store.similarity_search(combined_query, top_k, context)
        vector_hits = [
            {"unit_id": item["id"], "score": item["score"], "source": "vector"} for item in vector_hits_raw
        ]

        graph_seed_hits: list[dict[str, Any]] = []
        seen_seed_units: set[str] = set()
        for seed in query_terms[:8]:
            for item in self.text_search_store.search(seed, 3, context):
                if str(item["unit_id"]) in seen_seed_units:
                    continue
                seen_seed_units.add(str(item["unit_id"]))
                graph_seed_hits.append({"unit_id": item["unit_id"], "score": item["score"], "seed": seed})

        graph_hits = self._expand_graph(graph_seed_hits, graph_hops, context)

        fused = reciprocal_rank_fusion(
            {
                "text": text_hits,
                "vector": vector_hits,
                "graph": graph_hits,
            }
        )
        candidates = list(fused.values())
        candidates.sort(key=lambda item: item["rrf_score"], reverse=True)
        return candidates, {
            "query_terms": query_terms,
            "combined_query": combined_query,
            "opensearch_query": build_opensearch_query(query_terms, route, structured_case.jurisdiction),
            "text_hits": text_hits,
            "vector_hits": vector_hits,
            "graph_seed_hits": graph_seed_hits,
            "graph_hits": graph_hits,
            "rrf": candidates,
        }

    def _expand_graph(
        self,
        seed_hits: list[dict[str, Any]],
        max_depth: int,
        context: ObservationContext,
    ) -> list[dict[str, Any]]:
        scored: dict[str, float] = defaultdict(float)
        queue: deque[tuple[str, int]] = deque((str(hit["unit_id"]), 0) for hit in seed_hits)
        seen: set[tuple[str, int]] = set()

        for hit in seed_hits:
            scored[str(hit["unit_id"])] += float(hit["score"])

        while queue:
            unit_id, depth = queue.popleft()
            if (unit_id, depth) in seen or depth >= max_depth:
                continue
            seen.add((unit_id, depth))
            for neighbor in self.graph_store.neighbors(unit_id, context):
                neighbor_id = str(neighbor["neighbor_id"])
                scored[neighbor_id] += 1.0 / (depth + 2)
                queue.append((neighbor_id, depth + 1))

        hits = [{"unit_id": unit_id, "score": score} for unit_id, score in scored.items()]
        hits.sort(key=lambda item: item["score"], reverse=True)
        return hits[:20]
