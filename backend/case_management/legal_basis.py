from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from case_management.schemas import DocumentRecord, LegalBasisEntry
from ingestion.mock_data import MockLawDataset


DOC_TYPE_TO_SOURCE_KEYS: dict[str, list[str]] = {
    "investigation_report": ["art_002", "art_004", "app_005"],
    "disciplinary_request": ["art_002", "art_004", "art_006", "app_005"],
    "notice": ["art_006", "form_001"],
    "submission_cover": ["art_006", "form_001"],
    "security_investigation": ["art_002", "art_004", "app_001"],
    "circumstance_statement": ["art_006", "form_001"],
    "sanction_matrix": ["art_002", "art_004", "app_001", "app_005"],
    "final_checklist": ["art_006", "form_001", "app_001"],
}


def _summarize(text: str, limit: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}..."


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


@dataclass(frozen=True)
class _SourceEntry:
    entry_id: str
    source_key: str
    kind: str
    law_name: str
    article: str
    title: str
    summary: str


class DisciplinaryLegalBasisCatalog:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[2]
        self.mock_data_path = self.root_dir / "backend" / "mock_data" / "military_discipline_rule_demo.json"
        dataset = MockLawDataset.model_validate(json.loads(self.mock_data_path.read_text(encoding="utf-8")))
        self._entries_by_id: dict[str, _SourceEntry] = {}
        self._entry_id_by_source_key: dict[str, str] = {}
        self._load_dataset(dataset)

    def resolve_ids_for_document(self, document: DocumentRecord) -> list[str]:
        explicit_ids = [entry.id for entry in self.list_entries(document.legalBasisIds)]
        suggested_ids = self._suggest_ids_for_document(document)
        return _unique([*explicit_ids, *suggested_ids])

    def list_entries(
        self,
        ids: list[str],
        *,
        document: DocumentRecord | None = None,
    ) -> list[LegalBasisEntry]:
        entries: list[LegalBasisEntry] = []
        for entry_id in _unique(ids):
            source = self._entries_by_id.get(entry_id)
            if source is None:
                continue
            entries.append(
                LegalBasisEntry(
                    id=source.entry_id,
                    lawName=source.law_name,
                    article=source.article,
                    summary=source.summary,
                    rationale=self._build_rationale(source, document.title if document is not None else None),
                    relatedDocumentIds=[document.id] if document is not None else [],
                )
            )
        return entries

    def _suggest_ids_for_document(self, document: DocumentRecord) -> list[str]:
        source_keys = DOC_TYPE_TO_SOURCE_KEYS.get(document.type, [])
        return [
            self._entry_id_by_source_key[source_key]
            for source_key in source_keys
            if source_key in self._entry_id_by_source_key
        ]

    def _load_dataset(self, dataset: MockLawDataset) -> None:
        for article in dataset.articles:
            self._register(
                source_key=article.article_id,
                kind="article",
                law_name=dataset.law_name,
                article=article.article_no,
                title=article.title,
                summary=_summarize(article.content),
            )

        for appendix in dataset.appendices:
            self._register(
                source_key=appendix.appendix_id,
                kind="appendix",
                law_name=dataset.law_name,
                article=appendix.appendix_no,
                title=appendix.title,
                summary=_summarize(appendix.content),
            )

        for form in dataset.forms:
            self._register(
                source_key=form.form_id,
                kind="form",
                law_name=dataset.law_name,
                article=form.form_no,
                title=form.title,
                summary=_summarize(form.purpose),
            )

    def _register(
        self,
        *,
        source_key: str,
        kind: str,
        law_name: str,
        article: str,
        title: str,
        summary: str,
    ) -> None:
        public_id = f"mdr-{source_key.replace('_', '-')}"
        entry = _SourceEntry(
            entry_id=public_id,
            source_key=source_key,
            kind=kind,
            law_name=law_name,
            article=article,
            title=title,
            summary=summary,
        )
        self._entries_by_id[public_id] = entry
        self._entry_id_by_source_key[source_key] = public_id

    def _build_rationale(self, source: _SourceEntry, document_title: str | None) -> str:
        target = document_title or "징계 문서"
        if source.kind == "appendix":
            return f"{target}에서 비위 유형과 징계 수위를 비교하기 위한 기준표로 사용합니다."
        if source.kind == "form":
            return f"{target} 작성 시 서식 체계와 제출 문안을 맞추기 위한 기준으로 사용합니다."
        return f"{target} 작성 시 징계 절차와 판단 기준을 직접 연결하기 위해 사용합니다."
