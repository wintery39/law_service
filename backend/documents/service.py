from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Literal

from documents.evaluation import DocumentDraftEvaluator
from documents.evidence import EvidenceCollector
from documents.gemini import GeminiDocumentGenerator, GeminiGeneratedSection
from documents.generator import DocumentSectionGenerator
from documents.planning import DocumentPlanner
from schemas import (
    DocumentDraft,
    DocumentGenerationRequest,
    DocumentGenerationResponse,
    DocumentPlan,
    DocumentStreamEvent,
    EvidencePack,
    EvidenceReport,
    ObservationContext,
    SectionDraft,
)
from storage.observability import get_logger, log_info


logger = get_logger(__name__)


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
    generation_provider: Literal["auto", "heuristic", "gemini"] = "auto"


class DocumentGenerationService:
    def __init__(
        self,
        evidence_collector: EvidenceCollector,
        *,
        planner: DocumentPlanner | None = None,
        section_generator: DocumentSectionGenerator | None = None,
        gemini_generator: GeminiDocumentGenerator | None = None,
        evaluator: DocumentDraftEvaluator | None = None,
        settings: DocumentGenerationSettings | None = None,
    ) -> None:
        self.evidence_collector = evidence_collector
        self.planner = planner or DocumentPlanner()
        self.section_generator = section_generator or DocumentSectionGenerator()
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
        if self._should_use_gemini():
            if self.gemini_generator is None or not self.gemini_generator.is_configured():
                raise RuntimeError("Gemini document generation is enabled but GEMINI_API_KEY is not configured.")
            generated = await self.gemini_generator.generate_sections(request, evidence_pack, plan, context)
            return self._merge_sections_with_heuristics(request, evidence_pack, plan, generated, context)

        return self._generate_sections_heuristically(request, evidence_pack, plan, context)

    def _generate_sections_heuristically(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
        context: ObservationContext,
    ) -> list[SectionDraft]:
        sections: list[SectionDraft] = []
        for section_plan in plan.sections:
            sections.append(self.section_generator.generate_section(request, evidence_pack, section_plan, sections, context))
        return sections

    def _merge_sections_with_heuristics(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
        generated_sections: list[GeminiGeneratedSection],
        context: ObservationContext,
    ) -> list[SectionDraft]:
        sections_by_id = {}
        for section in generated_sections:
            if section.section_id not in sections_by_id and section.text.strip():
                sections_by_id[section.section_id] = section

        if not sections_by_id:
            raise RuntimeError("gemini generation returned no usable document sections")

        merged_sections: list[SectionDraft] = []
        for section_plan in plan.sections:
            heuristic_section = self.section_generator.generate_section(
                request,
                evidence_pack,
                section_plan,
                merged_sections,
                context,
            )
            llm_section = sections_by_id.get(section_plan.section_id)
            if llm_section is None:
                merged_sections.append(heuristic_section)
                continue
            merged_sections.append(
                heuristic_section.model_copy(
                    update={
                        "text": llm_section.text.strip(),
                        "open_issues": self._merge_open_issues(llm_section.open_issues, heuristic_section.open_issues),
                    }
                )
            )
        return merged_sections

    def _merge_open_issues(self, llm_open_issues: list[str], heuristic_open_issues: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in [*llm_open_issues, *heuristic_open_issues]:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def _should_use_gemini(self) -> bool:
        if self.settings.generation_provider == "heuristic":
            return False
        if self.settings.generation_provider == "gemini":
            return True
        return self.gemini_generator is not None and self.gemini_generator.is_configured()

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
