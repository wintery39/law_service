from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from schemas.common import ObservationContext, UnitType
from schemas.related_articles import DomainRoute, RelatedArticleCandidate, StructuredCase
from storage import CorpusRepository


class HeuristicRubricScorer:
    def score(
        self,
        structured_case: StructuredCase,
        unit_text: str,
        route: DomainRoute,
    ) -> dict[str, float]:
        _ = route
        case_terms = set(structured_case.keyphrases + structured_case.legal_terms)
        text = unit_text.lower()
        matches = sum(1 for term in case_terms if term.lower() in text)
        coverage = matches / max(len(case_terms), 1)
        risk = 0.6 if coverage < 0.2 else 0.15
        return {
            "relevance": min(1.0, coverage + 0.2),
            "evidence": min(1.0, coverage + 0.25),
            "overclaim_risk": risk,
        }


@dataclass
class RetrievalEvaluator:
    repository: CorpusRepository
    rubric_scorer: HeuristicRubricScorer | None = None

    def __post_init__(self) -> None:
        if self.rubric_scorer is None:
            self.rubric_scorer = HeuristicRubricScorer()

    def evaluate(
        self,
        structured_case: StructuredCase,
        route: DomainRoute,
        candidates: list[dict[str, Any]],
        context: ObservationContext,
        *,
        top_n: int = 5,
    ) -> tuple[list[RelatedArticleCandidate], list[RelatedArticleCandidate], dict[str, Any]]:
        evaluated: list[RelatedArticleCandidate] = []
        filtered_out: list[dict[str, Any]] = []
        case_terms = set(term.lower() for term in structured_case.keyphrases + structured_case.legal_terms)
        as_of = structured_case.as_of_date
        jurisdiction = structured_case.jurisdiction

        for candidate in candidates:
            unit = self.repository.get_unit(str(candidate["unit_id"]), context)
            version = self.repository.get_version(unit.version_id, context)
            law = self.repository.get_law_by_internal_id(unit.law_id, context)
            filter_reasons: list[str] = []
            minimum_units = {UnitType.ARTICLE, UnitType.PARAGRAPH, UnitType.ITEM, UnitType.SUBITEM}

            if jurisdiction and law.jurisdiction != jurisdiction:
                filter_reasons.append("jurisdiction_mismatch")
            if unit.unit_type not in minimum_units:
                filter_reasons.append("not_minimum_unit")
            if as_of and (version.effective_at and version.effective_at > as_of):
                filter_reasons.append("not_effective_yet")
            if as_of and (unit.effective_at and unit.effective_at > as_of):
                filter_reasons.append("unit_not_effective_yet")
            if version.is_repealed and (version.repealed_at is None or as_of is None or version.repealed_at <= as_of):
                filter_reasons.append("repealed_or_expired")

            unit_text = " ".join(filter(None, [unit.heading, unit.body_text]))
            covered_terms = {term for term in case_terms if term in unit_text.lower()}
            coverage_score = len(covered_terms) / max(len(case_terms), 1)
            rubric = self.rubric_scorer.score(structured_case, unit_text, route)
            rerank_score = coverage_score
            final_score = (
                float(candidate["rrf_score"]) * 0.35
                + rerank_score * 0.25
                + coverage_score * 0.20
                + rubric["relevance"] * 0.20
                - rubric["overclaim_risk"] * 0.15
            )

            article_candidate = RelatedArticleCandidate(
                internal_id=unit.id,
                law_name=law.name_ko,
                law_internal_id=law.id,
                official_law_id=law.official_law_id,
                unit_path=unit.unit_path,
                snippet=unit_text[:300],
                effective_at=unit.effective_at or version.effective_at,
                amended_at=version.promulgated_at,
                source_channels=list(candidate.get("source_channels", [])),
                rrf_score=float(candidate["rrf_score"]),
                rerank_score=round(rerank_score, 4),
                coverage_score=round(coverage_score, 4),
                rubric_score=round((rubric["relevance"] + rubric["evidence"]) / 2, 4),
                risk_score=round(rubric["overclaim_risk"], 4),
                final_score=round(final_score, 4),
            )

            if filter_reasons:
                filtered_out.append(
                    {
                        "internal_id": unit.id,
                        "reasons": filter_reasons,
                        "version_id": version.id,
                    }
                )
                continue

            evaluated.append(article_candidate)

        evaluated.sort(key=lambda item: item.final_score, reverse=True)
        return evaluated, evaluated[:top_n], {"filtered_out": filtered_out}
