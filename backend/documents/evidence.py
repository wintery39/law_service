from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from schemas import (
    DocumentGenerationRequest,
    EvidenceItem,
    EvidencePack,
    EvidenceType,
    ObservationContext,
    RelatedArticleCandidate,
    RelatedArticleRequest,
    RelatedArticleResponse,
    StructuredCase,
)
from search.pipeline import RelatedArticleFinderService
from search.store import TextSearchStore
from storage import CorpusRepository
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
REGULATION_NAME_HINTS = ("규정", "규율", "훈령", "예규", "지침")

CASE_LIBRARY = [
    {
        "evidence_id": "case:discipline-command-refusal",
        "title": "지휘명령 거부에 대한 징계 판단례",
        "summary": "정당한 지휘명령을 반복적으로 거부한 경우 복무질서를 해친 사정이 중하게 평가된다.",
        "snippet": "명령거부와 상관 지휘체계 훼손은 징계 양정에서 불리한 요소로 평가된다.",
        "keywords": ["명령거부", "징계", "상관", "지휘관"],
        "doc_types": ["disciplinary_opinion"],
    },
    {
        "evidence_id": "case:administrative-prior-notice",
        "title": "불이익처분 사전통지 흠결 판단례",
        "summary": "사전통지와 의견제출 기회가 누락되면 처분 절차상 하자가 문제될 수 있다.",
        "snippet": "사전통지 누락은 행정절차의 본질적 절차보장 침해 여부와 함께 검토한다.",
        "keywords": ["행정처분", "사전통지", "의견제출", "청문"],
        "doc_types": ["fact_summary", "defense_draft"],
    },
    {
        "evidence_id": "case:criminal-assault-defense",
        "title": "폭행 사건 사실관계 다툼 판단례",
        "summary": "폭행의 고의, 상해 발생 여부, 현장 정황이 사실인정의 핵심 요소가 된다.",
        "snippet": "신체 접촉의 정도와 피해 진술의 일관성이 핵심 쟁점으로 정리된다.",
        "keywords": ["폭행", "상해", "신체", "피해자"],
        "doc_types": ["fact_summary", "defense_draft"],
    },
]

REGULATION_LIBRARY = [
    {
        "evidence_id": "regulation:discipline-guideline",
        "title": "징계 양정 검토 기준",
        "summary": "복무위반의 반복성, 지휘체계 영향, 반성 여부를 함께 본다.",
        "snippet": "반복 위반 여부, 상관과의 관계, 부대질서 영향은 의견서 작성 시 정리 대상이다.",
        "keywords": ["징계", "근무지이탈", "명령거부", "복무"],
        "doc_types": ["disciplinary_opinion"],
    },
    {
        "evidence_id": "regulation:fact-memo-guide",
        "title": "사실관계 정리 작성 기준",
        "summary": "시점, 장소, 행위, 객체, 확인자료를 분리해 정리한다.",
        "snippet": "사실과 평가를 구분하고 누락 정보는 별도로 표시한다.",
        "keywords": ["사실관계", "시점", "장소", "행위", "객체"],
        "doc_types": ["fact_summary"],
    },
    {
        "evidence_id": "regulation:defense-draft-guide",
        "title": "항변서 초안 작성 유의사항",
        "summary": "단정 대신 주장 구조를 사용하고 사실, 절차, 법리 항변을 구분한다.",
        "snippet": "확정적 표현을 피하고 쟁점별 근거를 명시하는 방식이 바람직하다.",
        "keywords": ["항변", "절차", "법리", "주장"],
        "doc_types": ["defense_draft"],
    },
]

FORM_LIBRARY = {
    "fact_summary": {
        "evidence_id": "form:fact-summary-template",
        "title": "사실관계 정리서 기본 양식",
        "summary": "개요, 경위, 근거, 추가확인 사항 순으로 작성한다.",
        "snippet": "개요 - 경위 - 검토 근거 - 추가 확인 필요사항",
        "keywords": ["사실관계", "개요", "경위", "추가확인"],
    },
    "disciplinary_opinion": {
        "evidence_id": "form:disciplinary-opinion-template",
        "title": "징계 의견서 기본 양식",
        "summary": "위반행위, 적용 규정, 정상관계, 의견 순으로 정리한다.",
        "snippet": "위반행위 요지 - 적용 규정 - 정상참작 - 종합 의견",
        "keywords": ["징계", "의견서", "적용규정", "정상참작"],
    },
    "defense_draft": {
        "evidence_id": "form:defense-draft-template",
        "title": "항변서 초안 기본 양식",
        "summary": "사실관계, 절차상 문제, 법리 주장, 요청사항 순으로 작성한다.",
        "snippet": "사실관계 - 절차상 항변 - 법리상 항변 - 결론",
        "keywords": ["항변서", "절차", "법리", "결론"],
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


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _score_keywords(keywords: list[str], text_parts: list[str]) -> int:
    haystack = " ".join(text_parts).lower()
    return sum(1 for keyword in keywords if keyword.lower() in haystack)


def _classify_law_type(law_name: str) -> EvidenceType:
    return EvidenceType.REGULATION if any(token in law_name for token in REGULATION_NAME_HINTS) else EvidenceType.LAW


class RelatedArticlesClient(ABC):
    @abstractmethod
    async def find(
        self,
        request: RelatedArticleRequest,
        context: ObservationContext,
    ) -> RelatedArticleResponse:
        raise NotImplementedError


class InProcessRelatedArticlesClient(RelatedArticlesClient):
    def __init__(self, service: RelatedArticleFinderService) -> None:
        self.service = service

    async def find(
        self,
        request: RelatedArticleRequest,
        context: ObservationContext,
    ) -> RelatedArticleResponse:
        return await self.service.handle(request, context)


class EvidenceCollector:
    def __init__(
        self,
        related_articles_client: RelatedArticlesClient,
        repository: CorpusRepository,
        text_search_store: TextSearchStore,
    ) -> None:
        self.related_articles_client = related_articles_client
        self.repository = repository
        self.text_search_store = text_search_store

    async def collect(
        self,
        request: DocumentGenerationRequest,
        context: ObservationContext,
    ) -> tuple[EvidencePack, list[str], dict[str, Any]]:
        related_request = RelatedArticleRequest(
            session_id=request.session_id,
            user_text=request.user_text,
            structured_case=request.structured_case,
            as_of_date=request.as_of_date,
            jurisdiction=request.jurisdiction,
            user_profile=request.structured_case.user_profile if request.structured_case else None,
        )
        related_response = await self.related_articles_client.find(related_request, context)

        if related_response.type == "clarify":
            structured_case = related_response.partial_structured_case
            route_labels: list[str] = []
            checklist_missing_info = related_response.missing_slots
            legal_evidence: list[EvidenceItem] = []
        else:
            structured_case = related_response.structured_case
            route_labels = related_response.route.labels
            checklist_missing_info = structured_case.missing_slots
            legal_evidence = [self._candidate_to_evidence(candidate) for candidate in related_response.final]

        laws = [item for item in legal_evidence if item.evidence_type == EvidenceType.LAW]
        regulations = [item for item in legal_evidence if item.evidence_type == EvidenceType.REGULATION]
        keywords = self._build_keywords(request, structured_case, route_labels)
        case_evidence = self._search_library(CASE_LIBRARY, keywords, request.user_intent.doc_type, EvidenceType.CASE)
        regulations.extend(
            self._search_library(
                REGULATION_LIBRARY,
                keywords,
                request.user_intent.doc_type,
                EvidenceType.REGULATION,
            )
        )
        form_evidence = [self._build_form_evidence(request.user_intent.doc_type)]

        pack = EvidencePack(
            structured_case=structured_case,
            route_labels=route_labels,
            laws=self._dedupe_evidence(laws),
            cases=self._dedupe_evidence(case_evidence),
            regulations=self._dedupe_evidence(regulations),
            forms=self._dedupe_evidence(form_evidence),
            source_debug={
                "related_articles_type": related_response.type,
                "related_checklist_missing_info": checklist_missing_info,
                "base_keywords": keywords[:12],
            },
        )
        log_info(
            logger,
            "evidence collected",
            context,
            doc_type=request.user_intent.doc_type,
            source_mode=related_response.type,
            laws=len(pack.laws),
            cases=len(pack.cases),
            regulations=len(pack.regulations),
            forms=len(pack.forms),
        )
        return pack, checklist_missing_info, pack.source_debug

    def collect_additional_for_plan(
        self,
        request: DocumentGenerationRequest,
        plan_keywords: list[str],
        evidence_pack: EvidencePack,
        context: ObservationContext,
    ) -> tuple[EvidencePack, dict[str, Any]]:
        existing_source_refs = {item.source_ref for item in evidence_pack.all_items() if item.source_ref}
        additional_laws = list(evidence_pack.laws)
        additional_regulations = list(evidence_pack.regulations)
        added_ids: list[str] = []

        for keyword in plan_keywords[:6]:
            for hit in self.text_search_store.search(keyword, 2, context):
                unit_id = str(hit["unit_id"])
                if unit_id in existing_source_refs:
                    continue
                unit = self.repository.get_unit(unit_id, context)
                version = self.repository.get_version(unit.version_id, context)
                law = self.repository.get_law_by_internal_id(unit.law_id, context)
                evidence = EvidenceItem(
                    evidence_id=f"{_classify_law_type(law.name_ko).value}:{unit.id}",
                    evidence_type=_classify_law_type(law.name_ko),
                    title=f"{law.name_ko} {unit.heading or unit.unit_path}",
                    summary=(unit.body_text or unit.heading or "")[:180],
                    snippet=(unit.body_text or unit.heading or "")[:240],
                    citation_label=f"{law.name_ko} {unit.unit_path}",
                    keywords=[keyword, law.name_ko, unit.heading or unit.unit_path],
                    source_ref=unit.id,
                    metadata={
                        "official_law_id": law.official_law_id,
                        "unit_path": unit.unit_path,
                        "effective_at": (unit.effective_at or version.effective_at),
                    },
                    relevance_score=float(hit["score"]),
                )
                added_ids.append(evidence.evidence_id)
                if evidence.evidence_type == EvidenceType.LAW:
                    additional_laws.append(evidence)
                else:
                    additional_regulations.append(evidence)
                existing_source_refs.add(unit_id)

        additional_cases = list(evidence_pack.cases)
        additional_cases.extend(
            self._search_library(CASE_LIBRARY, plan_keywords, request.user_intent.doc_type, EvidenceType.CASE)
        )
        additional_regulations.extend(
            self._search_library(
                REGULATION_LIBRARY,
                plan_keywords,
                request.user_intent.doc_type,
                EvidenceType.REGULATION,
            )
        )

        updated_pack = evidence_pack.model_copy(deep=True)
        updated_pack.laws = self._dedupe_evidence(additional_laws)
        updated_pack.cases = self._dedupe_evidence(additional_cases)
        updated_pack.regulations = self._dedupe_evidence(additional_regulations)
        updated_pack.source_debug["plan_loop_keywords"] = plan_keywords[:10]
        updated_pack.source_debug["plan_loop_added_ids"] = added_ids
        return updated_pack, {"added_ids": added_ids}

    def _build_keywords(
        self,
        request: DocumentGenerationRequest,
        structured_case: StructuredCase,
        route_labels: list[str],
    ) -> list[str]:
        return _unique_strings(
            [
                *structured_case.keyphrases,
                *structured_case.legal_terms,
                *(action.verb for action in structured_case.actions),
                *(obj.name for obj in structured_case.objects),
                *route_labels,
                request.user_intent.doc_type,
                *_tokenize(request.user_text),
            ]
        )

    def _candidate_to_evidence(self, candidate: RelatedArticleCandidate) -> EvidenceItem:
        evidence_type = _classify_law_type(candidate.law_name)
        return EvidenceItem(
            evidence_id=f"{evidence_type.value}:{candidate.internal_id}",
            evidence_type=evidence_type,
            title=f"{candidate.law_name} {candidate.unit_path}",
            summary=candidate.snippet[:180],
            snippet=candidate.snippet,
            citation_label=f"{candidate.law_name} {candidate.unit_path}",
            keywords=[candidate.law_name, candidate.unit_path],
            source_ref=candidate.internal_id,
            metadata={
                "law_internal_id": candidate.law_internal_id,
                "official_law_id": candidate.official_law_id,
                "effective_at": candidate.effective_at,
                "amended_at": candidate.amended_at,
            },
            relevance_score=candidate.final_score,
        )

    def _search_library(
        self,
        library: list[dict[str, Any]],
        keywords: list[str],
        doc_type: str,
        evidence_type: EvidenceType,
    ) -> list[EvidenceItem]:
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in library:
            if doc_type not in item["doc_types"]:
                continue
            score = _score_keywords(keywords, [item["title"], item["summary"], item["snippet"], *item["keywords"]])
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda entry: entry[0], reverse=True)
        return [
            EvidenceItem(
                evidence_id=item["evidence_id"],
                evidence_type=evidence_type,
                title=item["title"],
                summary=item["summary"],
                snippet=item["snippet"],
                citation_label=item["title"],
                keywords=item["keywords"],
                source_ref=item["evidence_id"],
                metadata={"library": True},
                relevance_score=float(score),
            )
            for score, item in scored[:2]
        ]

    def _build_form_evidence(self, doc_type: str) -> EvidenceItem:
        form = FORM_LIBRARY[doc_type]
        return EvidenceItem(
            evidence_id=form["evidence_id"],
            evidence_type=EvidenceType.FORM,
            title=form["title"],
            summary=form["summary"],
            snippet=form["snippet"],
            citation_label=form["title"],
            keywords=form["keywords"],
            source_ref=form["evidence_id"],
            metadata={"library": True, "doc_type": doc_type},
            relevance_score=1.0,
        )

    def _dedupe_evidence(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        deduped: list[EvidenceItem] = []
        seen: set[str] = set()
        for item in items:
            if item.evidence_id in seen:
                continue
            seen.add(item.evidence_id)
            deduped.append(item)
        return deduped
