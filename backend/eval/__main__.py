from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from eval import build_default_runner, render_json_report, render_text_report
from eval.schemas import EvaluationThresholds
from schemas import ObservationContext


def _load_thresholds(raw: str | None) -> EvaluationThresholds | None:
    if raw is None:
        return None
    path = Path(raw)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(raw)
    return EvaluationThresholds.model_validate(payload)


async def _run(args: argparse.Namespace) -> int:
    runner = build_default_runner(enable_judge=not args.disable_judge)
    thresholds = _load_thresholds(args.thresholds)
    context = ObservationContext(
        request_id="eval-cli",
        corpus_version=args.corpus_version,
        ingestion_run_id=args.ingestion_run_id,
    )
    report = await runner.run_file(
        args.gold_cases,
        context,
        experiments=args.experiments,
        k_values=args.k_values,
        failure_top_n=args.failure_top_n,
        thresholds=thresholds,
        default_doc_type=args.default_doc_type,
    )
    output = render_json_report(report) if args.output_format == "json" else render_text_report(report)
    print(output)
    if not report.quality_gate.passed:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval/generation/safety evaluation suite.")
    parser.add_argument("--gold-cases", required=True, help="Path to gold_cases.jsonl")
    parser.add_argument("--experiments", nargs="+", default=["bm25", "vector", "graph", "hybrid"])
    parser.add_argument("--k-values", nargs="+", type=int, default=[1, 3, 5])
    parser.add_argument("--failure-top-n", type=int, default=10)
    parser.add_argument("--thresholds", help="JSON string or path to thresholds json")
    parser.add_argument("--default-doc-type", default="fact_summary")
    parser.add_argument("--disable-judge", action="store_true")
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--corpus-version", default="eval-cli")
    parser.add_argument("--ingestion-run-id", default="eval-cli")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
