from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

from schemas.common import ObservationContext
from schemas.corpus import Reference, Unit
from storage.observability import get_logger, log_info


logger = get_logger(__name__)


class GraphStore(ABC):
    @abstractmethod
    def upsert_units(self, units: list[Unit], context: ObservationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_references(self, references: list[Reference], context: ObservationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def neighbors(self, unit_id: str, context: ObservationContext) -> list[dict[str, object]]:
        raise NotImplementedError


class InMemoryGraphStore(GraphStore):
    def __init__(self) -> None:
        self._adjacency: dict[str, list[dict[str, object]]] = defaultdict(list)

    def upsert_units(self, units: list[Unit], context: ObservationContext) -> None:
        log_info(logger, "upserting units into graph", context, unit_count=len(units))
        for unit in units:
            if unit.parent_id:
                parent_edge = {"neighbor_id": unit.parent_id, "relationship": "PARENT"}
                child_edge = {"neighbor_id": unit.id, "relationship": "CHILD"}
                if parent_edge not in self._adjacency[unit.id]:
                    self._adjacency[unit.id].append(parent_edge)
                if child_edge not in self._adjacency[unit.parent_id]:
                    self._adjacency[unit.parent_id].append(child_edge)

    def upsert_references(self, references: list[Reference], context: ObservationContext) -> None:
        log_info(logger, "upserting references into graph", context, reference_count=len(references))
        for reference in references:
            if not reference.target_unit_id:
                continue
            outbound = {
                "neighbor_id": reference.target_unit_id,
                "relationship": f"REF_{reference.reference_type.value.upper()}",
                "reference_id": reference.id,
            }
            inbound = {
                "neighbor_id": reference.source_unit_id,
                "relationship": "REFERRED_BY",
                "reference_id": reference.id,
            }
            if outbound not in self._adjacency[reference.source_unit_id]:
                self._adjacency[reference.source_unit_id].append(outbound)
            if inbound not in self._adjacency[reference.target_unit_id]:
                self._adjacency[reference.target_unit_id].append(inbound)

    def neighbors(self, unit_id: str, context: ObservationContext) -> list[dict[str, object]]:
        log_info(logger, "retrieving graph neighbors", context, unit_id=unit_id)
        return list(self._adjacency.get(unit_id, []))
