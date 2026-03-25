from __future__ import annotations

import re
from abc import ABC, abstractmethod

from schemas.common import ObservationContext
from schemas.corpus import Unit
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


class TextSearchStore(ABC):
    @abstractmethod
    def index_units(self, units: list[Unit], context: ObservationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, limit: int, context: ObservationContext) -> list[dict[str, object]]:
        raise NotImplementedError


class InMemoryTextSearchStore(TextSearchStore):
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, object]] = {}

    def index_units(self, units: list[Unit], context: ObservationContext) -> None:
        log_info(logger, "indexing units for text search", context, unit_count=len(units))
        for unit in units:
            text = " ".join(filter(None, [unit.heading, unit.body_text]))
            self._documents[unit.id] = {
                "unit_id": unit.id,
                "version_id": unit.version_id,
                "law_id": unit.law_id,
                "text": text,
                "tokens": set(TOKEN_RE.findall(text.lower())),
            }

    def search(self, query: str, limit: int = 10, context: ObservationContext | None = None) -> list[dict[str, object]]:
        if context is not None:
            log_info(logger, "performing text search", context, query=query, limit=limit)
        query_tokens = set(TOKEN_RE.findall(query.lower()))
        scored: list[dict[str, object]] = []
        for document in self._documents.values():
            overlap = len(query_tokens & document["tokens"])
            if overlap == 0:
                continue
            scored.append(
                {
                    "unit_id": document["unit_id"],
                    "version_id": document["version_id"],
                    "law_id": document["law_id"],
                    "score": overlap,
                    "snippet": str(document["text"])[:240],
                }
            )
        scored.sort(key=lambda item: (item["score"], item["unit_id"]), reverse=True)
        return scored[:limit]
