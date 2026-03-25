from __future__ import annotations

from schemas import (
    DocumentGenerationRequest,
    EvidenceItem,
    EvidencePack,
    EvidenceType,
    ObservationContext,
    SectionDraft,
    SectionPlan,
)
from storage.observability import get_logger, log_info


logger = get_logger(__name__)

OPENING_BY_SECTION = {
    "issue_summary": "현재까지 확인된 자료를 기준으로 사안의 핵심 사실과 쟁점은 다음과 같습니다.",
    "chronology": "확인된 자료를 시간 순서로 정리하면 다음과 같습니다.",
    "legal_points": "직접 검토가 필요한 근거는 다음과 같이 정리됩니다.",
    "open_points": "아직 보완이 필요한 사항은 아래와 같습니다.",
    "violation_summary": "징계 검토를 위해 위반행위를 요약하면 다음과 같습니다.",
    "applicable_rules": "현재 적용 가능성이 높은 규정과 법령은 다음과 같습니다.",
    "mitigation_aggravation": "정상참작 요소와 불리한 요소를 구분하면 다음과 같습니다.",
    "opinion": "현재 확보된 자료를 기준으로 한 종합 의견은 다음과 같습니다.",
    "position": "본 초안에서 기본 입장은 다음과 같이 정리됩니다.",
    "facts": "다툼의 전제가 되는 사실관계는 다음과 같습니다.",
    "arguments": "절차 및 법리 항변 포인트는 다음과 같습니다.",
    "request": "현재 단계에서 요청할 사항은 다음과 같습니다.",
}


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class DocumentSectionGenerator:
    def generate_section(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        section_plan: SectionPlan,
        generated_sections: list[SectionDraft],
        context: ObservationContext,
    ) -> SectionDraft:
        structured_case = evidence_pack.structured_case
        evidence_items = self._select_evidence(section_plan, evidence_pack)
        citations = [item.evidence_id for item in evidence_items]
        open_issues = list(structured_case.missing_slots)

        if not citations and section_plan.required_evidence_types:
            open_issues.append(
                f"필요 근거 부족: {', '.join(evidence_type.value for evidence_type in section_plan.required_evidence_types)}"
            )

        text_parts = [
            OPENING_BY_SECTION.get(section_plan.section_id, f"{section_plan.title}은 다음과 같습니다."),
            self._render_case_sentence(request, evidence_pack),
        ]

        if section_plan.section_id in {"chronology", "facts"}:
            text_parts.append(self._render_fact_details(evidence_pack))
        if section_plan.section_id in {"legal_points", "applicable_rules", "arguments"}:
            text_parts.append(self._render_evidence_summary(evidence_items, section_plan))
        if section_plan.section_id in {"mitigation_aggravation", "opinion", "request", "open_points"}:
            text_parts.append(self._render_open_issues_and_next_steps(open_issues, evidence_items, request))

        if generated_sections and section_plan.section_id in {"opinion", "request"}:
            previous_titles = ", ".join(section.title for section in generated_sections[-2:])
            text_parts.append(f"앞선 섹션 {previous_titles}에서 정리한 내용과 모순되지 않도록 문안을 유지합니다.")

        text = " ".join(part for part in text_parts if part).strip()
        for prohibited in section_plan.prohibited_phrases:
            text = text.replace(prohibited, f"{prohibited}(사용금지)")

        section = SectionDraft(
            section_id=section_plan.section_id,
            title=section_plan.title,
            text=text,
            citations=citations,
            open_issues=_unique_strings(open_issues),
        )
        log_info(
            logger,
            "document section generated",
            context,
            section_id=section.section_id,
            citation_count=len(section.citations),
            open_issue_count=len(section.open_issues),
        )
        return section

    def _select_evidence(self, section_plan: SectionPlan, evidence_pack: EvidencePack) -> list[EvidenceItem]:
        selected: list[EvidenceItem] = []
        by_type = {
            EvidenceType.LAW: evidence_pack.laws,
            EvidenceType.CASE: evidence_pack.cases,
            EvidenceType.REGULATION: evidence_pack.regulations,
            EvidenceType.FORM: evidence_pack.forms,
        }
        for evidence_type in section_plan.required_evidence_types:
            pool = by_type.get(evidence_type, [])
            if pool:
                selected.append(pool[0])

        if section_plan.required_evidence_ids:
            selected.extend(
                item
                for item in evidence_pack.all_items()
                if item.evidence_id in section_plan.required_evidence_ids
            )

        if not selected:
            selected = evidence_pack.all_items()[:2]
        return self._dedupe(selected)

    def _render_case_sentence(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
    ) -> str:
        structured_case = evidence_pack.structured_case
        actors = ", ".join(actor.role or actor.description or "관계인" for actor in structured_case.actors[:2]) or "관계인"
        actions = ", ".join(action.verb for action in structured_case.actions[:2]) or "문제 행위"
        objects = ", ".join(obj.name for obj in structured_case.objects[:2]) or "대상"
        place = structured_case.place.name if structured_case.place and structured_case.place.name else "장소 미상"
        time_text = structured_case.time.mentioned_text if structured_case.time and structured_case.time.mentioned_text else (
            structured_case.as_of_date.isoformat() if structured_case.as_of_date else "시점 미상"
        )
        return (
            f"현재 입력에 따르면 {actors}이/가 {place}에서 {objects}와 관련해 {actions}한 사안으로 보이며,"
            f" 확인 기준 시점은 {time_text}입니다."
        )

    def _render_fact_details(self, evidence_pack: EvidencePack) -> str:
        structured_case = evidence_pack.structured_case
        relationship_text = ", ".join(rel.relation for rel in structured_case.relationships[:2]) or "관계 정보 추가 확인 필요"
        intent = structured_case.intent.description if structured_case.intent and structured_case.intent.description else "의도는 아직 단정하기 어렵습니다"
        damage = structured_case.damage.model_dump(exclude_none=True) if structured_case.damage else {}
        damage_text = ", ".join(f"{key}:{value}" for key, value in damage.items()) or "피해 내용 추가 확인 필요"
        return f"관계 정보는 {relationship_text} 수준으로 파악되며, {intent}. 현재 확인된 피해는 {damage_text}입니다."

    def _render_evidence_summary(self, evidence_items: list[EvidenceItem], section_plan: SectionPlan) -> str:
        if not evidence_items:
            return f"{section_plan.title}에 직접 연결된 근거가 아직 충분하지 않습니다."
        summaries = [
            f"{item.title}은 {item.summary}" for item in evidence_items[:3]
        ]
        return " ".join(summaries)

    def _render_open_issues_and_next_steps(
        self,
        open_issues: list[str],
        evidence_items: list[EvidenceItem],
        request: DocumentGenerationRequest,
    ) -> str:
        doc_type = request.user_intent.doc_type
        if open_issues:
            return f"추가 확인이 필요한 사항은 {', '.join(open_issues[:4])}입니다."
        if evidence_items:
            return f"{doc_type} 문안은 현재 근거를 중심으로 작성하되, 추가 사실관계가 들어오면 보강이 필요합니다."
        return "현재 확보된 자료만으로는 단정적 결론을 피하고 보완조사를 전제로 문안을 유지해야 합니다."

    def _dedupe(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        deduped: list[EvidenceItem] = []
        seen: set[str] = set()
        for item in items:
            if item.evidence_id in seen:
                continue
            seen.add(item.evidence_id)
            deduped.append(item)
        return deduped
