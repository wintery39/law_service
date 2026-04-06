from __future__ import annotations

from dataclasses import dataclass
import re
from typing import AsyncIterator, Literal

from documents.evaluation import DocumentDraftEvaluator
from documents.evidence import EvidenceCollector
from documents.gemini import GeminiDocumentGenerator, GeminiGeneratedSection
from documents.planning import DocumentPlanner
from schemas import (
    DocumentDraft,
    DocumentGenerationRequest,
    DocumentGenerationResponse,
    DocumentPlan,
    DocumentStreamEvent,
    EvidenceItem,
    EvidencePack,
    EvidenceReport,
    EvidenceType,
    ObservationContext,
    SectionDraft,
    SectionPlan,
)
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
PROMPT_LEAK_LINE_PREFIXES = (
    "추가 필요 정보",
    "누락정보",
    "출력 형식",
    "입력값",
    "추가 지시",
    "작성 원칙",
    "중요:",
    "목표:",
)
PROMPT_LEAK_LINE_PATTERNS = (
    re.compile(
        r'^\s*["\']?(document_title|document_type|user_text|objective|audience|constraints|structured_case|plan|evidence)["\']?\s*:'
    ),
    re.compile(r"^\s*[\{\}\[\]]\s*,?$"),
)
PROMPT_LEAK_SUBSTRINGS = (
    "내부적으로는 다음",
    "내부적으로 다음",
    "그러나 출력에는",
    "출력은 반드시 JSON schema",
    "responseJsonSchema",
    "문서 제목은 backend가 별도로 표시",
    "heading 번호와 section title은 backend가 붙이므로",
    "citations는 backend가 별도로 붙이므로",
)
PROMPT_PROFILE_SECTION_MARKERS: dict[str, dict[str, list[str]]] = {
    "fact_finding_report": {
        "subject_profile": ["- 소속:", "- 직위/직급:", "- 성명:", "- 사건명:"],
        "allegations": ["- 혐의사실 1:", "- 혐의사실 2:"],
        "findings": ["- 인정되는 사실", "- 다툼이 있는 사항", "- 확인되지 않은 사항"],
        "evidence_summary": ["- 증거 1:", "- 증거 2:", "- 각 증거로 확인되는 내용:"],
        "mitigating_aggravating": ["- 유리한 정상:", "- 불리한 정상:"],
        "recommendation": ["- 징계의결 요구 여부 또는 추가 조사 필요 여부:"],
    },
    "committee_reference": {
        "case_overview": ["- 사건명:", "- 심의 일시:", "- 심의 대상자:", "- 사건 요약:"],
        "subject_profile": ["- 소속:", "- 직위/직급:", "- 성명:"],
        "fact_summary": ["- 사실관계 1:", "- 사실관계 2:", "- 사실관계 3:"],
        "issues": ["- 쟁점 1:", "- 쟁점 2:", "- 쟁점 3:"],
        "evidence_summary": ["- 증거 1:", "- 증거 2:", "- 증거 3:"],
        "statements": ["- 대상자 진술 요지:", "- 참고인/관계인 진술 요지:", "- 다툼이 있는 부분:"],
        "mitigating_aggravating": ["- 유리한 정상:", "- 불리한 정상:"],
        "applicable_rules": ["- 관련 법령/규정:", "- 검토 포인트:"],
        "judgment_points": ["- 사실인정 포인트", "- 양정 판단 포인트", "- 추가 확인 필요 사항"],
    },
    "disciplinary_resolution": {
        "subject_profile": ["- 소속:", "- 직위(직급):", "- 성명:"],
        "decision_order": ["- "],
        "reasoning": [
            "가. 인정되는 사실",
            "나. 증거의 판단",
            "다. 적용 규정",
            "라. 양정 판단",
            "- 비위의 정도",
            "- 고의/과실",
            "- 조직 영향",
            "- 유리한 정상",
            "- 불리한 정상",
        ],
        "decision_date": ["- 의결일자:"],
        "committee_name": ["- 징계위원회명:"],
        "committee_members": ["- 위원장 및 위원 표시:"],
    },
    "attendance_notice": {
        "personal_info": ["- 성명:", "- 소속:", "- 직위(직급):", "- 주소:"],
        "appearance_datetime": ["- "],
        "appearance_location": ["- "],
        "notes": [
            "- 출석하여 진술하기를 원하지 않는 경우 진술권 포기서를 제출할 수 있음",
            "- 서면진술을 원할 경우 지정 기한까지 진술서를 제출할 수 있음",
            "- 정당한 사유 없이 불출석하고 서면진술도 없으면 진술 의사가 없는 것으로 보고 처리될 수 있음",
            "- 필요 시 소명자료 또는 증빙자료를 제출할 수 있음",
        ],
        "notice_statement": ["- 관련 규정에 따라 위와 같이 귀하의 출석을 통지합니다."],
        "sender": ["- 통지일:", "- 징계위원회명:", "- 위원회 청인 또는 직인 표시"],
        "recipient": ["- 귀하"],
        "appendix": ["- 필요 시 진술권 포기서 양식"],
    },
}


def build_document_stream_error_event(error: Exception) -> DocumentStreamEvent:
    detail = str(error).strip() or error.__class__.__name__
    return DocumentStreamEvent(
        event="error",
        data={"detail": detail, "error_type": type(error).__name__},
    )


@dataclass
class DocumentGenerationSettings:
    operational_mode: bool = False
    enable_plan_retrieval_loop: bool = True
    generation_provider: Literal["gemini"] = "gemini"


class DocumentGenerationService:
    def __init__(
        self,
        evidence_collector: EvidenceCollector,
        *,
        planner: DocumentPlanner | None = None,
        gemini_generator: GeminiDocumentGenerator | None = None,
        evaluator: DocumentDraftEvaluator | None = None,
        settings: DocumentGenerationSettings | None = None,
    ) -> None:
        self.evidence_collector = evidence_collector
        self.planner = planner or DocumentPlanner()
        self.gemini_generator = gemini_generator
        self.evaluator = evaluator or DocumentDraftEvaluator()
        self.settings = settings or DocumentGenerationSettings()

    async def aclose(self) -> None:
        if self.gemini_generator is not None:
            await self.gemini_generator.aclose()

    async def generate(
        self,
        request: DocumentGenerationRequest,
        context: ObservationContext,
    ) -> DocumentGenerationResponse:
        response: DocumentGenerationResponse | None = None
        error_detail: str | None = None
        async for event in self.stream(request, context):
            if event.event == "complete":
                response = DocumentGenerationResponse.model_validate(event.data["response"])
            if event.event == "error":
                error_detail = str(event.data.get("detail") or "document generation failed")
        if response is None:
            raise RuntimeError(error_detail or "document generation did not complete")
        return response

    async def generate_with_artifacts(
        self,
        request: DocumentGenerationRequest,
        context: ObservationContext,
    ) -> tuple[DocumentGenerationResponse, EvidencePack]:
        evidence_pack, checklist_missing_info, _, plan = await self._prepare_generation(request, context)
        sections = await self._generate_sections(request, evidence_pack, plan, context)
        response = self._build_response(request, plan, sections, evidence_pack, checklist_missing_info)
        return response, evidence_pack

    async def stream(
        self,
        request: DocumentGenerationRequest,
        context: ObservationContext,
    ) -> AsyncIterator[DocumentStreamEvent]:
        log_info(logger, "document generation started", context, doc_type=request.user_intent.doc_type)
        yield DocumentStreamEvent(
            event="start",
            data={"session_id": request.session_id, "doc_type": request.user_intent.doc_type},
        )

        try:
            evidence_pack, checklist_missing_info, evidence_debug, plan = await self._prepare_generation(request, context)
            yield DocumentStreamEvent(
                event="evidence",
                data={
                    "checklist_missing_info": checklist_missing_info,
                    "totals_by_type": self._count_evidence(evidence_pack),
                    "source_debug": self._maybe_mask(evidence_debug),
                },
            )
            yield DocumentStreamEvent(
                event="plan",
                data={
                    "title": plan.title,
                    "sections": [section.model_dump(mode="json") for section in plan.sections],
                    "notes": plan.notes,
                    "additional_retrieval_keywords": plan.additional_retrieval_keywords,
                },
            )

            sections = await self._generate_sections(request, evidence_pack, plan, context)
            for section in sections:
                yield DocumentStreamEvent(event="section", data=section.model_dump(mode="json"))

            response = self._build_response(request, plan, sections, evidence_pack, checklist_missing_info)
            yield DocumentStreamEvent(
                event="evaluation",
                data={
                    "warning_count": len(response.warnings),
                    "warnings": [warning.model_dump(mode="json") for warning in response.warnings],
                },
            )
            yield DocumentStreamEvent(event="complete", data={"response": response.model_dump(mode="json")})
            log_info(
                logger,
                "document generation completed",
                context,
                doc_type=request.user_intent.doc_type,
                section_count=len(sections),
                warning_count=len(response.warnings),
            )
        except Exception as error:
            logger.exception(
                "document generation failed | request_id=%s corpus_version=%s ingestion_run_id=%s doc_type=%s",
                context.request_id,
                context.corpus_version,
                context.ingestion_run_id,
                request.user_intent.doc_type,
            )
            yield build_document_stream_error_event(error)

    async def _prepare_generation(
        self,
        request: DocumentGenerationRequest,
        context: ObservationContext,
    ) -> tuple[EvidencePack, list[str], dict[str, object], DocumentPlan]:
        evidence_pack, checklist_missing_info, evidence_debug = await self.evidence_collector.collect(request, context)
        plan = self.planner.create_plan(request, evidence_pack, checklist_missing_info, context)
        if self.settings.enable_plan_retrieval_loop and request.constraints.enable_plan_retrieval_loop:
            evidence_pack, loop_debug = self.evidence_collector.collect_additional_for_plan(
                request,
                plan.additional_retrieval_keywords,
                evidence_pack,
                context,
            )
            plan.notes.append(f"추가 근거 회수: {len(loop_debug['added_ids'])}건")
        return evidence_pack, checklist_missing_info, evidence_debug, plan

    async def _generate_sections(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
        context: ObservationContext,
    ) -> list[SectionDraft]:
        if self.gemini_generator is None or not self.gemini_generator.is_configured():
            raise RuntimeError("Gemini document generation is enabled but GEMINI_API_KEY is not configured.")
        generated = await self.gemini_generator.generate_sections(request, evidence_pack, plan, context)
        return self._build_sections_from_gemini(request, evidence_pack, plan, generated)

    def _build_sections_from_gemini(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
        generated_sections: list[GeminiGeneratedSection],
    ) -> list[SectionDraft]:
        sections_by_id: dict[str, GeminiGeneratedSection] = {}
        for section in generated_sections:
            if section.section_id not in sections_by_id and section.text.strip():
                sections_by_id[section.section_id] = section

        if not sections_by_id:
            raise RuntimeError("gemini generation returned no usable document sections")

        missing_sections: list[str] = []
        empty_sections: list[str] = []
        finalized_sections: list[SectionDraft] = []
        for section_plan in plan.sections:
            llm_section = sections_by_id.get(section_plan.section_id)
            if llm_section is None:
                missing_sections.append(section_plan.section_id)
                continue
            normalized_text = self._normalize_generated_text(
                request,
                section_plan.section_id,
                section_plan.title,
                llm_section.text,
            )
            if not normalized_text.strip():
                empty_sections.append(section_plan.section_id)
                continue
            finalized_sections.append(
                SectionDraft(
                    section_id=section_plan.section_id,
                    title=section_plan.title,
                    text=normalized_text,
                    citations=self._select_evidence_ids(section_plan, evidence_pack),
                    open_issues=self._unique_strings(llm_section.open_issues),
                )
            )

        if missing_sections or empty_sections:
            problems: list[str] = []
            if missing_sections:
                problems.append(f"누락 섹션: {', '.join(missing_sections)}")
            if empty_sections:
                problems.append(f"빈 섹션: {', '.join(empty_sections)}")
            raise RuntimeError("gemini generation did not produce all required sections. " + " / ".join(problems))

        return finalized_sections

    def _unique_strings(self, values: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def _select_evidence_ids(self, section_plan: SectionPlan, evidence_pack: EvidencePack) -> list[str]:
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

        citations: list[str] = []
        seen_ids: set[str] = set()
        for item in selected:
            if item.evidence_id in seen_ids:
                continue
            seen_ids.add(item.evidence_id)
            citations.append(item.evidence_id)
        return citations

    def _normalize_generated_text(
        self,
        request: DocumentGenerationRequest,
        section_id: str,
        section_title: str,
        text: str,
    ) -> str:
        normalized = self._strip_prompt_leakage(section_title, text)
        prompt_profile = request.constraints.prompt_profile
        if prompt_profile in PROMPT_PROFILE_SECTION_MARKERS:
            normalized = self._normalize_prompt_profile_text(prompt_profile, section_id, normalized)
        return normalized

    def _normalize_prompt_profile_text(self, prompt_profile: str, section_id: str, text: str) -> str:
        normalized = text.replace("\r\n", "\n").strip()
        markers = PROMPT_PROFILE_SECTION_MARKERS[prompt_profile].get(section_id, [])
        for marker in markers:
            normalized = re.sub(rf"(?<!\n){re.escape(marker)}", f"\n{marker}", normalized)
        normalized = self._trim_to_first_marker(normalized, markers)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.lstrip("\n")

    def _strip_prompt_leakage(self, section_title: str, text: str) -> str:
        normalized = text.replace("\r\n", "\n").strip()
        normalized = re.sub(rf"^\d+\.\s*{re.escape(section_title)}\s*$", "", normalized, count=1, flags=re.MULTILINE)
        normalized = re.sub(rf"^{re.escape(section_title)}\s*$", "", normalized, count=1, flags=re.MULTILINE)
        normalized = re.sub(r"^제목:\s*.+$", "", normalized, count=1, flags=re.MULTILINE)

        lines: list[str] = []
        previous_blank = False
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                if not previous_blank:
                    lines.append("")
                previous_blank = True
                continue
            if line.startswith("```"):
                continue
            if any(line.startswith(prefix) for prefix in PROMPT_LEAK_LINE_PREFIXES):
                continue
            if any(pattern.match(line) for pattern in PROMPT_LEAK_LINE_PATTERNS):
                continue
            if any(fragment in line for fragment in PROMPT_LEAK_SUBSTRINGS):
                continue
            lines.append(line)
            previous_blank = False

        cleaned = "\n".join(lines).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    def _trim_to_first_marker(self, text: str, markers: list[str]) -> str:
        if not text or not markers:
            return text

        first_positions = [text.find(marker) for marker in markers if text.find(marker) >= 0]
        if not first_positions:
            return text

        first_marker_position = min(first_positions)
        if first_marker_position <= 0:
            return text
        return text[first_marker_position:]

    def _build_response(
        self,
        request: DocumentGenerationRequest,
        plan: DocumentPlan,
        sections: list[SectionDraft],
        evidence_pack: EvidencePack,
        checklist_missing_info: list[str],
    ) -> DocumentGenerationResponse:
        draft = DocumentDraft(
            doc_type=request.user_intent.doc_type,
            title=plan.title,
            sections=sections,
            compiled_text=self._compile_text(sections),
        )
        warnings = self.evaluator.evaluate(request, plan, draft, evidence_pack)
        evidence_report = self._build_evidence_report(evidence_pack, sections)
        return DocumentGenerationResponse(
            draft=draft,
            checklist_missing_info=checklist_missing_info,
            evidence_report=evidence_report,
            warnings=warnings,
        )

    def _compile_text(self, sections: list[SectionDraft]) -> str:
        blocks = [f"{section.title}\n{section.text}" for section in sections]
        return "\n\n".join(blocks)

    def _build_evidence_report(
        self,
        evidence_pack: EvidencePack,
        sections: list[SectionDraft],
    ) -> EvidenceReport:
        used_ids = {citation for section in sections for citation in section.citations}
        all_ids = [item.evidence_id for item in evidence_pack.all_items()]
        section_coverage = {section.section_id: section.citations for section in sections}
        return EvidenceReport(
            totals_by_type=self._count_evidence(evidence_pack),
            used_evidence_ids=sorted(used_ids),
            unused_evidence_ids=[evidence_id for evidence_id in all_ids if evidence_id not in used_ids],
            section_coverage=section_coverage,
            source_mode=str(evidence_pack.source_debug.get("related_articles_type", "result")),
        )

    def _count_evidence(self, evidence_pack: EvidencePack) -> dict[str, int]:
        return {
            "law": len(evidence_pack.laws),
            "case": len(evidence_pack.cases),
            "regulation": len(evidence_pack.regulations),
            "form": len(evidence_pack.forms),
        }

    def _maybe_mask(self, debug: dict[str, object]) -> dict[str, object]:
        if not self.settings.operational_mode:
            return debug
        return {
            "related_articles_type": debug.get("related_articles_type"),
            "keyword_count": len(debug.get("base_keywords", [])) if isinstance(debug.get("base_keywords"), list) else 0,
        }
