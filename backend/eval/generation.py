from __future__ import annotations

from abc import ABC, abstractmethod

from documents import DocumentGenerationService
from eval.schemas import EvalGoldCase, GenerationArtifact, GenerationCaseResult, GenerationEvaluationReport
from eval.utils import average, extract_terms, unique_strings
from schemas import DocumentGenerationRequest, DocumentIntent, ObservationContext


class JudgeScorer(ABC):
    @abstractmethod
    def score(self, artifact: GenerationArtifact, *, unsupported_claim_count: int = 0) -> dict[str, float]:
        raise NotImplementedError


class HeuristicJudgeScorer(JudgeScorer):
    def score(self, artifact: GenerationArtifact, *, unsupported_claim_count: int = 0) -> dict[str, float]:
        warning_penalty = min(0.6, len(artifact.response.warnings) * 0.08)
        coverage = artifact.response.evidence_report.section_coverage
        empty_sections = sum(1 for citations in coverage.values() if not citations)
        section_count = max(len(coverage), 1)
        unsupported_penalty = min(0.3, unsupported_claim_count * 0.1)
        groundedness = max(0.0, 1.0 - (empty_sections / section_count) - warning_penalty - unsupported_penalty)
        overclaim_risk = min(1.0, (empty_sections / section_count) + warning_penalty + unsupported_penalty)
        internal_consistency = max(0.0, 1.0 - (len(artifact.response.warnings) / max(section_count, 1)) * 0.4)
        return {
            "judge_groundedness": round(groundedness, 4),
            "judge_overclaim_risk": round(overclaim_risk, 4),
            "judge_internal_consistency": round(internal_consistency, 4),
        }


class GenerationEvalService:
    def __init__(
        self,
        document_service: DocumentGenerationService,
        *,
        judge: JudgeScorer | None = None,
    ) -> None:
        self.document_service = document_service
        self.judge = judge

    async def evaluate(
        self,
        gold_cases: list[EvalGoldCase],
        context: ObservationContext,
        *,
        default_doc_type: str = "fact_summary",
    ) -> tuple[GenerationEvaluationReport, list[GenerationArtifact]]:
        case_results: list[GenerationCaseResult] = []
        artifacts: list[GenerationArtifact] = []
        summary_metrics: dict[str, list[float]] = {}

        for gold_case in gold_cases:
            doc_type = gold_case.doc_type or default_doc_type
            session_id = f"eval-generation-{gold_case.case_id}"
            self._clear_related_article_session(session_id)
            request = DocumentGenerationRequest(
                session_id=session_id,
                user_intent=DocumentIntent(doc_type=doc_type),
                user_text=gold_case.user_text,
                structured_case=gold_case.structured_case,
                as_of_date=gold_case.as_of_date,
                jurisdiction=gold_case.jurisdiction,
                constraints=gold_case.constraints,
            )
            try:
                response, evidence_pack = await self.document_service.generate_with_artifacts(request, context)
                artifact = GenerationArtifact(gold_case=gold_case, response=response, evidence_pack=evidence_pack)
                artifacts.append(artifact)
                case_result = self._evaluate_artifact(artifact)
                case_results.append(case_result)
                for metric_name, value in case_result.metrics.items():
                    summary_metrics.setdefault(metric_name, []).append(value)
            finally:
                self._clear_related_article_session(session_id)

        report = GenerationEvaluationReport(
            summary={metric_name: round(average(values), 4) for metric_name, values in summary_metrics.items()},
            case_results=case_results,
        )
        return report, artifacts

    def _evaluate_artifact(self, artifact: GenerationArtifact) -> GenerationCaseResult:
        response = artifact.response
        evidence_lookup = {item.evidence_id: item for item in artifact.evidence_pack.all_items()}
        structured_case = artifact.evidence_pack.structured_case
        base_terms = unique_strings(
            [
                *artifact.gold_case.expected_claim_keyphrases,
                *structured_case.keyphrases,
                *structured_case.legal_terms,
                *(action.verb for action in structured_case.actions),
                *(obj.name for obj in structured_case.objects),
            ]
        )

        total_sections = max(len(response.draft.sections), 1)
        cited_sections = 0
        total_citations = 0
        correct_citations = 0
        unsupported_claim_count = 0
        section_debug: list[dict[str, object]] = []

        for section in response.draft.sections:
            claim_terms = [term for term in base_terms if term.lower() in section.text.lower()]
            if not claim_terms:
                claim_terms = extract_terms(section.text)[:8]

            if section.citations:
                cited_sections += 1

            section_correct = False
            matched_terms: list[str] = []
            total_citations += len(section.citations)
            for citation_id in section.citations:
                evidence = evidence_lookup.get(citation_id)
                if evidence is None:
                    continue
                evidence_text = " ".join([evidence.snippet, evidence.summary, " ".join(evidence.keywords)]).lower()
                hits = [term for term in claim_terms if term.lower() in evidence_text]
                if hits:
                    section_correct = True
                    correct_citations += 1
                    matched_terms.extend(hits)

            if claim_terms and not section_correct:
                unsupported_claim_count += 1

            section_debug.append(
                {
                    "section_id": section.section_id,
                    "claim_terms": claim_terms,
                    "matched_terms": unique_strings(matched_terms),
                    "citations": section.citations,
                }
            )

        metrics = {
            "citation_coverage": round(cited_sections / total_sections, 4),
            "citation_correctness": round(correct_citations / max(total_citations, 1), 4),
            "unsupported_claim_count": float(unsupported_claim_count),
        }
        if self.judge is not None:
            metrics.update(self.judge.score(artifact, unsupported_claim_count=unsupported_claim_count))

        failure_tags: list[str] = []
        if metrics["citation_coverage"] < 1.0:
            failure_tags.append("citation_gap")
        if metrics["citation_correctness"] < 0.8:
            failure_tags.append("citation_incorrect")
        if unsupported_claim_count > 0:
            failure_tags.append("unsupported_claim")
        if response.checklist_missing_info:
            failure_tags.append("missing_info")
        warning_codes = [warning.code for warning in response.warnings]
        if any(code == "date_mismatch" for code in warning_codes):
            failure_tags.append("date_mismatch")

        return GenerationCaseResult(
            case_id=artifact.gold_case.case_id,
            doc_type=response.draft.doc_type,
            metrics=metrics,
            failure_tags=unique_strings(failure_tags),
            warnings=warning_codes,
            debug={
                "section_debug": section_debug,
                "used_evidence_ids": response.evidence_report.used_evidence_ids,
            },
        )

    def _clear_related_article_session(self, session_id: str) -> None:
        collector = self.document_service.evidence_collector
        client = getattr(collector, "related_articles_client", None)
        service = getattr(client, "service", None)
        structuring_service = getattr(service, "structuring_service", None)
        if structuring_service is not None and hasattr(structuring_service, "clear_session"):
            structuring_service.clear_session(session_id)
