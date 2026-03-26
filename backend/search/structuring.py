from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import ValidationError

from schemas.common import ObservationContext
from schemas.related_articles import (
    CaseAction,
    CaseActor,
    CaseDamage,
    CaseIntent,
    CaseObject,
    CasePlace,
    CaseTime,
    RelationshipInfo,
    RelatedArticleRequest,
    StructuredCase,
    UserProfile,
)
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
DATE_RE = re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})")

ACTION_KEYWORDS = {
    "폭행": ("폭행", "폭행", "criminal"),
    "구타": ("폭행", "구타", "criminal"),
    "상해": ("상해", "상해", "criminal"),
    "절도": ("절도", "절도", "criminal"),
    "반출": ("무단반출", "무단 반출", "military_special"),
    "훔": ("절도", "절취", "criminal"),
    "무단이탈": ("근무지이탈", "무단이탈", "disciplinary"),
    "이탈": ("근무지이탈", "이탈", "disciplinary"),
    "명령거부": ("명령거부", "명령거부", "disciplinary"),
    "명령 거부": ("명령거부", "명령 거부", "disciplinary"),
    "명령을 거부": ("명령거부", "명령 거부", "disciplinary"),
    "민원": ("불이익처분", "민원/처분", "administrative"),
    "처분": ("불이익처분", "행정처분", "administrative"),
    "의견제출": ("의견제출", "의견제출", "administrative"),
    "사전통지": ("사전통지", "사전통지", "administrative"),
    "청문": ("청문", "청문", "administrative"),
    "손해배상": ("손해배상", "손해배상", "civil"),
    "배상": ("손해배상", "배상", "civil"),
    "유출": ("기밀유출", "유출", "military_special"),
    "촬영": ("무단촬영", "무단촬영", "military_special"),
}

OBJECT_KEYWORDS = {
    "군용물": "military_property",
    "재물": "property",
    "물건": "property",
    "근무지": "duty_station",
    "처분": "administrative_decision",
    "사전통지": "notice",
    "의견": "opinion",
    "청문": "hearing",
    "손해": "damage",
    "기밀": "classified_info",
    "문서": "document",
    "명령": "order",
    "피해자": "person",
    "신체": "body",
    "휴대전화": "device",
    "사진": "recording",
}

PLACE_KEYWORDS = ["생활관", "근무지", "부대", "훈련장", "사무실", "보안구역", "창고", "행정기관"]
ACTOR_ROLES = ["병사", "군인", "상관", "부하", "민원인", "행정청", "피해자", "가해자", "지휘관"]
RELATION_KEYWORDS = {
    "상관": "superior-subordinate",
    "부하": "superior-subordinate",
    "선임": "senior-junior",
    "후임": "senior-junior",
    "동료": "peer",
}
STOPWORDS = {"관련", "문제", "상황", "정도", "때문", "경우", "대해", "있다", "했다", "합니다", "입니다"}
T = TypeVar("T")


class SchemaFillingLLM(ABC):
    @abstractmethod
    async def fill_case(
        self,
        request: RelatedArticleRequest,
        partial_case: StructuredCase | None,
        prompt: str,
        schema: dict[str, Any],
        context: ObservationContext,
    ) -> dict[str, Any]:
        raise NotImplementedError


class HeuristicSchemaFillingLLM(SchemaFillingLLM):
    async def fill_case(
        self,
        request: RelatedArticleRequest,
        partial_case: StructuredCase | None,
        prompt: str,
        schema: dict[str, Any],
        context: ObservationContext,
    ) -> dict[str, Any]:
        _ = prompt, schema, context
        narrative = request.user_text.strip()
        lower_text = narrative.lower()

        actions: list[CaseAction] = []
        legal_terms: list[str] = []
        for keyword, (verb, description, domain_tag) in ACTION_KEYWORDS.items():
            if keyword in lower_text:
                actions.append(CaseAction(verb=verb, description=description))
                legal_terms.extend([verb, domain_tag])

        objects: list[CaseObject] = []
        for keyword, category in OBJECT_KEYWORDS.items():
            if keyword in narrative:
                objects.append(CaseObject(name=keyword, category=category))

        actors: list[CaseActor] = []
        for role in ACTOR_ROLES:
            if role in narrative:
                actors.append(CaseActor(name=None, role=role, description=role))
        if "제가" in narrative or "나는" in narrative:
            actors.append(CaseActor(name="reporter", role="reporter", description="신고/상담 사용자"))
        if request.user_profile:
            actors.append(
                CaseActor(
                    name="user_profile",
                    role=request.user_profile.role,
                    description=request.user_profile.rank,
                )
            )

        place_name = next((keyword for keyword in PLACE_KEYWORDS if keyword in narrative), None)
        place = CasePlace(name=place_name, jurisdiction=request.jurisdiction or "kr") if place_name else None

        time_match = DATE_RE.search(narrative)
        if time_match:
            time = CaseTime(mentioned_text=time_match.group(0), as_of_date=time_match.group(0))
        elif any(token in narrative for token in ("어제", "오늘", "지난주", "지난달")):
            time = CaseTime(mentioned_text="relative-time", as_of_date=request.as_of_date)
        else:
            time = None

        intent = None
        if "고의" in narrative or "보복" in narrative:
            intent = CaseIntent(description="고의 가능성 언급", level="intentional")
        elif "실수" in narrative or "과실" in narrative:
            intent = CaseIntent(description="과실/실수 언급", level="negligent")

        damage = None
        if any(token in narrative for token in ("부상", "상해", "다쳤")):
            damage = CaseDamage(physical="신체 피해 언급")
        elif any(token in narrative for token in ("손해", "파손", "배상")):
            damage = CaseDamage(property="재산상 손해 언급")
        elif "징계" in narrative:
            damage = CaseDamage(disciplinary="징계 위험 언급")

        relationships = [
            RelationshipInfo(subject=None, object=None, relation=relation)
            for keyword, relation in RELATION_KEYWORDS.items()
            if keyword in narrative
        ]

        keyphrases = _extract_keyphrases(narrative, legal_terms)
        return StructuredCase(
            session_id=request.session_id,
            narrative=narrative,
            jurisdiction=request.jurisdiction or "kr",
            as_of_date=request.as_of_date,
            user_profile=request.user_profile,
            actors=_unique_models(actors),
            actions=_unique_models(actions),
            objects=_unique_models(objects),
            time=time,
            place=place,
            intent=intent,
            damage=damage,
            relationships=_unique_models(relationships),
            roles=_unique_strings([actor.role for actor in actors if actor.role]),
            legal_terms=_unique_strings(legal_terms),
            keyphrases=keyphrases,
            missing_slots=[],
        ).model_dump(mode="python")


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _unique_models(values: list[T]) -> list[T]:
    result: list[T] = []
    seen: set[str] = set()
    for value in values:
        key = repr(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _extract_keyphrases(text: str, legal_terms: list[str]) -> list[str]:
    tokens = [token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]
    return _unique_strings([*legal_terms, *tokens])[:20]


def merge_structured_cases(
    base: StructuredCase | None,
    update: StructuredCase,
) -> StructuredCase:
    if base is None:
        return update

    merged = update.model_copy(deep=True)
    merged.narrative = "\n".join(filter(None, [base.narrative, update.narrative]))
    merged.actors = _unique_models([*base.actors, *update.actors])
    merged.actions = _unique_models([*base.actions, *update.actions])
    merged.objects = _unique_models([*base.objects, *update.objects])
    merged.relationships = _unique_models([*base.relationships, *update.relationships])
    merged.roles = _unique_strings([*base.roles, *update.roles])
    merged.legal_terms = _unique_strings([*base.legal_terms, *update.legal_terms])
    merged.keyphrases = _unique_strings([*base.keyphrases, *update.keyphrases])
    merged.time = update.time or base.time
    merged.place = update.place or base.place
    merged.intent = update.intent or base.intent
    merged.damage = update.damage or base.damage
    merged.user_profile = update.user_profile or base.user_profile
    merged.as_of_date = update.as_of_date or base.as_of_date
    return merged


def detect_missing_slots(structured_case: StructuredCase) -> list[str]:
    missing: list[str] = []
    if not structured_case.actors:
        missing.append("actors")
    if not structured_case.actions:
        missing.append("actions")
    if not structured_case.objects:
        missing.append("objects")
    if structured_case.time is None:
        missing.append("time")
    if structured_case.place is None:
        missing.append("place")
    return missing


QUESTION_TEMPLATES = {
    "actors": "누가 어떤 지위에서 관련되었는지 알려주세요. 예: 병사, 상관, 민원인, 행정청",
    "actions": "문제가 된 행위가 무엇인지 구체적으로 적어주세요. 예: 폭행, 무단이탈, 처분, 손해배상 요구",
    "objects": "무엇을 대상으로 한 문제인지 알려주세요. 예: 군용물, 행정처분, 기밀자료, 재물",
    "time": "언제 발생했는지 알려주세요. 예: 2024-03-01, 어제, 지난주",
    "place": "어디에서 발생했는지 알려주세요. 예: 생활관, 근무지, 보안구역, 행정기관",
}


def build_clarification_questions(missing_slots: list[str]) -> list[str]:
    return [QUESTION_TEMPLATES[slot] for slot in missing_slots if slot in QUESTION_TEMPLATES]


class StructuredCaseService:
    def __init__(
        self,
        llm: SchemaFillingLLM | None = None,
        max_retries: int = 3,
    ) -> None:
        self.llm = llm or HeuristicSchemaFillingLLM()
        self.max_retries = max_retries
        self._sessions: dict[str, StructuredCase] = {}

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def structure(
        self,
        request: RelatedArticleRequest,
        context: ObservationContext,
    ) -> tuple[StructuredCase, dict[str, Any]]:
        partial = self._sessions.get(request.session_id)
        if request.structured_case is not None:
            partial = merge_structured_cases(partial, request.structured_case)
        schema = StructuredCase.model_json_schema()
        debug_attempts: list[dict[str, Any]] = []
        prompt = "Fill only the StructuredCase schema."

        for attempt in range(1, self.max_retries + 1):
            raw_payload = await self.llm.fill_case(request, partial, prompt, schema, context)
            try:
                candidate = StructuredCase.model_validate(raw_payload)
                merged = merge_structured_cases(partial, candidate)
                merged.missing_slots = detect_missing_slots(merged)
                self._sessions[request.session_id] = merged
                log_info(logger, "structured case created", context, attempt=attempt, missing_slots=merged.missing_slots)
                debug_attempts.append({"attempt": attempt, "status": "ok"})
                return merged, {"schema_attempts": debug_attempts}
            except ValidationError as error:
                debug_attempts.append({"attempt": attempt, "status": "validation_error", "error": str(error)})
                prompt = (
                    "Previous JSON failed validation. Return a valid JSON object matching the schema exactly. "
                    f"Validation error: {error}"
                )

        raise RuntimeError("structured case validation failed after retries")
