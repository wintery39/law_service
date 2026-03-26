from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from eval.schemas import EvalGoldCase, RetrievalCaseResult, RetrievalEvaluationReport, RetrievalExperimentSummary
from eval.utils import average, mean_reciprocal_rank, ndcg_at_k, precision_at_k, recall_at_k, unique_strings
from graph import GraphStore
from schemas import ObservationContext, RelatedArticleRequest, UnitType
from search import DomainRouter, StructuredCaseService, TextSearchStore
from search.retrieval import build_query_terms, reciprocal_rank_fusion
from storage import CorpusRepository, VectorStore


MINIMUM_UNITS = {UnitType.ARTICLE, UnitType.PARAGRAPH, UnitType.ITEM, UnitType.SUBITEM}


class RetrievalEvalService:
    def __init__(
        self,
        repository: CorpusRepository,
        graph_store: GraphStore,
        text_search_store: TextSearchStore,
        vector_store: VectorStore,
        *,
        structuring_service: StructuredCaseService | None = None,
        router: DomainRouter | None = None,
    ) -> None:
        self.repository = repository
        self.graph_store = graph_store
        self.text_search_store = text_search_store
        self.vector_store = vector_store
        self.structuring_service = structuring_service or StructuredCaseService()
        self.router = router or DomainRouter()

    async def evaluate(
        self,
        gold_cases: list[EvalGoldCase],
        context: ObservationContext,
        *,
        experiments: list[str] | None = None,
        k_values: list[int] | None = None,
    ) -> RetrievalEvaluationReport:
        experiments = experiments or ["bm25", "vector", "graph", "hybrid"]
        k_values = sorted(k_values or [1, 3, 5])
        case_results: list[RetrievalCaseResult] = []
        metrics_by_experiment: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

        for gold_case in gold_cases:
            session_id = f"eval-retrieval-{gold_case.case_id}"
            self.structuring_service.clear_session(session_id)
            try:
                structured_case, structure_debug = await self.structuring_service.structure(
                    RelatedArticleRequest(
                        session_id=session_id,
                        user_text=gold_case.user_text,
                        structured_case=gold_case.structured_case,
                        as_of_date=gold_case.as_of_date,
                        jurisdiction=gold_case.jurisdiction,
                    ),
                    context,
                )
                route = self.router.classify(structured_case)
                query_terms = build_query_terms(structured_case, route)
                for experiment in experiments:
                    ranked_ids, debug = self._retrieve(
                        experiment,
                        query_terms,
                        structured_case.jurisdiction,
                        context,
                        max(k_values),
                    )
                    filtered_ids, filter_debug, tags = self._post_filter(ranked_ids, gold_case, context)
                    if not query_terms:
                        tags = unique_strings(["query_terms_empty", *tags])
                    metrics = self._calculate_metrics(filtered_ids, gold_case.gold_article_ids, k_values)
                    metrics_by_experiment[experiment]["mrr"].append(metrics["mrr"])
                    for key, value in metrics.items():
                        metrics_by_experiment[experiment][key].append(value)
                    stage = self._infer_stage(tags)
                    case_results.append(
                        RetrievalCaseResult(
                            case_id=gold_case.case_id,
                            experiment=experiment,
                            metrics=metrics,
                            retrieved_ids=filtered_ids[: max(k_values)],
                            gold_ids=gold_case.gold_article_ids,
                            failure_tags=tags,
                            stage=stage,
                            debug={
                                "query_terms": query_terms,
                                "route_labels": route.labels,
                                "structure_debug": structure_debug,
                                "retrieval_debug": debug,
                                "filter_debug": filter_debug,
                            },
                        )
                    )
            finally:
                self.structuring_service.clear_session(session_id)

        summaries = [
            RetrievalExperimentSummary(
                experiment=experiment,
                case_count=len(gold_cases),
                metrics={
                    metric_name: round(average(values), 4)
                    for metric_name, values in metrics_by_experiment[experiment].items()
                },
            )
            for experiment in experiments
        ]
        return RetrievalEvaluationReport(summaries=summaries, case_results=case_results)

    def _retrieve(
        self,
        experiment: str,
        query_terms: list[str],
        jurisdiction: str,
        context: ObservationContext,
        top_k: int,
    ) -> tuple[list[str], dict[str, Any]]:
        limit = max(top_k * 3, 10)
        combined_query = " ".join(query_terms)
        bm25_hits = self.text_search_store.search(combined_query, limit, context)
        vector_hits = self.vector_store.similarity_search(combined_query, limit, context)
        graph_hits = self._graph_hits(query_terms, context, limit)

        if experiment == "bm25":
            ranked_ids = [str(hit["unit_id"]) for hit in bm25_hits]
        elif experiment == "vector":
            ranked_ids = [str(hit["id"]) for hit in vector_hits]
        elif experiment == "graph":
            ranked_ids = [str(hit["unit_id"]) for hit in graph_hits]
        elif experiment == "hybrid":
            fused = reciprocal_rank_fusion(
                {
                    "text": bm25_hits,
                    "vector": [{"unit_id": hit["id"], "score": hit["score"]} for hit in vector_hits],
                    "graph": graph_hits,
                }
            )
            ranked = sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)
            ranked_ids = [str(hit["unit_id"]) for hit in ranked]
        else:
            raise ValueError(f"unsupported retrieval experiment: {experiment}")

        return unique_strings(ranked_ids), {
            "combined_query": combined_query,
            "jurisdiction": jurisdiction,
            "bm25_ids": [str(hit["unit_id"]) for hit in bm25_hits[:limit]],
            "vector_ids": [str(hit["id"]) for hit in vector_hits[:limit]],
            "graph_ids": [str(hit["unit_id"]) for hit in graph_hits[:limit]],
        }

    def _graph_hits(
        self,
        query_terms: list[str],
        context: ObservationContext,
        limit: int,
    ) -> list[dict[str, Any]]:
        seed_hits: list[dict[str, Any]] = []
        seen_seed_units: set[str] = set()
        for seed in query_terms[:8]:
            for item in self.text_search_store.search(seed, 3, context):
                unit_id = str(item["unit_id"])
                if unit_id in seen_seed_units:
                    continue
                seen_seed_units.add(unit_id)
                seed_hits.append({"unit_id": unit_id, "score": float(item["score"]), "seed": seed})

        scored: dict[str, float] = defaultdict(float)
        queue: deque[tuple[str, int]] = deque((str(hit["unit_id"]), 0) for hit in seed_hits)
        seen: set[tuple[str, int]] = set()
        for hit in seed_hits:
            scored[str(hit["unit_id"])] += float(hit["score"])

        while queue:
            unit_id, depth = queue.popleft()
            if (unit_id, depth) in seen or depth >= 2:
                continue
            seen.add((unit_id, depth))
            for neighbor in self.graph_store.neighbors(unit_id, context):
                neighbor_id = str(neighbor["neighbor_id"])
                scored[neighbor_id] += 1.0 / (depth + 2)
                queue.append((neighbor_id, depth + 1))

        ranked = [{"unit_id": unit_id, "score": score} for unit_id, score in scored.items()]
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    def _post_filter(
        self,
        ranked_ids: list[str],
        gold_case: EvalGoldCase,
        context: ObservationContext,
    ) -> tuple[list[str], dict[str, Any], list[str]]:
        filtered_ids: list[str] = []
        filtered_out: list[dict[str, Any]] = []
        tags: list[str] = []
        allowed = set(gold_case.allowed_law_groups)
        gold_in_repo = [gold_id for gold_id in gold_case.gold_article_ids if self._exists_unit(gold_id, context)]
        if len(gold_in_repo) != len(gold_case.gold_article_ids):
            tags.append("gold_missing_from_corpus")

        for unit_id in ranked_ids:
            try:
                unit = self.repository.get_unit(unit_id, context)
                version = self.repository.get_version(unit.version_id, context)
                law = self.repository.get_law_by_internal_id(unit.law_id, context)
            except KeyError:
                filtered_out.append({"unit_id": unit_id, "reasons": ["missing_entity"]})
                continue

            reasons: list[str] = []
            if law.jurisdiction != gold_case.jurisdiction:
                reasons.append("jurisdiction_mismatch")
            if unit.unit_type not in MINIMUM_UNITS:
                reasons.append("not_minimum_unit")
            if allowed and not self._matches_allowed_law_group(law.name_ko, law.id, law.official_law_id, allowed):
                reasons.append("law_group_mismatch")
            if gold_case.as_of_date and version.effective_at and version.effective_at > gold_case.as_of_date:
                reasons.append("not_effective_yet")
            if gold_case.as_of_date and unit.effective_at and unit.effective_at > gold_case.as_of_date:
                reasons.append("unit_not_effective_yet")
            if version.is_repealed and (
                version.repealed_at is None or gold_case.as_of_date is None or version.repealed_at <= gold_case.as_of_date
            ):
                reasons.append("repealed_or_expired")

            if reasons:
                filtered_out.append({"unit_id": unit_id, "reasons": reasons})
                continue
            filtered_ids.append(unit_id)

        filtered_ids = unique_strings(filtered_ids)
        gold_ids = set(gold_case.gold_article_ids)
        if not ranked_ids:
            tags.append("empty_retrieval")
        elif not filtered_ids:
            tags.append("post_filter_drop")
        elif not any(candidate_id in gold_ids for candidate_id in filtered_ids[:5]):
            tags.append("rank_miss")
        if not gold_case.allowed_law_groups:
            tags = [tag for tag in tags if tag != "law_group_mismatch"]

        return filtered_ids, {"filtered_out": filtered_out}, unique_strings(tags)

    def _calculate_metrics(
        self,
        ranked_ids: list[str],
        gold_ids: list[str],
        k_values: list[int],
    ) -> dict[str, float]:
        gold_set = set(gold_ids)
        metrics = {"mrr": round(mean_reciprocal_rank(ranked_ids, gold_set), 4)}
        for k in k_values:
            metrics[f"recall@{k}"] = round(recall_at_k(ranked_ids, gold_set, k), 4)
            metrics[f"precision@{k}"] = round(precision_at_k(ranked_ids, gold_set, k), 4)
            metrics[f"ndcg@{k}"] = round(ndcg_at_k(ranked_ids, gold_set, k), 4)
        return metrics

    def _matches_allowed_law_group(
        self,
        law_name: str,
        law_id: str,
        official_law_id: str,
        allowed_groups: set[str],
    ) -> bool:
        if not allowed_groups:
            return True
        candidates = {law_name, law_id, official_law_id}
        return any(
            allowed in candidate or candidate in allowed
            for allowed in allowed_groups
            for candidate in candidates
        )

    def _exists_unit(self, unit_id: str, context: ObservationContext) -> bool:
        try:
            self.repository.get_unit(unit_id, context)
        except KeyError:
            return False
        return True

    def _infer_stage(self, tags: list[str]) -> str:
        if "query_terms_empty" in tags:
            return "structuring"
        if "post_filter_drop" in tags:
            return "post_filter"
        return "retrieval"
