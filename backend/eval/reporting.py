from __future__ import annotations

import json

from eval.schemas import (
    EvaluationReport,
    EvaluationThresholds,
    FailureCase,
    GenerationEvaluationReport,
    QualityGateResult,
    RetrievalEvaluationReport,
    SafetyEvaluationReport,
)


class QualityGateError(RuntimeError):
    pass


def build_top_failures(
    retrieval: RetrievalEvaluationReport,
    generation: GenerationEvaluationReport,
    safety: SafetyEvaluationReport,
    *,
    top_n: int = 10,
) -> list[FailureCase]:
    failures: list[FailureCase] = []

    for case in retrieval.case_results:
        if not case.failure_tags:
            continue
        score = 1.0 - max(case.metrics.get("recall@5", 0.0), case.metrics.get("mrr", 0.0))
        failures.append(
            FailureCase(
                evaluation_type="retrieval",
                case_id=case.case_id,
                experiment=case.experiment,
                stage=case.stage,
                reason_tags=case.failure_tags,
                score=round(score, 4),
                details={"metrics": case.metrics, "retrieved_ids": case.retrieved_ids[:5]},
            )
        )

    for case in generation.case_results:
        if not case.failure_tags:
            continue
        score = case.metrics.get("unsupported_claim_count", 0.0) + (1.0 - case.metrics.get("citation_correctness", 0.0))
        failures.append(
            FailureCase(
                evaluation_type="generation",
                case_id=case.case_id,
                experiment=case.doc_type,
                stage="generation",
                reason_tags=case.failure_tags,
                score=round(score, 4),
                details={"metrics": case.metrics, "warnings": case.warnings},
            )
        )

    for case in safety.case_results:
        if not case.failure_tags:
            continue
        score = (
            case.metrics.get("definitive_phrase_count", 0.0)
            + case.metrics.get("forbidden_phrase_count", 0.0)
            + case.metrics.get("missing_info_without_disclosure", 0.0)
        )
        failures.append(
            FailureCase(
                evaluation_type="safety",
                case_id=case.case_id,
                experiment=case.doc_type,
                stage="safety",
                reason_tags=case.failure_tags,
                score=round(score, 4),
                details={"metrics": case.metrics},
            )
        )

    failures.sort(key=lambda item: item.score, reverse=True)
    return failures[:top_n]


def evaluate_quality_gate(
    report: EvaluationReport,
    thresholds: EvaluationThresholds | None,
) -> QualityGateResult:
    if thresholds is None:
        return QualityGateResult(passed=True)

    failures: list[str] = []

    retrieval_summary = {summary.experiment: summary for summary in report.retrieval.summaries}
    for threshold in thresholds.retrieval:
        summary = retrieval_summary.get(threshold.experiment)
        if summary is None:
            failures.append(f"retrieval summary missing for experiment={threshold.experiment}")
            continue
        for metric_name, minimum in threshold.min_metrics.items():
            actual = summary.metrics.get(metric_name)
            if actual is None or actual < minimum:
                failures.append(
                    f"retrieval {threshold.experiment} {metric_name} below threshold: actual={actual} minimum={minimum}"
                )

    generation_summary = report.generation.summary
    if thresholds.generation.min_citation_coverage is not None:
        actual = generation_summary.get("citation_coverage", 0.0)
        if actual < thresholds.generation.min_citation_coverage:
            failures.append(
                "generation citation_coverage below threshold: "
                f"actual={actual} minimum={thresholds.generation.min_citation_coverage}"
            )
    if thresholds.generation.min_citation_correctness is not None:
        actual = generation_summary.get("citation_correctness", 0.0)
        if actual < thresholds.generation.min_citation_correctness:
            failures.append(
                "generation citation_correctness below threshold: "
                f"actual={actual} minimum={thresholds.generation.min_citation_correctness}"
            )
    if thresholds.generation.max_unsupported_claim_count is not None:
        actual = generation_summary.get("unsupported_claim_count", 0.0)
        if actual > thresholds.generation.max_unsupported_claim_count:
            failures.append(
                "generation unsupported_claim_count above threshold: "
                f"actual={actual} maximum={thresholds.generation.max_unsupported_claim_count}"
            )
    if thresholds.generation.min_judge_groundedness is not None:
        actual = generation_summary.get("judge_groundedness", 0.0)
        if actual < thresholds.generation.min_judge_groundedness:
            failures.append(
                "generation judge_groundedness below threshold: "
                f"actual={actual} minimum={thresholds.generation.min_judge_groundedness}"
            )

    safety_summary = report.safety.summary
    if thresholds.safety.max_definitive_phrase_count is not None:
        actual = safety_summary.get("definitive_phrase_count", 0.0)
        if actual > thresholds.safety.max_definitive_phrase_count:
            failures.append(
                "safety definitive_phrase_count above threshold: "
                f"actual={actual} maximum={thresholds.safety.max_definitive_phrase_count}"
            )
    if thresholds.safety.max_forbidden_phrase_count is not None:
        actual = safety_summary.get("forbidden_phrase_count", 0.0)
        if actual > thresholds.safety.max_forbidden_phrase_count:
            failures.append(
                "safety forbidden_phrase_count above threshold: "
                f"actual={actual} maximum={thresholds.safety.max_forbidden_phrase_count}"
            )
    if thresholds.safety.max_missing_info_without_disclosure is not None:
        actual = safety_summary.get("missing_info_without_disclosure", 0.0)
        if actual > thresholds.safety.max_missing_info_without_disclosure:
            failures.append(
                "safety missing_info_without_disclosure above threshold: "
                f"actual={actual} maximum={thresholds.safety.max_missing_info_without_disclosure}"
            )
    if thresholds.safety.max_warning_error_count is not None:
        actual = safety_summary.get("warning_error_count", 0.0)
        if actual > thresholds.safety.max_warning_error_count:
            failures.append(
                "safety warning_error_count above threshold: "
                f"actual={actual} maximum={thresholds.safety.max_warning_error_count}"
            )

    return QualityGateResult(passed=not failures, failures=failures)


def assert_quality_gate(report: EvaluationReport, thresholds: EvaluationThresholds | None) -> None:
    result = evaluate_quality_gate(report, thresholds)
    if not result.passed:
        raise QualityGateError("\n".join(result.failures))


def render_text_report(report: EvaluationReport) -> str:
    lines: list[str] = ["[Retrieval]"]
    for summary in report.retrieval.summaries:
        metric_text = ", ".join(f"{key}={value}" for key, value in sorted(summary.metrics.items()))
        lines.append(f"- {summary.experiment}: {metric_text}")

    lines.append("[Generation]")
    lines.append("- " + ", ".join(f"{key}={value}" for key, value in sorted(report.generation.summary.items())))

    lines.append("[Safety]")
    lines.append("- " + ", ".join(f"{key}={value}" for key, value in sorted(report.safety.summary.items())))

    lines.append("[Top Failures]")
    if not report.top_failures:
        lines.append("- none")
    else:
        for failure in report.top_failures:
            lines.append(
                f"- {failure.evaluation_type}:{failure.case_id}:{failure.experiment} "
                f"stage={failure.stage} score={failure.score} tags={','.join(failure.reason_tags)}"
            )

    lines.append("[Quality Gate]")
    lines.append(f"- passed={report.quality_gate.passed}")
    for failure in report.quality_gate.failures:
        lines.append(f"- {failure}")
    return "\n".join(lines)


def render_json_report(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
