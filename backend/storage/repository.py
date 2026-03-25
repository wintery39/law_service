from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date

from schemas.common import ObservationContext
from schemas.corpus import CorpusBundle, Law, Reference, Unit, Version
from storage.observability import get_logger, log_info


logger = get_logger(__name__)


def select_version_as_of(versions: list[Version], as_of: date) -> Version:
    eligible = [
        version
        for version in versions
        if (version.effective_at or version.promulgated_at or date.min) <= as_of
    ]
    if not eligible:
        raise LookupError("no version available for the given as-of date")
    eligible.sort(
        key=lambda version: (
            version.effective_at or date.min,
            version.promulgated_at or date.min,
            version.version_key,
        ),
        reverse=True,
    )
    return eligible[0]


class CorpusRepository(ABC):
    @abstractmethod
    def upsert_bundle(self, bundle: CorpusBundle, context: ObservationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_law(self, official_law_id: str, context: ObservationContext) -> Law:
        raise NotImplementedError

    @abstractmethod
    def list_versions(self, official_law_id: str, context: ObservationContext) -> list[Version]:
        raise NotImplementedError

    @abstractmethod
    def get_units_for_version(self, version_id: str, context: ObservationContext) -> list[Unit]:
        raise NotImplementedError

    @abstractmethod
    def get_version_as_of(
        self, official_law_id: str, as_of: date, context: ObservationContext
    ) -> Version:
        raise NotImplementedError

    @abstractmethod
    def get_version(self, version_id: str, context: ObservationContext) -> Version:
        raise NotImplementedError

    @abstractmethod
    def get_unit(self, unit_id: str, context: ObservationContext) -> Unit:
        raise NotImplementedError

    @abstractmethod
    def list_units(self, context: ObservationContext) -> list[Unit]:
        raise NotImplementedError

    @abstractmethod
    def get_law_by_internal_id(self, law_id: str, context: ObservationContext) -> Law:
        raise NotImplementedError

    @abstractmethod
    def count_entities(self) -> dict[str, int]:
        raise NotImplementedError


class InMemoryCorpusRepository(CorpusRepository):
    def __init__(self) -> None:
        self._laws: dict[str, Law] = {}
        self._law_by_official_id: dict[str, str] = {}
        self._versions: dict[str, Version] = {}
        self._versions_by_law: dict[str, set[str]] = defaultdict(set)
        self._units: dict[str, Unit] = {}
        self._units_by_version: dict[str, set[str]] = defaultdict(set)
        self._references: dict[str, Reference] = {}

    def upsert_bundle(self, bundle: CorpusBundle, context: ObservationContext) -> None:
        log_info(
            logger,
            "upserting corpus bundle",
            context,
            law_id=bundle.law.official_law_id,
            version_count=len(bundle.versions),
            unit_count=len(bundle.units),
            reference_count=len(bundle.references),
        )

        self._laws[bundle.law.id] = bundle.law
        self._law_by_official_id[bundle.law.official_law_id] = bundle.law.id

        for version in bundle.versions:
            self._versions[version.id] = version
            self._versions_by_law[bundle.law.official_law_id].add(version.id)

        for unit in bundle.units:
            self._units[unit.id] = unit
            self._units_by_version[unit.version_id].add(unit.id)

        for reference in bundle.references:
            self._references[reference.id] = reference

    def get_law(self, official_law_id: str, context: ObservationContext) -> Law:
        law_internal_id = self._law_by_official_id.get(official_law_id)
        if law_internal_id is None:
            raise KeyError(f"law not found: {official_law_id}")
        log_info(logger, "retrieving law", context, law_id=official_law_id)
        return self._laws[law_internal_id]

    def list_versions(self, official_law_id: str, context: ObservationContext) -> list[Version]:
        version_ids = self._versions_by_law.get(official_law_id)
        if not version_ids:
            raise KeyError(f"versions not found: {official_law_id}")
        log_info(logger, "listing versions", context, law_id=official_law_id)
        versions = [self._versions[version_id] for version_id in version_ids]
        versions.sort(
            key=lambda version: (
                version.effective_at or date.min,
                version.promulgated_at or date.min,
                version.version_key,
            ),
            reverse=True,
        )
        return versions

    def get_units_for_version(self, version_id: str, context: ObservationContext) -> list[Unit]:
        unit_ids = self._units_by_version.get(version_id, set())
        log_info(logger, "retrieving version units", context, version_id=version_id, unit_count=len(unit_ids))
        units = [self._units[unit_id] for unit_id in unit_ids]
        units.sort(key=lambda unit: (unit.order_index, unit.unit_path))
        return units

    def get_version_as_of(
        self, official_law_id: str, as_of: date, context: ObservationContext
    ) -> Version:
        versions = self.list_versions(official_law_id, context)
        selected = select_version_as_of(versions, as_of)
        log_info(
            logger,
            "selected version as-of",
            context,
            law_id=official_law_id,
            as_of=as_of.isoformat(),
            version_id=selected.id,
        )
        return selected

    def get_version(self, version_id: str, context: ObservationContext) -> Version:
        if version_id not in self._versions:
            raise KeyError(f"version not found: {version_id}")
        log_info(logger, "retrieving version", context, version_id=version_id)
        return self._versions[version_id]

    def get_unit(self, unit_id: str, context: ObservationContext) -> Unit:
        if unit_id not in self._units:
            raise KeyError(f"unit not found: {unit_id}")
        log_info(logger, "retrieving unit", context, unit_id=unit_id)
        return self._units[unit_id]

    def list_units(self, context: ObservationContext) -> list[Unit]:
        log_info(logger, "listing all units", context, unit_count=len(self._units))
        units = list(self._units.values())
        units.sort(key=lambda unit: (unit.order_index, unit.unit_path))
        return units

    def get_law_by_internal_id(self, law_id: str, context: ObservationContext) -> Law:
        if law_id not in self._laws:
            raise KeyError(f"law not found: {law_id}")
        log_info(logger, "retrieving law by internal id", context, law_id=law_id)
        return self._laws[law_id]

    def count_entities(self) -> dict[str, int]:
        return {
            "laws": len(self._laws),
            "versions": len(self._versions),
            "units": len(self._units),
            "references": len(self._references),
        }
