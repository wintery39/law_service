from __future__ import annotations

from datetime import datetime
from functools import lru_cache

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

COMMON_RANK_TOKENS = {
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
    "준장",
    "소장",
    "중장",
    "대장",
    "원수",
    "사원",
    "주임",
    "대리",
    "과장",
    "차장",
    "부장",
    "실장",
    "팀장",
    "주무관",
    "서기",
    "주사",
    "주사보",
    "사무관",
    "서기관",
    "부이사관",
    "이사관",
    "관리관",
    "연구사",
    "연구관",
    "교사",
    "교감",
    "교장",
    "경위",
    "경감",
    "경정",
    "총경",
    "경무관",
    "치안감",
    "치안정감",
    "치안총감",
}

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

NARRATIVE_FIELD_MAPPING = {
    "사건 제목": "title",
    "사건 유형": "case_type",
    "발생 일시": "occurred_at",
    "발생 장소": "location",
    "작성자": "author",
    "관련자": "related_people",
    "사건 개요": "summary",
    "상세 사실관계": "details",
    "첨부자료 요약": "attachment_summary",
    "출석 일시": "appearance_datetime",
    "출석 장소": "appearance_location",
    "징계위원회명": "committee_name",
    "통지일": "notice_date",
    "의결주문": "decision_order",
    "최종 의결결론": "decision_order",
    "인정 사실": "recognized_fact",
    "의결일자": "decision_date",
    "위원장 및 위원 표시": "committee_members",
}


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


@lru_cache(maxsize=256)
def _parse_narrative_fields_cached(narrative: str) -> tuple[tuple[str, str], ...]:
    fields: dict[str, str] = {}
    for line in narrative.splitlines():
        prefix, _, value = line.partition(":")
        key = NARRATIVE_FIELD_MAPPING.get(prefix.strip())
        if key is not None:
            fields[key] = value.strip()
    return tuple(fields.items())


@lru_cache(maxsize=256)
def _parse_related_people_cached(raw_value: str) -> tuple[tuple[str, str, str], ...]:
    people: list[tuple[str, str, str]] = []
    for item in [value.strip() for value in raw_value.split(",") if value.strip()]:
        parts = item.split()
        rank = "자료상 명확하지 않음"
        name = item
        if len(parts) >= 2:
            first_token = parts[0]
            last_token = parts[-1]
            if first_token in COMMON_RANK_TOKENS and last_token not in COMMON_RANK_TOKENS:
                rank = first_token
                name = " ".join(parts[1:])
            elif last_token in COMMON_RANK_TOKENS and first_token not in COMMON_RANK_TOKENS:
                rank = last_token
                name = " ".join(parts[:-1])
        people.append((item, rank, name))
    return tuple(people)


@lru_cache(maxsize=256)
def _split_sentences_cached(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    return tuple(sentence.strip(" .") for sentence in text.replace("\n", " ").split(".") if sentence.strip(" ."))


class DocumentSectionGenerator:
    def generate_section(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        section_plan: SectionPlan,
        generated_sections: list[SectionDraft],
        context: ObservationContext,
    ) -> SectionDraft:
        if request.constraints.prompt_profile == "fact_finding_report":
            return self._generate_fact_finding_report_section(request, evidence_pack, section_plan, context)
        if request.constraints.prompt_profile == "committee_reference":
            return self._generate_committee_reference_section(request, evidence_pack, section_plan, context)
        if request.constraints.prompt_profile == "disciplinary_resolution":
            return self._generate_disciplinary_resolution_section(request, evidence_pack, section_plan, context)
        if request.constraints.prompt_profile == "attendance_notice":
            return self._generate_attendance_notice_section(request, evidence_pack, section_plan, context)

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

    def _generate_disciplinary_resolution_section(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        section_plan: SectionPlan,
        context: ObservationContext,
    ) -> SectionDraft:
        structured_case = evidence_pack.structured_case
        evidence_items = self._select_evidence(section_plan, evidence_pack)
        citations = [item.evidence_id for item in evidence_items]
        narrative_fields = self._parse_narrative_fields(request.user_text)
        related_people = self._parse_related_people(narrative_fields.get("related_people", ""))
        primary_person = related_people[0] if related_people else None
        first_fact = self._first_sentence(narrative_fields.get("details")) or self._first_sentence(narrative_fields.get("summary"))
        second_fact = self._second_sentence(narrative_fields.get("details"))
        occurred_at = self._normalize_occurred_at(narrative_fields.get("occurred_at"))
        location = narrative_fields.get("location") or (structured_case.place.name if structured_case.place else None) or "자료상 명확하지 않음"
        issue_text = self._build_issue_text(first_fact, occurred_at, location)
        dispute_text = self._build_dispute_text(second_fact)
        regulation_text = self._build_regulation_text(evidence_items)
        attachment_items = self._split_attachment_items(narrative_fields.get("attachment_summary"))
        decision_order = narrative_fields.get("decision_order") or "자료상 명확하지 않음"
        recognized_fact = narrative_fields.get("recognized_fact")
        decision_date = narrative_fields.get("decision_date") or "자료상 명확하지 않음"
        committee_name = narrative_fields.get("committee_name") or "자료상 명확하지 않음"
        committee_members = narrative_fields.get("committee_members") or "자료상 명확하지 않음"

        section_text_by_id = {
            "subject_profile": "\n".join(
                [
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위(직급): {primary_person['rank'] if primary_person else '자료상 명확하지 않음'}",
                    f"- 성명: {primary_person['name'] if primary_person else '자료상 명확하지 않음'}",
                ]
            ),
            "decision_order": f"- {decision_order}",
            "reasoning": "\n".join(
                [
                    "가. 인정되는 사실",
                    f"{self._default_text(recognized_fact or issue_text)}.",
                    "나. 증거의 판단",
                    self._build_evidence_judgment_text(attachment_items, evidence_items),
                    "다. 적용 규정",
                    f"{regulation_text}.",
                    "라. 양정 판단",
                    f"- 비위의 정도: {self._default_text(recognized_fact or issue_text)}.",
                    "- 고의/과실: 자료상 명확하지 않음.",
                    "- 조직 영향: 조직 운영과 절차 준수 여부에 미친 영향을 검토할 필요가 있음.",
                    "- 유리한 정상: 자료상 명확하지 않음.",
                    f"- 불리한 정상: {self._build_adverse_text(dispute_text)}.",
                ]
            ),
            "decision_date": f"- 의결일자: {decision_date}",
            "committee_name": f"- 징계위원회명: {committee_name}",
            "committee_members": f"- 위원장 및 위원 표시: {committee_members}",
        }
        section = SectionDraft(
            section_id=section_plan.section_id,
            title=section_plan.title,
            text=section_text_by_id.get(section_plan.section_id, "자료상 명확하지 않음"),
            citations=citations,
            open_issues=self._build_disciplinary_resolution_open_issues(
                primary_person=primary_person,
                decision_order=decision_order,
                decision_date=decision_date,
                committee_name=committee_name,
                committee_members=committee_members,
                second_fact=second_fact,
            ),
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

    def _generate_committee_reference_section(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        section_plan: SectionPlan,
        context: ObservationContext,
    ) -> SectionDraft:
        structured_case = evidence_pack.structured_case
        evidence_items = self._select_evidence(section_plan, evidence_pack)
        citations = [item.evidence_id for item in evidence_items]
        narrative_fields = self._parse_narrative_fields(request.user_text)
        related_people = self._parse_related_people(narrative_fields.get("related_people", ""))
        primary_person = related_people[0] if related_people else None
        occurred_at = self._normalize_occurred_at(narrative_fields.get("occurred_at"))
        location = narrative_fields.get("location") or (structured_case.place.name if structured_case.place else None) or "자료상 명확하지 않음"
        summary_text = self._default_text(self._first_sentence(narrative_fields.get("summary")))
        detail_sentences = self._split_sentences(narrative_fields.get("details"))
        fact_lines = self._build_committee_fact_lines(detail_sentences, occurred_at, location)
        dispute_text = self._build_dispute_text(detail_sentences[1] if len(detail_sentences) > 1 else None)
        attachment_items = self._split_attachment_items(narrative_fields.get("attachment_summary"))
        regulation_text = self._build_regulation_text(evidence_items)

        section_text_by_id = {
            "case_overview": "\n".join(
                [
                    f"- 사건명: {narrative_fields.get('title') or '자료상 명확하지 않음'}",
                    "- 심의 일시: 자료상 명확하지 않음",
                    f"- 심의 대상자: {primary_person['raw'] if primary_person else '자료상 명확하지 않음'}",
                    f"- 사건 요약: {summary_text}",
                ]
            ),
            "subject_profile": "\n".join(
                [
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위/직급: {primary_person['rank'] if primary_person else '자료상 명확하지 않음'}",
                    f"- 성명: {primary_person['name'] if primary_person else '자료상 명확하지 않음'}",
                ]
            ),
            "fact_summary": "\n".join(
                [f"- 사실관계 {index}: {line}" for index, line in enumerate(fact_lines, start=1)]
            ),
            "issues": "\n".join(
                [
                    f"- 쟁점 1: {self._build_committee_issue_line(dispute_text, 1)}",
                    f"- 쟁점 2: {self._build_committee_issue_line(dispute_text, 2)}",
                    f"- 쟁점 3: {self._build_committee_issue_line(dispute_text, 3)}",
                ]
            ),
            "evidence_summary": self._build_committee_evidence_summary_text(attachment_items, evidence_items, fact_lines),
            "statements": "\n".join(
                [
                    "- 대상자 진술 요지: 자료상 명확하지 않음",
                    "- 참고인/관계인 진술 요지: 자료상 명확하지 않음",
                    f"- 다툼이 있는 부분: {self._default_text(dispute_text)}",
                ]
            ),
            "mitigating_aggravating": "\n".join(
                [
                    "- 유리한 정상: 자료상 명확하지 않음",
                    f"- 불리한 정상: {self._build_adverse_text(dispute_text)}",
                ]
            ),
            "applicable_rules": "\n".join(
                [
                    f"- 관련 법령/규정: {regulation_text}",
                    "- 검토 포인트: 승인 절차 준수 여부, 관련 규정 위반 성립 여부, 행위의 반복성 및 조직 영향",
                ]
            ),
            "judgment_points": "\n".join(
                [
                    f"- 사실인정 포인트: {self._default_text(fact_lines[0])}",
                    "- 양정 판단 포인트: 위반 정도, 행위자의 역할, 승인 절차 위반 여부 및 조직 영향",
                    f"- 추가 확인 필요 사항: {self._build_unconfirmed_text(detail_sentences[1] if len(detail_sentences) > 1 else None)}",
                ]
            ),
            "attachments": self._build_attachment_section_text(attachment_items),
        }
        open_issues = self._build_committee_reference_open_issues(
            primary_person=primary_person,
            attachment_items=attachment_items,
            dispute_text=dispute_text,
        )
        section = SectionDraft(
            section_id=section_plan.section_id,
            title=section_plan.title,
            text=section_text_by_id.get(section_plan.section_id, "자료상 명확하지 않음"),
            citations=citations,
            open_issues=open_issues,
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

    def _generate_attendance_notice_section(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        section_plan: SectionPlan,
        context: ObservationContext,
    ) -> SectionDraft:
        evidence_items = self._select_evidence(section_plan, evidence_pack)
        citations = [item.evidence_id for item in evidence_items]
        narrative_fields = self._parse_narrative_fields(request.user_text)
        related_people = self._parse_related_people(narrative_fields.get("related_people", ""))
        primary_person = related_people[0] if related_people else None
        appearance_datetime = narrative_fields.get("appearance_datetime")
        appearance_location = narrative_fields.get("appearance_location") or "자료상 명확하지 않음"
        notice_date = narrative_fields.get("notice_date") or "자료상 명확하지 않음"
        committee_name = narrative_fields.get("committee_name") or "자료상 명확하지 않음"
        appearance_reason = self._first_sentence(narrative_fields.get("details")) or self._first_sentence(
            narrative_fields.get("summary")
        )

        section_text_by_id = {
            "personal_info": "\n".join(
                [
                    f"- 성명: {primary_person['name'] if primary_person else '자료상 명확하지 않음'}",
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위(직급): {primary_person['rank'] if primary_person else '자료상 명확하지 않음'}",
                    "- 주소: 자료상 명확하지 않음",
                ]
            ),
            "appearance_reason": self._default_text(appearance_reason),
            "appearance_datetime": f"- {self._format_notice_datetime(appearance_datetime)}",
            "appearance_location": f"- {appearance_location}",
            "notes": "\n".join(
                [
                    "- 출석하여 진술하기를 원하지 않는 경우 진술권 포기서를 제출할 수 있음",
                    "- 서면진술을 원할 경우 지정 기한까지 진술서를 제출할 수 있음",
                    "- 정당한 사유 없이 불출석하고 서면진술도 없으면 진술 의사가 없는 것으로 보고 처리될 수 있음",
                    "- 필요 시 소명자료 또는 증빙자료를 제출할 수 있음",
                ]
            ),
            "notice_statement": "- 관련 규정에 따라 위와 같이 귀하의 출석을 통지합니다.",
            "sender": "\n".join(
                [
                    f"- 통지일: {notice_date}",
                    f"- 징계위원회명: {committee_name}",
                    "- 위원회 청인 또는 직인 표시",
                ]
            ),
            "recipient": "- 귀하",
            "appendix": "- 필요 시 진술권 포기서 양식",
        }
        section = SectionDraft(
            section_id=section_plan.section_id,
            title=section_plan.title,
            text=section_text_by_id.get(section_plan.section_id, "자료상 명확하지 않음"),
            citations=citations,
            open_issues=self._build_attendance_notice_open_issues(
                primary_person=primary_person,
                appearance_datetime=appearance_datetime,
                appearance_location=appearance_location,
                committee_name=committee_name,
                notice_date=notice_date,
            ),
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

    def _generate_fact_finding_report_section(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        section_plan: SectionPlan,
        context: ObservationContext,
    ) -> SectionDraft:
        structured_case = evidence_pack.structured_case
        evidence_items = self._select_evidence(section_plan, evidence_pack)
        citations = [item.evidence_id for item in evidence_items]
        narrative_fields = self._parse_narrative_fields(request.user_text)
        related_people = self._parse_related_people(narrative_fields.get("related_people", ""))
        primary_person = related_people[0] if related_people else None
        first_fact = self._first_sentence(narrative_fields.get("details")) or self._first_sentence(narrative_fields.get("summary"))
        second_fact = self._second_sentence(narrative_fields.get("details"))
        occurred_at = self._normalize_occurred_at(narrative_fields.get("occurred_at"))
        location = narrative_fields.get("location") or (structured_case.place.name if structured_case.place else None) or "자료상 명확하지 않음"
        issue_text = self._build_issue_text(first_fact, occurred_at, location)
        dispute_text = self._build_dispute_text(second_fact)
        attachment_items = self._split_attachment_items(narrative_fields.get("attachment_summary"))

        section_text_by_id = {
            "overview": (
                f"본 보고서는 {narrative_fields.get('title') or '해당 사건'}에 대한 사실관계와 관련 자료를 확인하기 위해 작성하였다. "
                f"현재까지 확보된 자료를 기준으로 사건 개요를 정리하면 {self._default_text(issue_text)}."
            ),
            "subject_profile": "\n".join(
                [
                    "- 소속: 자료상 명확하지 않음",
                    f"- 직위/직급: {primary_person['rank'] if primary_person else '자료상 명확하지 않음'}",
                    f"- 성명: {primary_person['name'] if primary_person else '자료상 명확하지 않음'}",
                    f"- 사건명: {narrative_fields.get('title') or '자료상 명확하지 않음'}",
                ]
            ),
            "allegations": "\n".join(
                [
                    f"- 혐의사실 1: {self._default_text(issue_text)}.",
                    f"- 혐의사실 2: {self._default_text(dispute_text)}.",
                ]
            ),
            "findings": "\n".join(
                [
                    f"- 인정되는 사실: {self._default_text(issue_text)}.",
                    f"- 다툼이 있는 사항: {self._default_text(dispute_text)}.",
                    f"- 확인되지 않은 사항: {self._build_unconfirmed_text(second_fact)}.",
                ]
            ),
            "evidence_summary": self._build_evidence_summary_text(attachment_items, evidence_items, issue_text),
            "mitigating_aggravating": "\n".join(
                [
                    "- 유리한 정상: 자료상 명확하지 않음",
                    f"- 불리한 정상: {self._build_adverse_text(dispute_text)}.",
                ]
            ),
            "integrated_opinion": (
                f"현재 자료에 따르면 {self._default_text(issue_text)}. "
                f"다만 {self._default_text(self._build_unconfirmed_text(second_fact))}."
            ),
            "recommendation": (
                "- 징계의결 요구 여부 또는 추가 조사 필요 여부: "
                f"{self._build_recommendation_text(dispute_text)}."
            ),
            "attachments": self._build_attachment_section_text(attachment_items),
        }
        open_issues = self._build_fact_finding_open_issues(
            primary_person=primary_person,
            second_fact=second_fact,
            attachment_items=attachment_items,
        )
        section = SectionDraft(
            section_id=section_plan.section_id,
            title=section_plan.title,
            text=section_text_by_id.get(section_plan.section_id, "자료상 명확하지 않음"),
            citations=citations,
            open_issues=open_issues,
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

    def _parse_narrative_fields(self, narrative: str) -> dict[str, str]:
        return dict(_parse_narrative_fields_cached(narrative))

    def _parse_related_people(self, raw_value: str) -> list[dict[str, str]]:
        return [
            {"raw": raw, "rank": rank, "name": name}
            for raw, rank, name in _parse_related_people_cached(raw_value)
        ]

    def _looks_like_rank(self, token: str) -> bool:
        return token.strip() in COMMON_RANK_TOKENS

    def _first_sentence(self, text: str | None) -> str | None:
        sentences = _split_sentences_cached(text)
        return sentences[0] if sentences else None

    def _second_sentence(self, text: str | None) -> str | None:
        sentences = _split_sentences_cached(text)
        return sentences[1] if len(sentences) > 1 else None

    def _split_sentences(self, text: str | None) -> list[str]:
        return list(_split_sentences_cached(text))

    def _normalize_occurred_at(self, value: str | None) -> str:
        if not value:
            return "자료상 명확하지 않음"
        normalized = value.replace("T", " ").replace("+00:00", "").replace("Z", "")
        return normalized.replace(":00:00", ":00")

    def _format_notice_datetime(self, value: str | None) -> str:
        if not value:
            return "자료상 명확하지 않음"
        text = value.strip()
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return "자료상 명확하지 않음"
        return parsed.strftime("%Y년 %m월 %d일 %H시 %M분")

    def _build_issue_text(self, fact: str | None, occurred_at: str, location: str) -> str:
        if fact:
            return f"{occurred_at}경 {location}에서 {fact}"
        return f"{occurred_at}경 {location}에서 관련 사실관계가 확인되었다"

    def _build_dispute_text(self, fact: str | None) -> str:
        if fact:
            return fact
        return "관련자 진술, 승인 여부 및 경위는 자료상 명확하지 않음"

    def _build_unconfirmed_text(self, fact: str | None) -> str:
        if fact and ("확인되지 않음" in fact or "명확하지 않음" in fact):
            return fact
        return "행위 주체, 승인 여부, 세부 경위는 확인되지 않음"

    def _build_adverse_text(self, dispute_text: str) -> str:
        if dispute_text != "관련자 진술, 승인 여부 및 경위는 자료상 명확하지 않음":
            return "관련자 진술과 승인 관련 자료 사이에 차이가 있어 추가 검토가 필요함"
        return "승인 여부와 경위가 명확히 확인되지 않아 추가 검토가 필요함"

    def _build_recommendation_text(self, dispute_text: str) -> str:
        if dispute_text != "관련자 진술, 승인 여부 및 경위는 자료상 명확하지 않음":
            return "관련자 진술과 승인 기록 등 다툼이 있는 사항을 추가 조사한 후 징계의결 요구 여부를 검토할 필요가 있음"
        return "관련자 진술과 승인 기록을 추가 확인한 뒤 징계의결 요구 여부를 검토할 필요가 있음"

    def _split_attachment_items(self, raw_value: str | None) -> list[str]:
        if not raw_value:
            return []
        normalized = raw_value.replace(" 및 ", ", ").replace("과 ", ", ").replace(" 와 ", ", ")
        items = [item.strip(" .") for item in normalized.split(",") if item.strip(" .")]
        cleaned: list[str] = []
        for item in items:
            normalized_item = item
            for suffix in ("이 첨부되었습니다", "가 첨부되었습니다", "첨부되었습니다"):
                if normalized_item.endswith(suffix):
                    normalized_item = normalized_item[: -len(suffix)].strip()
            cleaned.append(normalized_item or item)
        return cleaned

    def _build_evidence_summary_text(
        self,
        attachment_items: list[str],
        evidence_items: list[EvidenceItem],
        issue_text: str,
    ) -> str:
        evidence_labels = attachment_items or [item.title for item in evidence_items[:2]]
        if not evidence_labels:
            return "- 증거 1: 자료상 명확하지 않음\n- 각 증거로 확인되는 내용: 자료상 명확하지 않음"

        lines = [f"- 증거 {index}: {label}" for index, label in enumerate(evidence_labels[:2], start=1)]
        lines.append(f"- 각 증거로 확인되는 내용: {issue_text}.")
        return "\n".join(lines)

    def _build_attachment_section_text(self, attachment_items: list[str]) -> str:
        if not attachment_items:
            return "첨부자료 없음"
        return "\n".join(f"- {item}" for item in attachment_items)

    def _build_fact_finding_open_issues(
        self,
        *,
        primary_person: dict[str, str] | None,
        second_fact: str | None,
        attachment_items: list[str],
    ) -> list[str]:
        open_issues: list[str] = []
        if primary_person is None:
            open_issues.append("징계혐의자 인적사항")
        elif primary_person["rank"] == "자료상 명확하지 않음":
            open_issues.append("징계혐의자 직위/직급")
        if second_fact is None:
            open_issues.append("다툼이 있는 사항 또는 추가 조사 필요 내용")
        if not attachment_items:
            open_issues.append("첨부자료 또는 증빙자료 목록")
        return _unique_strings(open_issues)

    def _build_disciplinary_resolution_open_issues(
        self,
        *,
        primary_person: dict[str, str] | None,
        decision_order: str,
        decision_date: str,
        committee_name: str,
        committee_members: str,
        second_fact: str | None,
    ) -> list[str]:
        open_issues: list[str] = []
        if primary_person is None:
            open_issues.append("피징계자 인적사항")
        elif primary_person["rank"] == "자료상 명확하지 않음":
            open_issues.append("피징계자 직위(직급)")
        if decision_order == "자료상 명확하지 않음":
            open_issues.append("최종 의결결론")
        if decision_date == "자료상 명확하지 않음":
            open_issues.append("의결일자")
        if committee_name == "자료상 명확하지 않음":
            open_issues.append("징계위원회명")
        if committee_members == "자료상 명확하지 않음":
            open_issues.append("위원장 및 위원 표시")
        if second_fact is None:
            open_issues.append("정상참작 또는 가중사유")
        return _unique_strings(open_issues)[:5]

    def _build_committee_fact_lines(
        self,
        detail_sentences: list[str],
        occurred_at: str,
        location: str,
    ) -> list[str]:
        first_fact = detail_sentences[0] if detail_sentences else None
        second_fact = detail_sentences[1] if len(detail_sentences) > 1 else None
        third_fact = detail_sentences[2] if len(detail_sentences) > 2 else None
        return [
            self._default_text(self._build_issue_text(first_fact, occurred_at, location)),
            self._default_text(second_fact or "관련자 진술과 승인 여부에 관한 자료는 추가 확인이 필요함"),
            self._default_text(third_fact or "세부 경위와 행위 주체는 자료상 명확하지 않음"),
        ]

    def _build_committee_issue_line(self, dispute_text: str, index: int) -> str:
        if index == 1:
            return "승인 절차 준수 여부 및 관련 규정 위반 성립 여부"
        if index == 2:
            return "관련자 진술과 기록자료가 서로 일치하는지 여부"
        if dispute_text != "관련자 진술, 승인 여부 및 경위는 자료상 명확하지 않음":
            return dispute_text
        return "행위 주체와 구체적 경위를 추가 확인할 필요가 있는지 여부"

    def _build_committee_evidence_summary_text(
        self,
        attachment_items: list[str],
        evidence_items: list[EvidenceItem],
        fact_lines: list[str],
    ) -> str:
        evidence_labels = attachment_items or [item.title for item in evidence_items[:3]]
        if not evidence_labels:
            return (
                "- 증거 1: 자료상 명확하지 않음\n"
                "- 증거 2: 자료상 명확하지 않음\n"
                "- 증거 3: 자료상 명확하지 않음"
            )

        proof_lines = [
            "이동 정황 및 관련 시점을 확인할 수 있음",
            "승인 절차 또는 출입 경위를 확인할 수 있음",
            "심의 시 대조가 필요한 참고자료임",
        ]
        lines: list[str] = []
        for index in range(3):
            label = evidence_labels[index] if index < len(evidence_labels) else "자료상 명확하지 않음"
            proof = proof_lines[index]
            if index == 0 and fact_lines:
                proof = f"{fact_lines[0]}를 확인할 수 있음"
            lines.append(f"- 증거 {index + 1}: {label} - {proof}")
        return "\n".join(lines)

    def _build_evidence_judgment_text(
        self,
        attachment_items: list[str],
        evidence_items: list[EvidenceItem],
    ) -> str:
        evidence_labels = attachment_items or [item.title for item in evidence_items[:2]]
        if not evidence_labels:
            return "제출된 자료만으로는 증거 판단의 근거가 충분히 특정되지 않는다."
        labels = ", ".join(evidence_labels[:3])
        return f"{labels} 등을 종합하면 징계의 원인이 된 사실을 판단하기 위한 기초자료로 볼 수 있다."

    def _build_regulation_text(self, evidence_items: list[EvidenceItem]) -> str:
        labels = [item.title for item in evidence_items if item.title][:3]
        if not labels:
            return "자료상 명확하지 않음"
        return ", ".join(_unique_strings(labels))

    def _build_committee_reference_open_issues(
        self,
        *,
        primary_person: dict[str, str] | None,
        attachment_items: list[str],
        dispute_text: str,
    ) -> list[str]:
        open_issues: list[str] = []
        if primary_person is None:
            open_issues.extend(["심의 대상자", "심의대상자 인적사항"])
        elif primary_person["rank"] == "자료상 명확하지 않음":
            open_issues.append("심의대상자 직위/직급")
        open_issues.append("심의 일시")
        open_issues.append("대상자 진술 또는 소명")
        if dispute_text == "관련자 진술, 승인 여부 및 경위는 자료상 명확하지 않음":
            open_issues.append("다툼이 있는 부분")
        if not attachment_items:
            open_issues.append("첨부자료 목록")
        return _unique_strings(open_issues)

    def _build_attendance_notice_open_issues(
        self,
        *,
        primary_person: dict[str, str] | None,
        appearance_datetime: str | None,
        appearance_location: str,
        committee_name: str,
        notice_date: str,
    ) -> list[str]:
        open_issues: list[str] = []
        if primary_person is None:
            open_issues.extend(["대상자 성명", "대상자 직위(직급)"])
        if not appearance_datetime:
            open_issues.append("출석 일시")
        if appearance_location == "자료상 명확하지 않음":
            open_issues.append("출석 장소")
        if committee_name == "자료상 명확하지 않음":
            open_issues.append("징계위원회명")
        if notice_date == "자료상 명확하지 않음":
            open_issues.append("통지일")
        open_issues.append("대상자 주소")
        return _unique_strings(open_issues)[:5]

    def _default_text(self, value: str | None) -> str:
        if value:
            return value.rstrip(".")
        return "자료상 명확하지 않음"

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
