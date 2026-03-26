from __future__ import annotations

import json
from pathlib import Path

import pytest

from documents import DocumentGenerationService, DocumentGenerationSettings, EvidenceCollector, InProcessRelatedArticlesClient
from eval.__main__ import _load_thresholds
from eval import (
    EvalGoldCase,
    EvaluationRunner,
    EvaluationThresholds,
    GenerationEvalService,
    HeuristicJudgeScorer,
    QualityGateError,
    RetrievalEvalService,
    RetrievalThreshold,
    SafetyEvalService,
    assert_quality_gate,
    evaluate_quality_gate,
    load_gold_cases,
    render_text_report,
)
from tests.test_related_article_service import build_context, seed_related_article_fixture


def build_eval_runner() -> EvaluationRunner:
    fixture = seed_related_article_fixture()
    document_service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        settings=DocumentGenerationSettings(),
    )
    retrieval_eval = RetrievalEvalService(
        repository=fixture.repository,
        graph_store=fixture.graph_store,
        text_search_store=fixture.text_search_store,
        vector_store=fixture.vector_store,
        structuring_service=fixture.service.structuring_service,
        router=fixture.service.router,
    )
    generation_eval = GenerationEvalService(document_service, judge=HeuristicJudgeScorer())
    return EvaluationRunner(
        retrieval_eval=retrieval_eval,
        generation_eval=generation_eval,
        safety_eval=SafetyEvalService(),
    )


def write_gold_cases(path: Path, ids: dict[str, str]) -> Path:
    records = [
        {
            "case_id": "gold-admin-fact",
            "user_text": "행정청이 민원인에게 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
            "as_of_date": "2024-03-01",
            "gold_article_ids": [ids["admin_notice_v1"], ids["admin_opinion_v1"]],
            "allowed_law_groups": ["행정절차법"],
            "doc_type": "fact_summary",
            "expected_claim_keyphrases": ["행정처분", "사전통지", "의견제출"],
        },
        {
            "case_id": "gold-discipline-opinion",
            "user_text": "지휘관의 명령을 거부한 병사에 대한 징계 의견이 필요합니다.",
            "as_of_date": "2024-03-01",
            "gold_article_ids": [ids["discipline_order"]],
            "allowed_law_groups": ["군복무규율"],
            "doc_type": "disciplinary_opinion",
            "expected_claim_keyphrases": ["명령거부", "징계", "상관"],
        },
        {
            "case_id": "gold-defense-draft",
            "user_text": "병사가 생활관에서 폭행했다는 신고가 있었지만 피해자 진술이 일치하지 않습니다.",
            "as_of_date": "2024-03-01",
            "gold_article_ids": [ids["criminal_assault"]],
            "allowed_law_groups": ["형법"],
            "doc_type": "defense_draft",
            "expected_claim_keyphrases": ["폭행", "피해자", "신체"],
            "forbidden_phrases": ["반드시"],
        },
    ]
    gold_path = path / "gold_cases.jsonl"
    gold_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )
    return gold_path


def test_load_gold_cases(tmp_path: Path) -> None:
    fixture = seed_related_article_fixture()
    gold_path = write_gold_cases(tmp_path, fixture.ids)

    cases = load_gold_cases(gold_path)

    assert len(cases) == 3
    assert cases[0].case_id == "gold-admin-fact"
    assert cases[1].doc_type == "disciplinary_opinion"
    assert cases[2].gold_article_ids == [fixture.ids["criminal_assault"]]


@pytest.mark.asyncio
async def test_eval_runner_builds_report(tmp_path: Path) -> None:
    fixture = seed_related_article_fixture()
    runner = build_eval_runner()
    gold_path = write_gold_cases(tmp_path, fixture.ids)

    report = await runner.run_file(
        gold_path,
        build_context(),
        experiments=["bm25", "vector", "graph", "hybrid"],
        k_values=[1, 3, 5],
        failure_top_n=5,
    )

    retrieval_summary = {summary.experiment: summary.metrics for summary in report.retrieval.summaries}
    assert len(report.retrieval.case_results) == 12
    assert "recall@5" in retrieval_summary["hybrid"]
    assert "mrr" in retrieval_summary["bm25"]
    assert report.generation.summary["citation_coverage"] > 0
    assert "judge_groundedness" in report.generation.summary
    assert "definitive_phrase_count" in report.safety.summary
    assert report.quality_gate.passed is True
    assert render_text_report(report).startswith("[Retrieval]")


@pytest.mark.asyncio
async def test_eval_quality_gate(tmp_path: Path) -> None:
    fixture = seed_related_article_fixture()
    runner = build_eval_runner()
    gold_path = write_gold_cases(tmp_path, fixture.ids)
    report = await runner.run_file(
        gold_path,
        build_context(),
        experiments=["hybrid"],
        k_values=[1, 3, 5],
        failure_top_n=3,
    )

    passing_thresholds = EvaluationThresholds.model_validate(
        {
            "retrieval": [{"experiment": "hybrid", "min_metrics": {"recall@5": 0.3}}],
            "generation": {"min_citation_coverage": 0.5, "min_citation_correctness": 0.2},
            "safety": {"max_definitive_phrase_count": 0.0, "max_warning_error_count": 0.0},
        }
    )
    passing_result = evaluate_quality_gate(report, passing_thresholds)
    assert passing_result.passed is True

    failing_thresholds = EvaluationThresholds(
        retrieval=[RetrievalThreshold(experiment="hybrid", min_metrics={"recall@1": 1.1})]
    )
    failing_result = evaluate_quality_gate(report, failing_thresholds)
    assert failing_result.passed is False
    with pytest.raises(QualityGateError):
        assert_quality_gate(report, failing_thresholds)


@pytest.mark.asyncio
async def test_generation_eval_uses_final_generation_evidence_pack() -> None:
    fixture = seed_related_article_fixture()
    document_service = DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(fixture.service),
            repository=fixture.repository,
            text_search_store=fixture.text_search_store,
        ),
        settings=DocumentGenerationSettings(),
    )
    generation_eval = GenerationEvalService(document_service, judge=HeuristicJudgeScorer())

    report, artifacts = await generation_eval.evaluate(
        [
            EvalGoldCase(
                case_id="gold-clarify-plan-loop",
                user_text="폭행이 문제입니다.",
                as_of_date="2024-03-01",
                gold_article_ids=[fixture.ids["criminal_assault"]],
                allowed_law_groups=["형법"],
                doc_type="defense_draft",
                expected_claim_keyphrases=["폭행", "신체", "피해자"],
            )
        ],
        build_context(),
    )

    artifact = artifacts[0]
    artifact_evidence_ids = {item.evidence_id for item in artifact.evidence_pack.all_items()}
    used_evidence_ids = set(artifact.response.evidence_report.used_evidence_ids)

    assert artifact.response.evidence_report.source_mode == "clarify"
    assert any(evidence_id.startswith("law:") for evidence_id in used_evidence_ids)
    assert used_evidence_ids.issubset(artifact_evidence_ids)
    assert report.case_results[0].metrics["citation_correctness"] > 0
    assert fixture.service.structuring_service._sessions == {}


@pytest.mark.asyncio
async def test_retrieval_eval_marks_missing_gold_as_retrieval_stage() -> None:
    fixture = seed_related_article_fixture()
    retrieval_eval = RetrievalEvalService(
        repository=fixture.repository,
        graph_store=fixture.graph_store,
        text_search_store=fixture.text_search_store,
        vector_store=fixture.vector_store,
        structuring_service=fixture.service.structuring_service,
        router=fixture.service.router,
    )

    report = await retrieval_eval.evaluate(
        [
            EvalGoldCase(
                case_id="gold-missing-corpus",
                user_text="병사가 상관의 명령을 거부했습니다.",
                as_of_date="2024-03-01",
                gold_article_ids=["kr:missing-law:v1:article-999999"],
                allowed_law_groups=["군복무규율"],
                doc_type="disciplinary_opinion",
            )
        ],
        build_context(),
        experiments=["hybrid"],
        k_values=[1, 3],
    )

    assert report.case_results[0].stage == "retrieval"
    assert "gold_missing_from_corpus" in report.case_results[0].failure_tags
    assert fixture.service.structuring_service._sessions == {}


def test_load_thresholds_accepts_long_inline_json() -> None:
    raw = json.dumps(
        {
            "retrieval": [
                {
                    "experiment": "hybrid",
                    "min_metrics": {
                        "recall@5": 0.5,
                        "precision@5": 0.25,
                        "ndcg@5": 0.4,
                        "long_padding_metric_name_" + ("x" * 300): 0.1,
                    },
                }
            ],
            "generation": {"min_citation_coverage": 0.5},
        },
        ensure_ascii=False,
    )

    thresholds = _load_thresholds(raw)

    assert thresholds is not None
    assert thresholds.retrieval[0].experiment == "hybrid"
