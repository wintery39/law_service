from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import defaultdict

from schemas.common import ObservationContext
from schemas.corpus import Unit
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


class VectorStore(ABC):
    @abstractmethod
    def upsert_units(self, units: list[Unit], context: ObservationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def similarity_search(
        self, query: str, limit: int, context: ObservationContext
    ) -> list[dict[str, object]]:
        raise NotImplementedError


def _embed(text: str) -> dict[str, float]:
    counts: dict[str, float] = defaultdict(float)
    for token in TOKEN_RE.findall(text.lower()):
        counts[token] += 1.0
    return dict(counts)


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    numerator = sum(left[token] * right.get(token, 0.0) for token in left)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._vectors: dict[str, dict[str, float]] = {}
        self._texts: dict[str, str] = {}

    def upsert_units(self, units: list[Unit], context: ObservationContext) -> None:
        log_info(logger, "upserting vector documents", context, unit_count=len(units))
        for unit in units:
            text = " ".join(filter(None, [unit.heading, unit.body_text]))
            self._vectors[unit.id] = _embed(text)
            self._texts[unit.id] = text

    def similarity_search(
        self, query: str, limit: int = 10, context: ObservationContext | None = None
    ) -> list[dict[str, object]]:
        if context is not None:
            log_info(logger, "performing vector similarity search", context, limit=limit)
        query_vector = _embed(query)
        scored = [
            {"id": unit_id, "score": _cosine(query_vector, vector), "text": self._texts[unit_id]}
            for unit_id, vector in self._vectors.items()
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        return [item for item in scored[:limit] if item["score"] > 0]
