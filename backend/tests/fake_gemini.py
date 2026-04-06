from __future__ import annotations

from dataclasses import dataclass

from documents import DocumentGenerationService, DocumentGenerationSettings, EvidenceCollector, InProcessRelatedArticlesClient
from documents.gemini import GeminiGeneratedSection
from schemas import DocumentGenerationRequest, DocumentPlan, EvidencePack, ObservationContext


FIELD_MAP = {
    "사건 제목": "title",
    "사건 유형": "case_type",
    "발생 일시": "occurred_at",
    "발생 장소": "location",
    "작성자": "author",
    "관련자": "related_people",
    "사건 개요": "summary",
    "상세 사실관계": "details",
    "첨부자료 요약": "attachment_summary",
}

RANK_TOKENS = {
    "이병",
    "일병",
    "상병",
    "병장",
    "하사",
    "중사",
    "상사",
    "원사",
    "준위",
    "소위",
    "중위",
    "대위",
    "소령",
    "중령",
    "대령",
}


def _parse_fields(user_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in user_text.splitlines():
        prefix, separator, value = line.partition(":")
        if not separator:
            continue
        key = FIELD_MAP.get(prefix.strip())
        if key is None:
            continue
        fields[key] = value.strip()
    return fields


def _split_sentences(text: str | None) -> list[str]:
    if not text:
        return []
    normalized = text.replace("\n", " ").strip()
    return [sentence.strip(" .") for sentence in normalized.split(".") if sentence.strip(" .")]


def _parse_primary_person(raw_value: str | None) -> dict[str, str]:
    if not raw_value:
        return {"raw": "자료상 명확하지 않음", "rank": "자료상 명확하지 않음", "name": "자료상 명확하지 않음"}
    first = raw_value.split(",")[0].strip()
    parts = first.split()
    if len(parts) >= 2:
        if parts[0] in RANK_TOKENS:
            return {"raw": first, "rank": parts[0], "name": " ".join(parts[1:])}
        if parts[-1] in RANK_TOKENS:
            return {"raw": first, "rank": parts[-1], "name": " ".join(parts[:-1])}
    return {"raw": first, "rank": "자료상 명확하지 않음", "name": first}


def _summary_text(fields: dict[str, str]) -> str:
    return fields.get("summary") or "자료상 명확하지 않음"


def _detail_sentences(fields: dict[str, str]) -> list[str]:
    details = _split_sentences(fields.get("details"))
    if details:
        return details
    summary = _split_sentences(fields.get("summary"))
    return summary or ["자료상 명확하지 않음"]


def _build_generic_text(doc_type: str, section_id: str, title: str, fields: dict[str, str]) -> str:
    summary = _summary_text(fields)
    details = _detail_sentences(fields)
    if doc_type == "fact_summary":
        mapping = {
            "issue_summary": f"현재까지 확인된 자료를 기준으로 사안의 핵심 사실과 쟁점은 다음과 같습니다. {summary}",
            "chronology": f"1. {details[0]}\n2. {details[1] if len(details) > 1 else '추가 경위 확인이 필요합니다.'}",
            "legal_points": "직접 검토가 필요한 근거는 사전통지, 의견제출, 절차 준수 여부입니다.",
            "open_points": "- 추가 확인 필요: 구체적 경위와 관련 자료 보강",
        }
        return mapping.get(section_id, f"{title} 관련 정리입니다.")
    if doc_type == "disciplinary_opinion":
        mapping = {
            "violation_summary": f"징계 검토를 위해 위반행위를 요약하면 다음과 같습니다. {summary}",
            "applicable_rules": "현재 적용 가능성이 높은 규정과 법령을 중심으로 징계 검토 기준을 정리합니다.",
            "mitigation_aggravation": "정상참작 요소와 불리한 요소를 구분해 추가 확인이 필요합니다.",
            "opinion": "현재 자료만으로도 징계 검토 필요성은 충분히 제기됩니다.",
        }
        return mapping.get(section_id, f"{title} 관련 검토 내용입니다.")
    mapping = {
        "position": "본 초안의 기본 입장은 혐의 사실이 충분히 소명되지 않았다는 점입니다.",
        "facts": f"다툼의 전제가 되는 사실관계는 다음과 같습니다. {details[0]}",
        "arguments": "피해자 진술 불일치와 보강 증거 부족을 중심으로 항변합니다.",
        "request": "추가 조사와 불리한 단정의 유보를 요청합니다.",
    }
    return mapping.get(section_id, f"{title} 관련 항변 내용입니다.")


def _build_profile_specific_text(
    prompt_profile: str,
    section_id: str,
    fields: dict[str, str],
) -> tuple[str, list[str]]:
    primary_person = _parse_primary_person(fields.get("related_people"))
    details = _detail_sentences(fields)
    title = fields.get("title") or "자료상 명확하지 않음"
    first_detail = details[0]
    second_detail = details[1] if len(details) > 1 else "자료상 명확하지 않음"

    if prompt_profile == "fact_finding_report":
        mapping = {
            "overview": f"본 보고서는 {title}의 사실관계를 정리한 초안입니다.",
            "subject_profile": "\n".join(
                [
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위/직급: {primary_person['rank']}",
                    f"- 성명: {primary_person['name']}",
                    f"- 사건명: {title}",
                ]
            ),
            "allegations": f"- 혐의사실 1: {first_detail}\n- 혐의사실 2: {second_detail}",
            "findings": (
                f"- 인정되는 사실: {first_detail}\n"
                f"- 다툼이 있는 사항: {second_detail}\n"
                "- 확인되지 않은 사항: 추가 진술과 승인 여부 확인이 필요합니다."
            ),
            "evidence_summary": "- 증거 1: CCTV 캡처본\n- 증거 2: 출입기록\n- 각 증거로 확인되는 내용: 핵심 사실관계를 교차 확인했습니다.",
            "mitigating_aggravating": "- 유리한 정상: 자료상 명확하지 않음\n- 불리한 정상: 절차 위반 가능성이 있습니다.",
            "integrated_opinion": f"현재 자료에 따르면 {first_detail}",
            "recommendation": "- 징계의결 요구 여부 또는 추가 조사 필요 여부: 보강 조사가 필요합니다.",
            "attachments": "- CCTV 캡처본\n- 출입기록",
        }
        return mapping.get(section_id, "자료상 명확하지 않음"), []

    if prompt_profile == "committee_reference":
        mapping = {
            "case_overview": "\n".join(
                [
                    f"- 사건명: {title}",
                    "- 심의 일시: 자료상 명확하지 않음",
                    f"- 심의 대상자: {primary_person['raw']}",
                    f"- 사건 요약: {_summary_text(fields)}",
                ]
            ),
            "subject_profile": "\n".join(
                [
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위/직급: {primary_person['rank']}",
                    f"- 성명: {primary_person['name']}",
                ]
            ),
            "fact_summary": f"- 사실관계 1: {first_detail}\n- 사실관계 2: {second_detail}\n- 사실관계 3: 추가 확인 필요",
            "issues": "- 쟁점 1: 승인 여부\n- 쟁점 2: 사실관계 범위\n- 쟁점 3: 양정 요소",
            "evidence_summary": "- 증거 1: 첨부자료\n- 증거 2: 관련 규정\n- 증거 3: 사실관계 진술",
            "statements": "- 대상자 진술 요지: 자료상 명확하지 않음\n- 참고인/관계인 진술 요지: 자료상 명확하지 않음\n- 다툼이 있는 부분: 추가 확인 필요",
            "mitigating_aggravating": "- 유리한 정상: 자료상 명확하지 않음\n- 불리한 정상: 자료상 명확하지 않음",
            "applicable_rules": "- 관련 법령/규정: 군인 징계령 및 시행규칙 검토\n- 검토 포인트: 위반 성립 여부와 양정 판단",
            "judgment_points": "- 사실인정 포인트: 핵심 사실관계 정리\n- 양정 판단 포인트: 조직 영향과 반복성\n- 추가 확인 필요 사항: 심의 일시와 진술 보강",
            "attachments": "- 첨부자료 요약서\n- 참고 규정 목록",
        }
        return mapping.get(section_id, "자료상 명확하지 않음"), []

    if prompt_profile == "disciplinary_resolution":
        mapping = {
            "subject_profile": "\n".join(
                [
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위(직급): {primary_person['rank']}",
                    f"- 성명: {primary_person['name']}",
                ]
            ),
            "decision_order": "- 자료상 명확하지 않음",
            "reasoning": "\n".join(
                [
                    "가. 인정되는 사실",
                    f"{first_detail}.",
                    "나. 증거의 판단",
                    "현재 제출된 자료를 종합해 판단합니다.",
                    "다. 적용 규정",
                    "군인 징계 관련 규정을 중심으로 검토합니다.",
                    "라. 양정 판단",
                    "- 비위의 정도: 자료상 명확하지 않음.",
                    "- 고의/과실: 자료상 명확하지 않음.",
                    "- 조직 영향: 자료상 명확하지 않음.",
                    "- 유리한 정상: 자료상 명확하지 않음.",
                    "- 불리한 정상: 자료상 명확하지 않음.",
                ]
            ),
            "decision_date": "- 의결일자: 자료상 명확하지 않음",
            "committee_name": "- 징계위원회명: 자료상 명확하지 않음",
            "committee_members": "- 위원장 및 위원 표시: 자료상 명확하지 않음",
        }
        return mapping.get(section_id, "자료상 명확하지 않음"), []

    mapping = {
        "personal_info": "\n".join(
            [
                f"- 성명: {primary_person['name']}",
                "- 소속: 자료상 명확하지 않음",
                f"- 직위(직급): {primary_person['rank']}",
                "- 주소: 자료상 명확하지 않음",
            ]
        ),
        "appearance_reason": first_detail,
        "appearance_datetime": "- 자료상 명확하지 않음",
        "appearance_location": "- 자료상 명확하지 않음",
        "notes": "\n".join(
            [
                "- 출석하여 진술하기를 원하지 않는 경우 진술권 포기서를 제출할 수 있음",
                "- 서면진술을 원할 경우 지정 기한까지 진술서를 제출할 수 있음",
                "- 정당한 사유 없이 불출석하고 서면진술도 없으면 진술 의사가 없는 것으로 보고 처리될 수 있음",
                "- 필요 시 소명자료 또는 증빙자료를 제출할 수 있음",
            ]
        ),
        "notice_statement": "- 관련 규정에 따라 위와 같이 귀하의 출석을 통지합니다.",
        "sender": "- 통지일: 자료상 명확하지 않음\n- 징계위원회명: 자료상 명확하지 않음\n- 위원회 청인 또는 직인 표시",
        "recipient": "- 귀하",
        "appendix": "- 필요 시 진술권 포기서 양식",
    }
    return mapping.get(section_id, "자료상 명확하지 않음"), []


@dataclass
class FakeGeminiGenerator:
    configured: bool = True

    def is_configured(self) -> bool:
        return self.configured

    async def aclose(self) -> None:
        return None

    async def generate_sections(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
        context: ObservationContext,
    ) -> list[GeminiGeneratedSection]:
        del evidence_pack, context
        fields = _parse_fields(request.user_text)
        prompt_profile = request.constraints.prompt_profile
        sections: list[GeminiGeneratedSection] = []
        for section_plan in plan.sections:
            if prompt_profile:
                text, open_issues = _build_profile_specific_text(prompt_profile, section_plan.section_id, fields)
            else:
                text = _build_generic_text(
                    request.user_intent.doc_type,
                    section_plan.section_id,
                    section_plan.title,
                    fields,
                )
                open_issues = []
            sections.append(
                GeminiGeneratedSection(
                    section_id=section_plan.section_id,
                    text=text,
                    open_issues=open_issues,
                )
            )
        return sections


def build_fake_document_service(related_articles_service, repository, text_search_store) -> DocumentGenerationService:
    return DocumentGenerationService(
        evidence_collector=EvidenceCollector(
            related_articles_client=InProcessRelatedArticlesClient(related_articles_service),
            repository=repository,
            text_search_store=text_search_store,
        ),
        gemini_generator=FakeGeminiGenerator(),
        settings=DocumentGenerationSettings(),
    )
