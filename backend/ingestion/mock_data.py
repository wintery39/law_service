from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re

from pydantic import Field, field_validator

from graph import GraphStore
from schemas.api import MockDataIngestionResponse
from schemas.common import CanonicalBaseModel, ObservationContext, ReferenceType, UnitType, parse_date_value
from schemas.corpus import CorpusBundle, Law, Reference, SourceMeta, Unit, Version
from search.store import TextSearchStore
from storage import CorpusRepository, VectorStore
from storage.id_policy import build_internal_id, build_law_id, build_reference_id, build_version_id, build_version_key
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
ARTICLE_REF_RE = re.compile(r"(제\s*\d+\s*조(?:의\s*\d+)?)")
APPENDIX_REF_RE = re.compile(r"(별표\s*\d+(?:의\s*\d+)?)")
FORM_REF_RE = re.compile(r"(별지\s*제\s*\d+호(?:의\s*\d+)?서식)")
MULTISPACE_RE = re.compile(r"\s+")


def _normalize_space(value: str) -> str:
    return MULTISPACE_RE.sub(" ", value).strip()


class MockUsageRecommendation(CanonicalBaseModel):
    suitable_for: list[str] = Field(default_factory=list)
    not_suitable_for: list[str] = Field(default_factory=list)


class MockArticleEntry(CanonicalBaseModel):
    article_id: str
    article_no: str
    title: str
    content: str
    keywords: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)


class MockAppendixEntry(CanonicalBaseModel):
    appendix_id: str
    appendix_no: str
    title: str
    content: str
    keywords: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    sample_categories: list[str] = Field(default_factory=list)


class MockFormEntry(CanonicalBaseModel):
    form_id: str
    form_no: str
    title: str
    purpose: str
    keywords: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)


class MockDocumentGenerationHint(CanonicalBaseModel):
    preferred_evidence_order: list[str] = Field(default_factory=list)
    recommended_sections: list[str] = Field(default_factory=list)


class MockLawDataset(CanonicalBaseModel):
    law_id: str
    law_name: str
    promulgation_no: str | None = None
    effective_date: date
    dataset_version: str
    dataset_type: str | None = None
    jurisdiction: str = "대한민국"
    scope_notice: str | None = None
    usage_recommendation: MockUsageRecommendation | None = None
    articles: list[MockArticleEntry] = Field(default_factory=list)
    appendices: list[MockAppendixEntry] = Field(default_factory=list)
    forms: list[MockFormEntry] = Field(default_factory=list)
    search_synonyms: dict[str, list[str]] = Field(default_factory=dict)
    document_generation_hints: dict[str, MockDocumentGenerationHint] = Field(default_factory=dict)

    _parse_effective_date = field_validator("effective_date", mode="before")(parse_date_value)


@dataclass
class MockDataIngestionService:
    repository: CorpusRepository
    graph_store: GraphStore
    text_search_store: TextSearchStore
    vector_store: VectorStore
    mock_data_dir: Path

    def ingest_directory(
        self,
        context: ObservationContext,
        directory: Path | None = None,
    ) -> MockDataIngestionResponse:
        target_dir = directory or self.mock_data_dir
        if not target_dir.exists():
            return MockDataIngestionResponse(
                source_directory=str(target_dir),
                loaded_files=[],
                loaded_laws=[],
                ingested_units=0,
                ingested_references=0,
            )

        loaded_files: list[str] = []
        loaded_laws: list[str] = []
        ingested_units = 0
        ingested_references = 0

        for path in sorted(target_dir.glob("*.json")):
            bundle, dataset = self.ingest_file(path, context)
            loaded_files.append(path.name)
            loaded_laws.append(dataset.law_name)
            ingested_units += len(bundle.units)
            ingested_references += len(bundle.references)

        return MockDataIngestionResponse(
            source_directory=str(target_dir),
            loaded_files=loaded_files,
            loaded_laws=loaded_laws,
            ingested_units=ingested_units,
            ingested_references=ingested_references,
        )

    def ingest_file(
        self,
        path: Path,
        context: ObservationContext,
    ) -> tuple[CorpusBundle, MockLawDataset]:
        dataset = MockLawDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
        bundle = self._transform_dataset(dataset, path, context)
        self._persist_bundle(bundle, context)
        return bundle, dataset

    def _transform_dataset(
        self,
        dataset: MockLawDataset,
        source_path: Path,
        context: ObservationContext,
    ) -> CorpusBundle:
        jurisdiction = "kr"
        official_law_id = dataset.law_id
        law_id = build_law_id(jurisdiction, official_law_id)
        version_key = build_version_key(
            dataset.effective_date,
            dataset.effective_date,
            dataset.promulgation_no,
            dataset.dataset_version,
        )
        version_id = build_version_id(jurisdiction, official_law_id, version_key)
        source_meta = SourceMeta(
            jurisdiction=jurisdiction,
            ministry_name="국방부",
            law_kind_name="시연용 요약 데이터셋",
            status_name=dataset.dataset_type or "demo",
            promulgation_number=dataset.promulgation_no,
            promulgated_at=dataset.effective_date,
            source_system="mock_data",
            source_url=str(source_path),
            current_history_code=dataset.dataset_version,
        )
        version = Version(
            id=version_id,
            law_id=law_id,
            official_law_id=official_law_id,
            version_key=version_key,
            promulgated_at=dataset.effective_date,
            effective_at=dataset.effective_date,
            amendment_type=dataset.dataset_type,
            history_code=dataset.dataset_version,
            source_meta=source_meta,
        )
        units = self._build_units(dataset, law_id, version_id, version_key)
        references = self._build_references(dataset, official_law_id, law_id, version_id, version_key, units)
        law = Law(
            id=law_id,
            jurisdiction=jurisdiction,
            official_law_id=official_law_id,
            name_ko=dataset.law_name,
            source_meta=source_meta,
            version_ids=[version_id],
            latest_version_id=version_id,
        )
        log_info(
            logger,
            "transformed mock data dataset",
            context,
            official_law_id=official_law_id,
            unit_count=len(units),
            reference_count=len(references),
            source_file=source_path.name,
        )
        return CorpusBundle(law=law, versions=[version], units=units, references=references)

    def _build_units(
        self,
        dataset: MockLawDataset,
        law_id: str,
        version_id: str,
        version_key: str,
    ) -> list[Unit]:
        units: list[Unit] = []
        order_index = 0

        chapter_specs = [
            ("조문", "chapter/articles", dataset.scope_notice or "핵심 조문 요약"),
            ("별표", "chapter/appendices", "징계 양정 기준과 부가 기준"),
            ("서식", "chapter/forms", "실무 문서 작성 시 참조할 서식"),
        ]
        chapter_ids: dict[str, str] = {}
        for chapter_title, chapter_path, chapter_text in chapter_specs:
            chapter_id = build_internal_id("kr", dataset.law_id, version_key, chapter_path)
            chapter_ids[chapter_title] = chapter_id
            units.append(
                Unit(
                    id=chapter_id,
                    law_id=law_id,
                    version_id=version_id,
                    version_key=version_key,
                    unit_path=chapter_title,
                    unit_type=UnitType.CHAPTER,
                    unit_number=chapter_title,
                    heading=chapter_title,
                    body_text=chapter_text,
                    parent_id=None,
                    order_index=order_index,
                    effective_at=dataset.effective_date,
                )
            )
            order_index += 1

        for article in dataset.articles:
            unit_path = _normalize_space(article.article_no)
            units.append(
                self._build_leaf_unit(
                    dataset=dataset,
                    law_id=law_id,
                    version_id=version_id,
                    version_key=version_key,
                    parent_id=chapter_ids["조문"],
                    unit_key=unit_path,
                    unit_number=article.article_no,
                    heading=f"{article.article_no} {article.title}",
                    body_text=article.content,
                    keywords=article.keywords,
                    related_terms=article.related_terms,
                    extra_terms=[],
                    order_index=order_index,
                )
            )
            order_index += 1

        for appendix in dataset.appendices:
            unit_path = _normalize_space(appendix.appendix_no)
            units.append(
                self._build_leaf_unit(
                    dataset=dataset,
                    law_id=law_id,
                    version_id=version_id,
                    version_key=version_key,
                    parent_id=chapter_ids["별표"],
                    unit_key=unit_path,
                    unit_number=appendix.appendix_no,
                    heading=f"{appendix.appendix_no} {appendix.title}",
                    body_text=appendix.content,
                    keywords=appendix.keywords,
                    related_terms=appendix.related_terms,
                    extra_terms=appendix.sample_categories,
                    order_index=order_index,
                )
            )
            order_index += 1

        for form in dataset.forms:
            unit_path = _normalize_space(form.form_no)
            units.append(
                self._build_leaf_unit(
                    dataset=dataset,
                    law_id=law_id,
                    version_id=version_id,
                    version_key=version_key,
                    parent_id=chapter_ids["서식"],
                    unit_key=unit_path,
                    unit_number=form.form_no,
                    heading=f"{form.form_no} {form.title}",
                    body_text=form.purpose,
                    keywords=form.keywords,
                    related_terms=form.related_terms,
                    extra_terms=[],
                    order_index=order_index,
                )
            )
            order_index += 1

        units.sort(key=lambda item: (item.order_index, item.unit_path))
        return units

    def _build_leaf_unit(
        self,
        *,
        dataset: MockLawDataset,
        law_id: str,
        version_id: str,
        version_key: str,
        parent_id: str,
        unit_key: str,
        unit_number: str,
        heading: str,
        body_text: str,
        keywords: list[str],
        related_terms: list[str],
        extra_terms: list[str],
        order_index: int,
    ) -> Unit:
        expanded_synonyms = self._expand_synonyms(dataset.search_synonyms, [heading, body_text, *keywords, *related_terms, *extra_terms])
        enriched_body = self._build_enriched_body_text(
            body_text=body_text,
            keywords=keywords,
            related_terms=related_terms,
            extra_terms=extra_terms,
            expanded_synonyms=expanded_synonyms,
        )
        return Unit(
            id=build_internal_id("kr", dataset.law_id, version_key, unit_key),
            law_id=law_id,
            version_id=version_id,
            version_key=version_key,
            unit_path=unit_key,
            unit_type=UnitType.ARTICLE,
            unit_number=unit_number,
            heading=heading,
            body_text=enriched_body,
            parent_id=parent_id,
            order_index=order_index,
            effective_at=dataset.effective_date,
        )

    def _build_references(
        self,
        dataset: MockLawDataset,
        official_law_id: str,
        law_id: str,
        version_id: str,
        version_key: str,
        units: list[Unit],
    ) -> list[Reference]:
        references: dict[str, Reference] = {}
        leaf_units = [unit for unit in units if unit.unit_type == UnitType.ARTICLE]
        by_path = {_normalize_space(unit.unit_path): unit.id for unit in leaf_units}
        by_heading = {_normalize_space(unit.heading or ""): unit.id for unit in leaf_units}

        for unit in leaf_units:
            text = " ".join(filter(None, [unit.heading, unit.body_text]))
            for match in ARTICLE_REF_RE.finditer(text):
                normalized = _normalize_space(match.group(1))
                target_id = by_path.get(normalized)
                if target_id and target_id != unit.id:
                    reference = self._build_reference(
                        official_law_id=official_law_id,
                        version_key=version_key,
                        version_id=version_id,
                        law_id=law_id,
                        source_unit=unit,
                        raw_text=normalized,
                        target_unit_id=target_id,
                        reference_type=ReferenceType.INTERNAL,
                    )
                    references[reference.id] = reference

            for regex in (APPENDIX_REF_RE, FORM_REF_RE):
                for match in regex.finditer(text):
                    normalized = _normalize_space(match.group(1))
                    target_id = by_path.get(normalized)
                    if target_id and target_id != unit.id:
                        reference = self._build_reference(
                            official_law_id=official_law_id,
                            version_key=version_key,
                            version_id=version_id,
                            law_id=law_id,
                            source_unit=unit,
                            raw_text=normalized,
                            target_unit_id=target_id,
                            reference_type=ReferenceType.RELATED,
                        )
                        references[reference.id] = reference

            for term in self._extract_named_reference_terms(unit.body_text or ""):
                target_id = by_heading.get(term)
                if target_id and target_id != unit.id:
                    reference = self._build_reference(
                        official_law_id=official_law_id,
                        version_key=version_key,
                        version_id=version_id,
                        law_id=law_id,
                        source_unit=unit,
                        raw_text=term,
                        target_unit_id=target_id,
                        reference_type=ReferenceType.RELATED,
                    )
                    references[reference.id] = reference

        return list(references.values())

    def _build_reference(
        self,
        *,
        official_law_id: str,
        version_key: str,
        version_id: str,
        law_id: str,
        source_unit: Unit,
        raw_text: str,
        target_unit_id: str,
        reference_type: ReferenceType,
    ) -> Reference:
        return Reference(
            id=build_reference_id("kr", official_law_id, version_key, source_unit.unit_path, raw_text),
            source_unit_id=source_unit.id,
            source_law_id=law_id,
            version_id=version_id,
            reference_type=reference_type,
            raw_text=raw_text,
            normalized_citation=raw_text,
            target_law_id=law_id,
            target_unit_id=target_unit_id,
        )

    def _extract_named_reference_terms(self, body_text: str) -> list[str]:
        terms: list[str] = []
        for line in body_text.splitlines():
            if line.startswith(("연관 용어:", "예시 비위:", "검색 동의어:")):
                terms.extend(_normalize_space(item) for item in line.split(":", 1)[1].split(",") if item.strip())
        return terms

    def _expand_synonyms(
        self,
        synonym_map: dict[str, list[str]],
        searchable_terms: list[str],
    ) -> list[str]:
        haystack = " ".join(searchable_terms).lower()
        expanded: list[str] = []
        for synonym, targets in synonym_map.items():
            if any(target.lower() in haystack for target in targets):
                expanded.append(synonym)
        return sorted(set(expanded))

    def _build_enriched_body_text(
        self,
        *,
        body_text: str,
        keywords: list[str],
        related_terms: list[str],
        extra_terms: list[str],
        expanded_synonyms: list[str],
    ) -> str:
        parts = [body_text.strip()]
        if keywords:
            parts.append(f"키워드: {', '.join(keywords)}")
        if related_terms:
            parts.append(f"연관 용어: {', '.join(related_terms)}")
        if extra_terms:
            parts.append(f"예시 비위: {', '.join(extra_terms)}")
        if expanded_synonyms:
            parts.append(f"검색 동의어: {', '.join(expanded_synonyms)}")
        return "\n".join(parts)

    def _persist_bundle(self, bundle: CorpusBundle, context: ObservationContext) -> None:
        self.repository.upsert_bundle(bundle, context)
        self.graph_store.upsert_units(bundle.units, context)
        self.graph_store.upsert_references(bundle.references, context)
        self.text_search_store.index_units(bundle.units, context)
        self.vector_store.upsert_units(bundle.units, context)
        log_info(
            logger,
            "completed mock data ingestion",
            context,
            law_id=bundle.law.official_law_id,
            version_count=len(bundle.versions),
            unit_count=len(bundle.units),
            reference_count=len(bundle.references),
        )
