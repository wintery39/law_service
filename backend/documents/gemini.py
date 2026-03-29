from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

from schemas import DocumentGenerationRequest, DocumentPlan, EvidenceItem, EvidencePack, ObservationContext
from storage.observability import get_logger, log_info


logger = get_logger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[1]


class GeminiGenerationSettings(BaseSettings):
    model_config = ConfigDict(
        env_prefix="GEMINI_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str | None = None
    model_name: str = "gemini-2.5-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: float = 30.0
    temperature: float = 0.3
    top_p: float = 0.95
    max_output_tokens: int = 4096

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


class GeminiGeneratedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    text: str = Field(min_length=1)
    open_issues: list[str] = Field(default_factory=list)


class GeminiGeneratedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[GeminiGeneratedSection]


@dataclass(slots=True)
class GeminiDocumentGenerator:
    settings: GeminiGenerationSettings
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient = field(init=False)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout_seconds,
            transport=self.transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def is_configured(self) -> bool:
        return self.settings.is_configured()

    async def generate_sections(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
        context: ObservationContext,
    ) -> list[GeminiGeneratedSection]:
        if not self.is_configured():
            raise RuntimeError("Gemini document generation is not configured. Set GEMINI_API_KEY.")

        prompt = self._build_prompt(request, evidence_pack, plan)
        response_schema = self._build_response_schema(plan)
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self.settings.temperature,
                "topP": self.settings.top_p,
                "maxOutputTokens": self.settings.max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema,
            },
        }

        try:
            response = await self._client.post(
                f"/models/{self.settings.model_name}:generateContent",
                headers={"x-goog-api-key": self.settings.api_key or ""},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            detail = ""
            if isinstance(error, httpx.HTTPStatusError):
                detail = error.response.text.strip()
            raise RuntimeError(f"gemini api request failed: {detail or error}") from error

        body = response.json()
        raw_text = self._extract_text(body)
        try:
            generated = GeminiGeneratedDocument.model_validate_json(self._strip_code_fence(raw_text))
        except Exception as error:
            raise RuntimeError("gemini response did not match expected document schema") from error

        if not generated.sections:
            raise RuntimeError("gemini response did not contain any document sections")

        log_info(
            logger,
            "gemini document sections generated",
            context,
            model=self.settings.model_name,
            section_count=len(generated.sections),
        )
        return generated.sections

    def _build_prompt(
        self,
        request: DocumentGenerationRequest,
        evidence_pack: EvidencePack,
        plan: DocumentPlan,
    ) -> str:
        structured_case = evidence_pack.structured_case
        prompt_payload = {
            "document_title": plan.title,
            "document_type": request.user_intent.doc_type,
            "user_text": request.user_text,
            "objective": request.user_intent.objective,
            "audience": request.user_intent.audience,
            "constraints": request.constraints.model_dump(mode="json"),
            "structured_case": {
                "narrative": structured_case.narrative,
                "as_of_date": structured_case.as_of_date.isoformat() if structured_case.as_of_date else None,
                "actors": [actor.model_dump(mode="json") for actor in structured_case.actors],
                "actions": [action.model_dump(mode="json") for action in structured_case.actions],
                "objects": [obj.model_dump(mode="json") for obj in structured_case.objects],
                "place": structured_case.place.model_dump(mode="json") if structured_case.place else None,
                "time": structured_case.time.model_dump(mode="json") if structured_case.time else None,
                "relationships": [relation.model_dump(mode="json") for relation in structured_case.relationships],
                "legal_terms": structured_case.legal_terms,
                "keyphrases": structured_case.keyphrases,
                "missing_slots": structured_case.missing_slots,
            },
            "plan": {
                "title": plan.title,
                "notes": plan.notes,
                "sections": [
                    {
                        "section_id": section.section_id,
                        "title": section.title,
                        "purpose": section.purpose,
                        "keyphrases": section.keyphrases,
                        "prohibited_phrases": section.prohibited_phrases,
                    }
                    for section in plan.sections
                ],
            },
            "evidence": [self._serialize_evidence(item) for item in evidence_pack.all_items()[:10]],
        }
        instructions = [
            "당신은 한국어 법률 문서 작성 보조 시스템이다.",
            "주어진 사실관계와 근거 범위를 벗어나 새로운 사실을 만들지 마라.",
            "각 section_id별로 실무 문안 수준의 본문을 2~4문장으로 작성하라.",
            "문서 전체는 정중하고 공식적인 톤으로 작성하라.",
            "형사 유죄 확정, 단정적 결론, 과도한 추정 표현은 피하라.",
            "open_issues에는 추가 확인이 필요한 항목만 짧게 넣고, 없으면 빈 배열을 넣어라.",
            "citations는 backend가 별도로 붙이므로 citation id나 각주 형식을 쓰지 마라.",
            "출력은 반드시 JSON schema를 따르는 JSON 한 개만 반환하라.",
            "",
            json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str),
        ]
        return "\n".join(instructions)

    def _build_response_schema(self, plan: DocumentPlan) -> dict[str, Any]:
        section_ids = [section.section_id for section in plan.sections]
        return {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "minItems": len(section_ids),
                    "maxItems": len(section_ids),
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_id": {"type": "string", "enum": section_ids},
                            "text": {"type": "string"},
                            "open_issues": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["section_id", "text", "open_issues"],
                        "propertyOrdering": ["section_id", "text", "open_issues"],
                    },
                }
            },
            "required": ["sections"],
            "propertyOrdering": ["sections"],
        }

    def _serialize_evidence(self, item: EvidenceItem) -> dict[str, Any]:
        return {
            "evidence_id": item.evidence_id,
            "evidence_type": item.evidence_type.value,
            "title": item.title,
            "summary": item.summary,
            "snippet": item.snippet,
            "citation_label": item.citation_label,
            "keywords": item.keywords,
            "metadata": item.metadata,
        }

    def _extract_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            prompt_feedback = payload.get("promptFeedback") or {}
            block_reason = prompt_feedback.get("blockReason") or "unknown"
            raise RuntimeError(f"gemini returned no candidates (block_reason={block_reason})")

        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if text:
                    return str(text)

        raise RuntimeError("gemini returned no text parts")

    def _strip_code_fence(self, text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
