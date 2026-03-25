from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from documents.evaluation import DocumentDraftEvaluator
from documents.evidence import EvidenceCollector
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


@dataclass
class DocumentGenerationSettings:
    operational_mode: bool = False
    enable_plan_retrieval_loop: bool = True


class DocumentGenerationService:
    def __init__(
        self,
        evidence_collector: EvidenceCollector,
        *,
        planner: DocumentPlanner | None = None,
        section_generator: DocumentSectionGenerator | None = None,
        evaluator: DocumentDraftEvaluator | None = None,
        settings: DocumentGenerationSettings | None = None,
    ) -> None:
        self.evidence_collector = evidence_collector
        self.planner = planner or DocumentPlanner()
        self.section_generator = section_generator or DocumentSectionGenerator()
        self.evaluator = evaluator or DocumentDraftEvaluator()
        self.settings = settings or DocumentGenerationSettings()

    async def generate(
        self,
        request: DocumentGenerationRequest,
        context: ObservationContext,
    ) -> DocumentGenerationResponse:
        response: DocumentGenerationResponse | None = None
        async for event in self.stream(request, context):
            if event.event == "complete":
                response = DocumentGenerationResponse.model_validate(event.data["response"])
        if response is None:
            raise RuntimeError("document generation did not complete")
        return response

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

        evidence_pack, checklist_missing_info, evidence_debug = await self.evidence_collector.collect(request, context)
        yield DocumentStreamEvent(
            event="evidence",
            data={
                "checklist_missing_info": checklist_missing_info,
                "totals_by_type": self._count_evidence(evidence_pack),
                "source_debug": self._maybe_mask(evidence_debug),
            },
        )

        plan = self.planner.create_plan(request, evidence_pack, checklist_missing_info, context)
        if self.settings.enable_plan_retrieval_loop and request.constraints.enable_plan_retrieval_loop:
            evidence_pack, loop_debug = self.evidence_collector.collect_additional_for_plan(
                request,
                plan.additional_retrieval_keywords,
                evidence_pack,
                context,
            )
            plan.notes.append(f"추가 근거 회수: {len(loop_debug['added_ids'])}건")

        yield DocumentStreamEvent(
            event="plan",
            data={
                "title": plan.title,
                "sections": [section.model_dump(mode="json") for section in plan.sections],
                "notes": plan.notes,
                "additional_retrieval_keywords": plan.additional_retrieval_keywords,
            },
        )

        sections: list[SectionDraft] = []
        for section_plan in plan.sections:
            section = self.section_generator.generate_section(request, evidence_pack, section_plan, sections, context)
            sections.append(section)
            yield DocumentStreamEvent(event="section", data=section.model_dump(mode="json"))

        draft = DocumentDraft(
            doc_type=request.user_intent.doc_type,
            title=plan.title,
            sections=sections,
            compiled_text=self._compile_text(sections),
        )
        warnings = self.evaluator.evaluate(request, plan, draft, evidence_pack)
        evidence_report = self._build_evidence_report(evidence_pack, sections)
        response = DocumentGenerationResponse(
            draft=draft,
            checklist_missing_info=checklist_missing_info,
            evidence_report=evidence_report,
            warnings=warnings,
        )
        yield DocumentStreamEvent(
            event="evaluation",
            data={
                "warning_count": len(warnings),
                "warnings": [warning.model_dump(mode="json") for warning in warnings],
            },
        )
        yield DocumentStreamEvent(event="complete", data={"response": response.model_dump(mode="json")})
        log_info(
            logger,
            "document generation completed",
            context,
            doc_type=request.user_intent.doc_type,
            section_count=len(sections),
            warning_count=len(warnings),
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
