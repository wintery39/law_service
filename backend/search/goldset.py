from __future__ import annotations

from typing import Literal

from pydantic import Field

from schemas.common import CanonicalBaseModel
from schemas.related_articles import RelatedArticleRequest


class GoldExpectation(CanonicalBaseModel):
    expected_type: Literal["clarify", "result"]
    expected_missing_slots: list[str] = Field(default_factory=list)
    expected_route_labels: list[str] = Field(default_factory=list)
    expected_final_ids: list[str] = Field(default_factory=list)


class GoldScenario(CanonicalBaseModel):
    name: str
    request: RelatedArticleRequest
    expectation: GoldExpectation


class GoldSet(CanonicalBaseModel):
    scenarios: list[GoldScenario]
