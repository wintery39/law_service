from __future__ import annotations

from typing import Any

from schemas import (
    DocumentGenerationRequest,
    DocumentPlan,
    EvidencePack,
    EvidenceType,
    ObservationContext,
    SectionPlan,
)
from storage.observability import get_logger, log_info


logger = get_logger(__name__)

PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "fact_summary": {
        "title": "사실관계 정리서",
        "sections": [
            {
                "section_id": "issue_summary",
                "title": "사안 개요",
                "purpose": "사안의 핵심 사실과 쟁점을 짧게 정리한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.FORM],
                "seed_keywords": ["사실관계", "쟁점", "행위", "객체"],
                "prohibited_phrases": ["명백히", "확정적으로"],
            },
            {
                "section_id": "chronology",
                "title": "주요 경위",
                "purpose": "발생 시점, 장소, 행위, 대상의 순서를 정리한다.",
                "required_evidence_types": [EvidenceType.FORM, EvidenceType.REGULATION],
                "seed_keywords": ["시점", "장소", "경위", "행위"],
                "prohibited_phrases": ["추정컨대"],
            },
            {
                "section_id": "legal_points",
                "title": "검토 필요 근거",
                "purpose": "확인된 사실과 직접 연결되는 근거를 유형별로 적시한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.CASE],
                "seed_keywords": ["근거", "법령", "판단례", "쟁점"],
                "prohibited_phrases": ["무조건"],
            },
            {
                "section_id": "open_points",
                "title": "추가 확인 필요사항",
                "purpose": "누락 정보와 추가 증빙 필요사항을 분리해 적는다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["누락", "추가확인", "증빙"],
                "prohibited_phrases": [],
            },
        ],
    },
    "disciplinary_opinion": {
        "title": "징계 의견서",
        "sections": [
            {
                "section_id": "violation_summary",
                "title": "위반행위 요지",
                "purpose": "위반행위를 징계 관점에서 요약한다.",
                "required_evidence_types": [EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["징계", "복무", "위반행위"],
                "prohibited_phrases": ["유죄가 확정된다"],
            },
            {
                "section_id": "applicable_rules",
                "title": "적용 규정",
                "purpose": "적용 가능한 규정과 관련 법령을 정리한다.",
                "required_evidence_types": [EvidenceType.REGULATION, EvidenceType.LAW],
                "seed_keywords": ["적용규정", "복무규율", "법령"],
                "prohibited_phrases": ["형사처벌이 당연하다"],
            },
            {
                "section_id": "mitigation_aggravation",
                "title": "정상 및 가중요소",
                "purpose": "정상참작과 불리한 사정을 나눠 검토한다.",
                "required_evidence_types": [EvidenceType.CASE, EvidenceType.REGULATION],
                "seed_keywords": ["정상참작", "반성", "반복성", "지휘체계"],
                "prohibited_phrases": ["반드시 파면"],
            },
            {
                "section_id": "opinion",
                "title": "종합 의견",
                "purpose": "징계 필요성, 추가 조사 필요성, 문서 작성 유의사항을 제시한다.",
                "required_evidence_types": [EvidenceType.FORM, EvidenceType.REGULATION],
                "seed_keywords": ["의견", "추가조사", "권고"],
                "prohibited_phrases": ["결론적으로 유죄"],
            },
        ],
    },
    "defense_draft": {
        "title": "항변서 초안",
        "sections": [
            {
                "section_id": "position",
                "title": "기본 입장",
                "purpose": "주장 구조와 다투는 범위를 분명히 한다.",
                "required_evidence_types": [EvidenceType.FORM, EvidenceType.CASE],
                "seed_keywords": ["주장", "다툼", "입장"],
                "prohibited_phrases": ["완전히 허위다"],
            },
            {
                "section_id": "facts",
                "title": "사실관계 정리",
                "purpose": "유리한 사실과 아직 불명확한 사실을 구분한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.FORM],
                "seed_keywords": ["사실관계", "경위", "불명확"],
                "prohibited_phrases": ["확정적으로"],
            },
            {
                "section_id": "arguments",
                "title": "절차 및 법리 항변",
                "purpose": "절차상 하자 또는 법리상 쟁점을 구조화한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.CASE, EvidenceType.REGULATION],
                "seed_keywords": ["절차", "법리", "항변", "하자"],
                "prohibited_phrases": ["패소가 확실하다"],
            },
            {
                "section_id": "request",
                "title": "요청사항",
                "purpose": "보완 조사나 처분 재검토 등 요청을 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["요청", "재검토", "보완조사"],
                "prohibited_phrases": ["즉시 기각"],
            },
        ],
    },
}


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class DocumentPlanner:
    def create_plan(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        checklist_missing_info: list[str],
        context: ObservationContext,
    ) -> DocumentPlan:
        template = PLAN_TEMPLATES[request.user_intent.doc_type]
        structured_case = evidence_pack.structured_case
        base_keywords = _unique_strings(
            [
                *structured_case.legal_terms,
                *structured_case.keyphrases,
                *(action.verb for action in structured_case.actions),
                *(obj.name for obj in structured_case.objects),
                *evidence_pack.route_labels,
            ]
        )
        evidence_ids_by_type = {
            EvidenceType.LAW: [item.evidence_id for item in evidence_pack.laws],
            EvidenceType.CASE: [item.evidence_id for item in evidence_pack.cases],
            EvidenceType.REGULATION: [item.evidence_id for item in evidence_pack.regulations],
            EvidenceType.FORM: [item.evidence_id for item in evidence_pack.forms],
        }

        sections: list[SectionPlan] = []
        for spec in template["sections"]:
            keyphrases = _unique_strings([*spec["seed_keywords"], *base_keywords[:6], *request.constraints.extra_instructions[:2]])
            required_evidence_ids: list[str] = []
            for evidence_type in spec["required_evidence_types"]:
                required_evidence_ids.extend(evidence_ids_by_type.get(evidence_type, [])[:1])
            sections.append(
                SectionPlan(
                    section_id=spec["section_id"],
                    title=spec["title"],
                    purpose=spec["purpose"],
                    keyphrases=keyphrases[:8],
                    required_evidence_types=spec["required_evidence_types"],
                    required_evidence_ids=_unique_strings(required_evidence_ids),
                    prohibited_phrases=_unique_strings(
                        [*spec["prohibited_phrases"], *request.constraints.prohibited_phrases]
                    ),
                )
            )

        required_section_ids = {section.section_id for section in sections}
        for custom_section in request.constraints.required_sections:
            if custom_section in required_section_ids:
                continue
            sections.append(
                SectionPlan(
                    section_id=custom_section,
                    title=custom_section.replace("_", " ").title(),
                    purpose="사용자 제약에서 지정한 추가 섹션이다.",
                    keyphrases=base_keywords[:6],
                    required_evidence_types=[EvidenceType.FORM],
                    required_evidence_ids=evidence_ids_by_type.get(EvidenceType.FORM, [])[:1],
                    prohibited_phrases=request.constraints.prohibited_phrases,
                )
            )

        notes = []
        if checklist_missing_info:
            notes.append(f"누락 정보: {', '.join(checklist_missing_info)}")
        if request.constraints.extra_instructions:
            notes.append(f"추가 지시: {', '.join(request.constraints.extra_instructions)}")

        additional_retrieval_keywords = _unique_strings(
            [keyword for section in sections for keyword in section.keyphrases]
        )[:10]
        plan = DocumentPlan(
            doc_type=request.user_intent.doc_type,
            title=template["title"],
            sections=sections,
            additional_retrieval_keywords=additional_retrieval_keywords,
            notes=notes,
        )
        log_info(
            logger,
            "document plan created",
            context,
            doc_type=plan.doc_type,
            section_count=len(plan.sections),
            retrieval_keywords=len(plan.additional_retrieval_keywords),
        )
        return plan
