from __future__ import annotations

import json
from pathlib import Path

from eval.schemas import EvalGoldCase


def load_gold_cases(path: str | Path) -> list[EvalGoldCase]:
    file_path = Path(path)
    cases: list[EvalGoldCase] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if "case_id" not in payload:
                payload["case_id"] = f"case-{index:04d}"
            cases.append(EvalGoldCase.model_validate(payload))
    return cases
