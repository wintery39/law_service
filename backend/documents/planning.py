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
PROMPT_PROFILE_PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "fact_finding_report": {
        "title": "사실결과조사보고",
        "sections": [
            {
                "section_id": "overview",
                "title": "개요",
                "purpose": "조사 목적과 사건 개요를 보고문체로 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["조사 목적", "사건 개요", "조사 배경"],
                "prohibited_phrases": ["추정컨대", "명백히"],
            },
            {
                "section_id": "subject_profile",
                "title": "징계혐의자 인적사항",
                "purpose": "조사대상자의 기본 인적사항과 사건명을 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["소속", "직위", "직급", "성명", "사건명"],
                "prohibited_phrases": ["불성실", "비난"],
            },
            {
                "section_id": "allegations",
                "title": "징계혐의사실",
                "purpose": "혐의사실을 시간순으로 정리하고 날짜, 시간, 장소, 행위, 결과를 빠짐없이 적는다.",
                "required_evidence_types": [EvidenceType.FORM, EvidenceType.REGULATION],
                "seed_keywords": ["혐의사실", "시간순", "날짜", "장소", "행위", "결과"],
                "prohibited_phrases": ["확정적으로"],
            },
            {
                "section_id": "findings",
                "title": "사실조사 결과",
                "purpose": "인정되는 사실, 다툼이 있는 사항, 확인되지 않은 사항을 구분한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["인정 사실", "다툼", "확인되지 않음"],
                "prohibited_phrases": ["단정적으로"],
            },
            {
                "section_id": "evidence_summary",
                "title": "증거요지",
                "purpose": "증거와 각 증거로 확인되는 내용을 대응시켜 적는다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.CASE, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["증거", "증빙자료", "진술", "기록", "확인되는 내용"],
                "prohibited_phrases": ["입증되었다"],
            },
            {
                "section_id": "mitigating_aggravating",
                "title": "정상자료",
                "purpose": "유리한 정상과 불리한 정상을 구분해 적는다.",
                "required_evidence_types": [EvidenceType.CASE, EvidenceType.FORM],
                "seed_keywords": ["정상자료", "유리한 정상", "불리한 정상"],
                "prohibited_phrases": ["반드시"],
            },
            {
                "section_id": "integrated_opinion",
                "title": "종합의견",
                "purpose": "확인된 범위의 사실과 쟁점을 요약해 종합 의견을 제시한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.REGULATION],
                "seed_keywords": ["종합의견", "쟁점", "요약"],
                "prohibited_phrases": ["유죄", "처벌"],
            },
            {
                "section_id": "recommendation",
                "title": "건의",
                "purpose": "징계의결 요구 여부 또는 추가 조사 필요 여부를 제시한다.",
                "required_evidence_types": [EvidenceType.FORM, EvidenceType.REGULATION],
                "seed_keywords": ["건의", "징계의결 요구", "추가 조사"],
                "prohibited_phrases": ["즉시 징계"],
            },
            {
                "section_id": "attachments",
                "title": "첨부자료 목록",
                "purpose": "첨부자료 및 증빙자료 목록을 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["첨부자료", "목록", "증빙자료"],
                "prohibited_phrases": [],
            },
        ],
    },
    "committee_reference": {
        "title": "징계위원회 참고자료",
        "sections": [
            {
                "section_id": "case_overview",
                "title": "사건 개요",
                "purpose": "사건명, 심의 일시, 심의 대상자, 사건 요약을 심의 참고용으로 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["사건명", "심의 일시", "심의 대상자", "사건 요약"],
                "prohibited_phrases": ["최종 결론"],
            },
            {
                "section_id": "subject_profile",
                "title": "심의대상자 인적사항",
                "purpose": "심의대상자의 소속, 직위/직급, 성명을 최소한으로 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["소속", "직위", "직급", "성명"],
                "prohibited_phrases": ["비난"],
            },
            {
                "section_id": "fact_summary",
                "title": "징계혐의 사실 요약",
                "purpose": "징계혐의 사실을 시간순으로 3개 이내로 요약한다.",
                "required_evidence_types": [EvidenceType.FORM, EvidenceType.REGULATION],
                "seed_keywords": ["혐의사실", "시간순", "사실관계"],
                "prohibited_phrases": ["확정적으로"],
            },
            {
                "section_id": "issues",
                "title": "주요 쟁점",
                "purpose": "위원회 심의에 필요한 주요 쟁점을 분리해 제시한다.",
                "required_evidence_types": [EvidenceType.CASE, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["쟁점", "심의", "판단 포인트"],
                "prohibited_phrases": ["유죄"],
            },
            {
                "section_id": "evidence_summary",
                "title": "증거자료 요약",
                "purpose": "주요 증거와 각 증거가 입증하는 내용을 대응시켜 적는다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.CASE, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["증거자료", "입증", "증빙"],
                "prohibited_phrases": ["완전히 입증"],
            },
            {
                "section_id": "statements",
                "title": "당사자 진술 및 소명 요지",
                "purpose": "대상자와 참고인/관계인의 진술 요지를 구분하고 다툼 지점을 적는다.",
                "required_evidence_types": [EvidenceType.CASE, EvidenceType.FORM],
                "seed_keywords": ["소명", "진술", "참고인", "다툼"],
                "prohibited_phrases": ["허위"],
            },
            {
                "section_id": "mitigating_aggravating",
                "title": "정상참작 사항",
                "purpose": "유리한 정상과 불리한 정상을 나눠 적는다.",
                "required_evidence_types": [EvidenceType.CASE, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["정상참작", "유리한 정상", "불리한 정상"],
                "prohibited_phrases": ["반드시 중징계"],
            },
            {
                "section_id": "applicable_rules",
                "title": "적용 가능 규정",
                "purpose": "관련 법령/규정과 양정 검토 포인트를 정리한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["관련 규정", "양정", "검토 포인트"],
                "prohibited_phrases": ["당연히 징계"],
            },
            {
                "section_id": "judgment_points",
                "title": "위원회 판단 포인트",
                "purpose": "사실인정, 양정 판단, 추가 확인 필요 사항을 분리한다.",
                "required_evidence_types": [EvidenceType.CASE, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["사실인정", "양정 판단", "추가 확인"],
                "prohibited_phrases": ["최종적으로"],
            },
            {
                "section_id": "attachments",
                "title": "첨부자료 목록",
                "purpose": "위원회에 배포할 첨부자료 목록을 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["첨부자료", "목록", "배포자료"],
                "prohibited_phrases": [],
            },
        ],
    },
    "disciplinary_resolution": {
        "title": "징계의결서",
        "sections": [
            {
                "section_id": "subject_profile",
                "title": "징계혐의자 인적사항",
                "purpose": "피징계자의 소속, 직위(직급), 성명을 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["피징계자", "소속", "직위", "직급", "성명"],
                "prohibited_phrases": ["비난"],
            },
            {
                "section_id": "decision_order",
                "title": "의결주문",
                "purpose": "최종 의결결론 또는 처분 주문을 명확히 적는다.",
                "required_evidence_types": [EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["의결주문", "처분", "징계결론"],
                "prohibited_phrases": ["추정컨대"],
            },
            {
                "section_id": "reasoning",
                "title": "이유",
                "purpose": "징계의 원인이 된 사실, 증거 판단, 적용 규정, 양정 판단을 순서대로 정리한다.",
                "required_evidence_types": [EvidenceType.LAW, EvidenceType.CASE, EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["인정 사실", "증거 판단", "적용 규정", "양정 판단"],
                "prohibited_phrases": ["증거 없이"],
            },
            {
                "section_id": "decision_date",
                "title": "의결일자",
                "purpose": "의결일자를 공식 문서 형식으로 적는다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["의결일자", "의결일"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "committee_name",
                "title": "징계위원회명",
                "purpose": "의결한 징계위원회 명칭을 적는다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["징계위원회명", "위원회명"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "committee_members",
                "title": "위원장 및 위원 표시",
                "purpose": "위원장 및 위원 표시 또는 직인/서명 표시를 적는다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["위원장", "위원", "직인", "서명"],
                "prohibited_phrases": [],
            },
        ],
    },
    "attendance_notice": {
        "title": "출석통지서",
        "sections": [
            {
                "section_id": "personal_info",
                "title": "인적사항",
                "purpose": "수신자의 인적사항을 통지서 형식에 맞춰 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["성명", "소속", "직위", "직급", "주소"],
                "prohibited_phrases": ["추정컨대"],
            },
            {
                "section_id": "appearance_reason",
                "title": "출석 이유",
                "purpose": "징계혐의 또는 심의대상 사유를 방어권 보장에 필요한 정도로 특정한다.",
                "required_evidence_types": [EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["징계혐의", "심의대상", "출석 요구 사유"],
                "prohibited_phrases": ["감정적으로"],
            },
            {
                "section_id": "appearance_datetime",
                "title": "출석 일시",
                "purpose": "출석 일시를 연월일시분 형식으로 명확히 기재한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["출석 일시", "연월일", "시각"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "appearance_location",
                "title": "출석 장소",
                "purpose": "회의실명 또는 주소를 포함해 출석 장소를 특정한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["출석 장소", "회의실", "주소"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "notes",
                "title": "유의사항",
                "purpose": "진술권, 서면진술, 불출석 시 처리, 증빙자료 제출 안내를 빠짐없이 넣는다.",
                "required_evidence_types": [EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["진술권", "서면진술", "불출석", "소명자료"],
                "prohibited_phrases": ["불이익을 감수"],
            },
            {
                "section_id": "notice_statement",
                "title": "통지 문구",
                "purpose": "관련 규정에 따른 통지 문구를 명확하게 적는다.",
                "required_evidence_types": [EvidenceType.REGULATION, EvidenceType.FORM],
                "seed_keywords": ["관련 규정", "통지"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "sender",
                "title": "발신",
                "purpose": "통지일, 징계위원회명, 청인 또는 직인 표시를 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["통지일", "징계위원회명", "기관명", "직인"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "recipient",
                "title": "수신",
                "purpose": "수신자를 명확하게 적는다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["수신", "귀하"],
                "prohibited_phrases": [],
            },
            {
                "section_id": "appendix",
                "title": "별첨",
                "purpose": "필요 시 진술권 포기서 양식 등 별첨 자료를 정리한다.",
                "required_evidence_types": [EvidenceType.FORM],
                "seed_keywords": ["별첨", "진술권 포기서", "양식"],
                "prohibited_phrases": [],
            },
        ],
    }
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
    def _select_template(self, request: DocumentGenerationRequest) -> dict[str, Any]:
        prompt_profile = request.constraints.prompt_profile
        if prompt_profile and prompt_profile in PROMPT_PROFILE_PLAN_TEMPLATES:
            return PROMPT_PROFILE_PLAN_TEMPLATES[prompt_profile]
        return PLAN_TEMPLATES[request.user_intent.doc_type]

    def create_plan(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        checklist_missing_info: list[str],
        context: ObservationContext,
    ) -> DocumentPlan:
        template = self._select_template(request)
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
