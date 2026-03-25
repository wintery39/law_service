from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from schemas.common import ObservationContext, ReferenceType, UnitType, parse_date_value
from schemas.corpus import (
    AmendmentHistory,
    CorpusBundle,
    Law,
    Reference,
    SourceMeta,
    Unit,
    Version,
)
from storage.id_policy import (
    build_internal_id,
    build_law_id,
    build_reference_id,
    build_version_id,
    build_version_key,
)
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
ARTICLE_REF_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
EXTERNAL_LAW_RE = re.compile(r"「([^」]+)」")


def _walk_nodes(payload: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        yield payload
        for value in payload.values():
            yield from _walk_nodes(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_nodes(item)


def _pick_first(payload: Any, *keys: str) -> Any:
    if isinstance(payload, Mapping):
        for key in keys:
            if payload.get(key) not in (None, ""):
                return payload[key]
        for value in payload.values():
            found = _pick_first(value, *keys)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _pick_first(item, *keys)
            if found not in (None, ""):
                return found
    return None


def _normalize_jo_code(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if text.isdigit():
        return text.zfill(6)
    digits = re.findall(r"\d+", text)
    if not digits:
        return "000000"
    primary = int(digits[0])
    sub = int(digits[1]) if len(digits) > 1 else 0
    return f"{primary:04d}{sub:02d}"


class CanonicalLawTransformer:
    def extract_article_numbers(self, raw_body: Any) -> list[str]:
        article_numbers: set[str] = set()
        for node in _walk_nodes(raw_body):
            jo_number = _pick_first(node, "조문번호", "jo", "JO")
            if jo_number not in (None, ""):
                article_numbers.add(_normalize_jo_code(jo_number))
        return sorted(article_numbers)

    def transform(
        self,
        list_payload: Any,
        body_payload: Any,
        article_payloads: list[Any],
        history_payload: Any,
        context: ObservationContext,
    ) -> CorpusBundle:
        log_info(logger, "transforming raw law payload into canonical bundle", context)
        official_law_id = str(
            _pick_first(body_payload, "법령ID", "ID", "law_id")
            or _pick_first(list_payload, "법령ID", "law_id", "ID")
            or "unknown"
        )
        law_name = str(
            _pick_first(body_payload, "법령명한글", "법령명", "법령명_한글")
            or _pick_first(list_payload, "법령명한글", "법령명", "법령명_한글")
            or "이름 미상 법령"
        )
        jurisdiction = "kr"
        source_meta = SourceMeta(
            jurisdiction=jurisdiction,
            ministry_name=_pick_first(body_payload, "소관부처명", "소관부처"),
            ministry_code=_pick_first(body_payload, "소관부처코드", "org"),
            law_kind_name=_pick_first(body_payload, "법령구분명", "법령종류", "법령구분"),
            law_kind_code=_pick_first(body_payload, "법령종류코드", "knd"),
            status_name=_pick_first(body_payload, "법령상태", "법령상태명"),
            promulgation_number=str(
                _pick_first(body_payload, "공포번호", "공포번호(공동부령의 공포번호)", "ancNo") or ""
            )
            or None,
            promulgated_at=parse_date_value(_pick_first(body_payload, "공포일자", "공포일")),
            source_url=_pick_first(body_payload, "법령상세링크", "상세링크"),
            current_history_code=_pick_first(body_payload, "현행연혁코드", "historyCode"),
        )
        version_key = build_version_key(
            source_meta.promulgated_at,
            parse_date_value(_pick_first(body_payload, "시행일자", "시행일")),
            source_meta.promulgation_number,
            source_meta.current_history_code,
        )

        law_id = build_law_id(jurisdiction, official_law_id)
        version_id = build_version_id(jurisdiction, official_law_id, version_key)

        history_entries = self._extract_history_entries(history_payload)
        version = Version(
            id=version_id,
            law_id=law_id,
            official_law_id=official_law_id,
            version_key=version_key,
            promulgated_at=source_meta.promulgated_at,
            effective_at=parse_date_value(_pick_first(body_payload, "시행일자", "시행일")),
            repealed_at=parse_date_value(_pick_first(body_payload, "폐지일자", "실효일자")),
            amendment_type=_pick_first(body_payload, "제개정구분명", "제개정구분"),
            history_code=source_meta.current_history_code,
            is_repealed=source_meta.status_name in {"폐지", "실효"},
            history_entries=history_entries,
            source_meta=source_meta,
        )

        units = self._build_units(
            official_law_id=official_law_id,
            law_id=law_id,
            version_id=version_id,
            version_key=version_key,
            article_payloads=article_payloads,
            context=context,
        )
        references = self._extract_references(
            official_law_id=official_law_id,
            version_id=version_id,
            version_key=version_key,
            units=units,
        )
        law = Law(
            id=law_id,
            jurisdiction=jurisdiction,
            official_law_id=official_law_id,
            name_ko=law_name,
            name_alias=_pick_first(body_payload, "법령약칭명", "약칭"),
            source_meta=source_meta,
            version_ids=[version_id],
            latest_version_id=version_id,
        )
        return CorpusBundle(law=law, versions=[version], units=units, references=references)

    def _extract_history_entries(self, history_payload: Any) -> list[AmendmentHistory]:
        entries: list[AmendmentHistory] = []
        seen: set[tuple[str | None, str | None]] = set()
        for node in _walk_nodes(history_payload):
            change_date = parse_date_value(_pick_first(node, "공포일자", "조문변경일"))
            amendment_type = _pick_first(node, "제개정구분명", "변경사유")
            if change_date is None and amendment_type is None:
                continue
            key = (change_date.isoformat() if change_date else None, str(amendment_type or ""))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                AmendmentHistory(
                    event_date=change_date,
                    amendment_type=str(amendment_type) if amendment_type else None,
                    description=_pick_first(node, "변경사유", "비고"),
                    promulgation_number=str(_pick_first(node, "공포번호", "ancNo") or "") or None,
                )
            )
        entries.sort(key=lambda item: item.event_date or parse_date_value("1900-01-01"), reverse=True)
        return entries

    def _build_units(
        self,
        official_law_id: str,
        law_id: str,
        version_id: str,
        version_key: str,
        article_payloads: list[Any],
        context: ObservationContext,
    ) -> list[Unit]:
        units_by_id: dict[str, Unit] = {}
        order_index = 0

        for payload in article_payloads:
            article_number = _normalize_jo_code(_pick_first(payload, "조문번호", "JO"))
            article_path = f"article-{article_number}"
            article_id = build_internal_id("kr", official_law_id, version_key, article_path)
            article = Unit(
                id=article_id,
                law_id=law_id,
                version_id=version_id,
                version_key=version_key,
                unit_path=article_path,
                unit_type=UnitType.ARTICLE,
                unit_number=article_number,
                heading=_pick_first(payload, "조문제목", "조제목"),
                body_text=_pick_first(payload, "조문내용", "조내용"),
                parent_id=None,
                order_index=order_index,
                effective_at=parse_date_value(_pick_first(payload, "조문시행일자", "시행일자")),
            )
            units_by_id[article.id] = article
            order_index += 1

            paragraph_nodes = [
                node for node in _walk_nodes(payload) if _pick_first(node, "항번호") not in (None, "")
            ]
            if not paragraph_nodes and _pick_first(payload, "항내용"):
                paragraph_nodes = [payload]

            for paragraph_node in paragraph_nodes:
                paragraph_no = str(_pick_first(paragraph_node, "항번호") or "1")
                paragraph_path = f"{article_path}/paragraph-{paragraph_no.zfill(3)}"
                paragraph_id = build_internal_id("kr", official_law_id, version_key, paragraph_path)
                paragraph = Unit(
                    id=paragraph_id,
                    law_id=law_id,
                    version_id=version_id,
                    version_key=version_key,
                    unit_path=paragraph_path,
                    unit_type=UnitType.PARAGRAPH,
                    unit_number=paragraph_no,
                    heading=None,
                    body_text=_pick_first(paragraph_node, "항내용"),
                    parent_id=article.id,
                    order_index=order_index,
                    effective_at=parse_date_value(_pick_first(paragraph_node, "조문시행일자", "시행일자")),
                )
                units_by_id[paragraph.id] = paragraph
                order_index += 1

                item_nodes = [
                    node for node in _walk_nodes(paragraph_node) if _pick_first(node, "호번호") not in (None, "")
                ]
                for item_node in item_nodes:
                    item_no = str(_pick_first(item_node, "호번호"))
                    item_path = f"{paragraph_path}/item-{item_no}"
                    item_id = build_internal_id("kr", official_law_id, version_key, item_path)
                    item = Unit(
                        id=item_id,
                        law_id=law_id,
                        version_id=version_id,
                        version_key=version_key,
                        unit_path=item_path,
                        unit_type=UnitType.ITEM,
                        unit_number=item_no,
                        heading=None,
                        body_text=_pick_first(item_node, "호내용"),
                        parent_id=paragraph.id,
                        order_index=order_index,
                        effective_at=parse_date_value(_pick_first(item_node, "조문시행일자", "시행일자")),
                    )
                    units_by_id[item.id] = item
                    order_index += 1

                    subitem_nodes = [
                        node
                        for node in _walk_nodes(item_node)
                        if _pick_first(node, "목번호") not in (None, "")
                    ]
                    for subitem_node in subitem_nodes:
                        subitem_no = str(_pick_first(subitem_node, "목번호"))
                        subitem_path = f"{item_path}/subitem-{subitem_no}"
                        subitem_id = build_internal_id("kr", official_law_id, version_key, subitem_path)
                        subitem = Unit(
                            id=subitem_id,
                            law_id=law_id,
                            version_id=version_id,
                            version_key=version_key,
                            unit_path=subitem_path,
                            unit_type=UnitType.SUBITEM,
                            unit_number=subitem_no,
                            heading=None,
                            body_text=_pick_first(subitem_node, "목내용"),
                            parent_id=item.id,
                            order_index=order_index,
                            effective_at=parse_date_value(
                                _pick_first(subitem_node, "조문시행일자", "시행일자")
                            ),
                        )
                        units_by_id[subitem.id] = subitem
                        order_index += 1

        units = list(units_by_id.values())
        log_info(logger, "built canonical units", context, unit_count=len(units))
        units.sort(key=lambda unit: (unit.order_index, unit.unit_path))
        return units

    def _extract_references(
        self,
        official_law_id: str,
        version_id: str,
        version_key: str,
        units: list[Unit],
    ) -> list[Reference]:
        references: dict[str, Reference] = {}
        law_id = build_law_id("kr", official_law_id)

        for unit in units:
            text = " ".join(filter(None, [unit.heading, unit.body_text]))
            for match in ARTICLE_REF_RE.finditer(text):
                jo_main = int(match.group(1))
                jo_sub = int(match.group(2) or 0)
                jo_code = f"{jo_main:04d}{jo_sub:02d}"
                target_unit_path = f"article-{jo_code}"
                target_unit_id = build_internal_id("kr", official_law_id, version_key, target_unit_path)
                reference = Reference(
                    id=build_reference_id("kr", official_law_id, version_key, unit.unit_path, match.group(0)),
                    source_unit_id=unit.id,
                    source_law_id=law_id,
                    version_id=version_id,
                    reference_type=ReferenceType.INTERNAL,
                    raw_text=match.group(0),
                    normalized_citation=f"{official_law_id}:{jo_code}",
                    target_law_id=law_id,
                    target_unit_id=target_unit_id,
                )
                references[reference.id] = reference

            for match in EXTERNAL_LAW_RE.finditer(text):
                target_name = match.group(1)
                reference = Reference(
                    id=build_reference_id("kr", official_law_id, version_key, unit.unit_path, match.group(0)),
                    source_unit_id=unit.id,
                    source_law_id=law_id,
                    version_id=version_id,
                    reference_type=ReferenceType.EXTERNAL,
                    raw_text=match.group(0),
                    normalized_citation=target_name,
                    target_law_id=target_name,
                    target_unit_id=None,
                )
                references[reference.id] = reference

        return list(references.values())
