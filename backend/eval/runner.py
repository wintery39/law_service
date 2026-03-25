from __future__ import annotations

from pathlib import Path

from documents import DocumentGenerationService
from eval.dataset import load_gold_cases
from eval.generation import GenerationEvalService, HeuristicJudgeScorer
from eval.reporting import build_top_failures, evaluate_quality_gate
from eval.retrieval import RetrievalEvalService
from eval.safety import SafetyEvalService
from eval.schemas import EvalGoldCase, EvaluationReport, EvaluationThresholds
from schemas import ObservationContext
from search import RelatedArticleFinderService


class EvaluationRunner:
    def __init__(
        self,
        *,
        retrieval_eval: RetrievalEvalService,
        generation_eval: GenerationEvalService,
        safety_eval: SafetyEvalService | None = None,
    ) -> None:
        self.retrieval_eval = retrieval_eval
        self.generation_eval = generation_eval
        self.safety_eval = safety_eval or SafetyEvalService()

    async def run_cases(
        self,
        gold_cases: list[EvalGoldCase],
        context: ObservationContext,
        *,
        experiments: list[str] | None = None,
        k_values: list[int] | None = None,
        failure_top_n: int = 10,
        thresholds: EvaluationThresholds | None = None,
        default_doc_type: str = "fact_summary",
    ) -> EvaluationReport:
        retrieval_report = await self.retrieval_eval.evaluate(
            gold_cases,
            context,
            experiments=experiments,
            k_values=k_values,
        )
        generation_report, artifacts = await self.generation_eval.evaluate(
            gold_cases,
            context,
            default_doc_type=default_doc_type,
        )
        safety_report = self.safety_eval.evaluate(artifacts)
        report = EvaluationReport(
            retrieval=retrieval_report,
            generation=generation_report,
            safety=safety_report,
        )
        report.top_failures = build_top_failures(
            retrieval_report,
            generation_report,
            safety_report,
            top_n=failure_top_n,
        )
        report.quality_gate = evaluate_quality_gate(report, thresholds)
        return report

    async def run_file(
        self,
        gold_case_path: str | Path,
        context: ObservationContext,
        *,
        experiments: list[str] | None = None,
        k_values: list[int] | None = None,
        failure_top_n: int = 10,
        thresholds: EvaluationThresholds | None = None,
        default_doc_type: str = "fact_summary",
    ) -> EvaluationReport:
        gold_cases = load_gold_cases(gold_case_path)
        return await self.run_cases(
            gold_cases,
            context,
            experiments=experiments,
            k_values=k_values,
            failure_top_n=failure_top_n,
            thresholds=thresholds,
            default_doc_type=default_doc_type,
        )


def build_default_runner(
    related_article_service: RelatedArticleFinderService | None = None,
    document_generation_service: DocumentGenerationService | None = None,
    *,
    enable_judge: bool = True,
) -> EvaluationRunner:
    if related_article_service is None or document_generation_service is None:
        from main import container

        related_article_service = related_article_service or container.related_article_service
        document_generation_service = document_generation_service or container.document_generation_service

    retrieval_eval = RetrievalEvalService(
        repository=related_article_service.repository,
        graph_store=related_article_service.graph_store,
        text_search_store=related_article_service.text_search_store,
        vector_store=related_article_service.vector_store,
        structuring_service=related_article_service.structuring_service,
        router=related_article_service.router,
    )
    generation_eval = GenerationEvalService(
        document_generation_service,
        judge=HeuristicJudgeScorer() if enable_judge else None,
    )
    return EvaluationRunner(
        retrieval_eval=retrieval_eval,
        generation_eval=generation_eval,
        safety_eval=SafetyEvalService(),
    )
