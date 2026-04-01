from __future__ import annotations

import json
from pathlib import Path

from case_management.schemas import DocumentRecord, LegalBasisEntry


DOC_TYPE_TO_LEGAL_BASIS_IDS: dict[str, list[str]] = {
    "investigation_report": ["lb-003", "lb-005"],
    "disciplinary_request": ["lb-003", "lb-005"],
    "notice": ["lb-004"],
    "submission_cover": ["lb-003", "lb-004", "lb-005"],
    "security_investigation": ["lb-003", "lb-009", "lb-010"],
    "circumstance_statement": ["lb-004"],
    "sanction_matrix": ["lb-003", "lb-005", "lb-009"],
    "final_checklist": ["lb-003", "lb-004", "lb-005"],
    "fact_finding_report": ["lb-003", "lb-005"],
    "attendance_notice": ["lb-004"],
    "committee_reference": ["lb-003", "lb-005"],
    "disciplinary_resolution": ["lb-003", "lb-004", "lb-005"],
}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


class DisciplinaryLegalBasisCatalog:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[2]
        self.seed_path = self.root_dir / "backend" / "case_management" / "seed" / "legal-basis.json"
        raw_items = json.loads(self.seed_path.read_text(encoding="utf-8"))
        entries = [LegalBasisEntry.model_validate(item) for item in raw_items]
        self._entries_by_id = {entry.id: entry for entry in entries}

    def resolve_ids_for_document(self, document: DocumentRecord) -> list[str]:
        explicit_ids = [entry.id for entry in self.list_entries(document.legalBasisIds)]
        if explicit_ids:
            return explicit_ids
        return _unique(DOC_TYPE_TO_LEGAL_BASIS_IDS.get(document.type, []))

    def list_entries(
        self,
        ids: list[str],
        *,
        document: DocumentRecord | None = None,
    ) -> list[LegalBasisEntry]:
        del document
        return [
            self._entries_by_id[entry_id].model_copy(deep=True)
            for entry_id in _unique(ids)
            if entry_id in self._entries_by_id
        ]
