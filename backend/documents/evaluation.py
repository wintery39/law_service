from __future__ import annotations

import re

from schemas import (
    DocumentDraft,
    DocumentGenerationRequest,
    DocumentPlan,
    DraftPatch,
    DraftWarning,
    EvidencePack,
    EvidenceType,
)


DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TERM_REPLACEMENTS = {
    "disciplinary_opinion": {"처벌": "징계 검토"},
    "defense_draft": {"유죄": "혐의"},
    "fact_summary": {"명백히": "현재 자료상", "확정적으로": "확인된 범위에서"},
}


class DocumentDraftEvaluator:
    def evaluate(
        self,
        request: DocumentGenerationRequest,
        plan: DocumentPlan,
        draft: DocumentDraft,
        evidence_pack: EvidencePack,
    ) -> list[DraftWarning]:
        warnings: list[DraftWarning] = []
        warnings.extend(self._check_schema(plan, draft))
        warnings.extend(self._check_citations(plan, draft, evidence_pack))
        warnings.extend(self._check_dates(request, draft, evidence_pack))
        warnings.extend(self._check_terms(request, plan, draft, evidence_pack))
        return warnings

    def _check_schema(self, plan: DocumentPlan, draft: DocumentDraft) -> list[DraftWarning]:
        warnings: list[DraftWarning] = []
        expected_ids = {section.section_id for section in plan.sections}
        actual_ids = {section.section_id for section in draft.sections}

        for missing in sorted(expected_ids - actual_ids):
            warnings.append(
                DraftWarning(
                    code="missing_section",
                    severity="error",
                    message=f"필수 섹션 {missing} 이 초안에 없습니다.",
                    section_id=missing,
                    patch=DraftPatch(
                        section_id=missing,
                        issue_code="missing_section",
                        instruction="누락된 섹션을 추가합니다.",
                        replacement_text=f"{missing} 섹션을 추가하고 관련 근거를 붙이세요.",
                    ),
                )
            )

        for section in draft.sections:
            if not section.text.strip():
                warnings.append(
                    DraftWarning(
                        code="empty_section",
                        severity="error",
                        message=f"{section.section_id} 섹션 본문이 비어 있습니다.",
                        section_id=section.section_id,
                        patch=DraftPatch(
                            section_id=section.section_id,
                            issue_code="empty_section",
                            instruction="섹션 본문을 채웁니다.",
                            replacement_text=f"{section.title}의 목적과 근거를 반영한 문단을 추가하세요.",
                        ),
                    )
                )
        return warnings

    def _check_citations(
        self,
        plan: DocumentPlan,
        draft: DocumentDraft,
        evidence_pack: EvidencePack,
    ) -> list[DraftWarning]:
        warnings: list[DraftWarning] = []
        valid_ids = {item.evidence_id for item in evidence_pack.all_items()}
        plan_by_id = {section.section_id: section for section in plan.sections}
        for section in draft.sections:
            unknown = [citation for citation in section.citations if citation not in valid_ids]
            if unknown:
                warnings.append(
                    DraftWarning(
                        code="unknown_citation",
                        severity="error",
                        message=f"{section.section_id} 섹션에 등록되지 않은 인용이 있습니다: {', '.join(unknown)}",
                        section_id=section.section_id,
                    )
                )
            planned = plan_by_id.get(section.section_id)
            requires_evidence = bool(planned and planned.required_evidence_types)
            if requires_evidence and not section.citations:
                replacement = "근거 인용을 추가하세요."
                if planned.required_evidence_types:
                    replacement = (
                        f"{', '.join(evidence_type.value for evidence_type in planned.required_evidence_types)}"
                        " 유형 근거를 인용하세요."
                    )
                warnings.append(
                    DraftWarning(
                        code="unsupported_paragraph",
                        severity="warning",
                        message=f"{section.section_id} 섹션에 근거 인용이 없습니다.",
                        section_id=section.section_id,
                        patch=DraftPatch(
                            section_id=section.section_id,
                            issue_code="unsupported_paragraph",
                            instruction="근거 없는 문단을 보완합니다.",
                            target_excerpt=section.text[:120],
                            replacement_text=replacement,
                        ),
                    )
                )
        return warnings

    def _check_dates(
        self,
        request: DocumentGenerationRequest,
        draft: DocumentDraft,
        evidence_pack: EvidencePack,
    ) -> list[DraftWarning]:
        known_dates = set()
        structured_case = evidence_pack.structured_case
        for candidate in [
            request.as_of_date,
            structured_case.as_of_date,
            structured_case.time.as_of_date if structured_case.time else None,
        ]:
            if candidate is not None:
                known_dates.add(candidate.isoformat())
        for item in evidence_pack.all_items():
            for key in ("effective_at", "amended_at"):
                value = item.metadata.get(key)
                if value is not None:
                    known_dates.add(str(value))

        warnings: list[DraftWarning] = []
        for section in draft.sections:
            seen_dates = set(DATE_RE.findall(section.text))
            mismatched = sorted(value for value in seen_dates if value not in known_dates)
            if mismatched:
                warnings.append(
                    DraftWarning(
                        code="date_mismatch",
                        severity="warning",
                        message=f"{section.section_id} 섹션의 날짜가 입력 또는 근거와 일치하지 않을 수 있습니다: {', '.join(mismatched)}",
                        section_id=section.section_id,
                        patch=DraftPatch(
                            section_id=section.section_id,
                            issue_code="date_mismatch",
                            instruction="날짜를 입력 사실관계 또는 근거 기준일과 대조합니다.",
                            replacement_text=f"사용 가능한 날짜는 {', '.join(sorted(known_dates)) or '없음'} 입니다.",
                        ),
                    )
                )
        return warnings

    def _check_terms(
        self,
        request: DocumentGenerationRequest,
        plan: DocumentPlan,
        draft: DocumentDraft,
        evidence_pack: EvidencePack,
    ) -> list[DraftWarning]:
        warnings: list[DraftWarning] = []
        preferred_terms = {
            *[action.verb for action in evidence_pack.structured_case.actions],
            *[obj.name for obj in evidence_pack.structured_case.objects],
        }
        preferred_terms.discard("")
        if preferred_terms:
            combined_text = " ".join(section.text for section in draft.sections)
            missing_terms = [term for term in sorted(preferred_terms) if term and term not in combined_text]
            if missing_terms:
                first_section = draft.sections[0].section_id if draft.sections else plan.sections[0].section_id
                warnings.append(
                    DraftWarning(
                        code="term_coverage_gap",
                        severity="warning",
                        message=f"핵심 용어가 초안에 충분히 반영되지 않았습니다: {', '.join(missing_terms[:4])}",
                        section_id=first_section,
                        patch=DraftPatch(
                            section_id=first_section,
                            issue_code="term_coverage_gap",
                            instruction="핵심 용어를 명시해 용어 일관성을 높입니다.",
                            replacement_text=f"핵심 용어 {', '.join(missing_terms[:4])} 를 해당 문단에 반영하세요.",
                        ),
                    )
                )

        replacements = TERM_REPLACEMENTS.get(request.user_intent.doc_type, {})
        for section in draft.sections:
            for wrong, preferred in replacements.items():
                if wrong in section.text:
                    warnings.append(
                        DraftWarning(
                            code="term_inconsistency",
                            severity="warning",
                            message=f"{section.section_id} 섹션에서 {wrong} 대신 {preferred} 표현을 검토하세요.",
                            section_id=section.section_id,
                            patch=DraftPatch(
                                section_id=section.section_id,
                                issue_code="term_inconsistency",
                                instruction="문서 유형에 맞는 용어로 바꿉니다.",
                                target_excerpt=wrong,
                                replacement_text=preferred,
                            ),
                        )
                    )

        section_by_id = {section.section_id: section for section in draft.sections}
        for section_plan in plan.sections:
            draft_section = section_by_id.get(section_plan.section_id)
            if draft_section is None:
                continue
            for prohibited in section_plan.prohibited_phrases:
                if prohibited and prohibited in draft_section.text:
                    warnings.append(
                        DraftWarning(
                            code="prohibited_phrase",
                            severity="warning",
                            message=f"{draft_section.section_id} 섹션에 금지 표현 {prohibited} 이 포함되어 있습니다.",
                            section_id=draft_section.section_id,
                            patch=DraftPatch(
                                section_id=draft_section.section_id,
                                issue_code="prohibited_phrase",
                                instruction="금지 표현을 중립적 표현으로 바꿉니다.",
                                target_excerpt=prohibited,
                                replacement_text="현재 자료상",
                            ),
                        )
                    )
        return warnings
