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
    max_output_tokens: int = 8192
    response_parse_retries: int = 1

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
        self._client = self._build_client()

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout_seconds,
            transport=self.transport,
        )

    async def aclose(self) -> None:
        if not self._client.is_closed:
            try:
                await self._client.aclose()
            except RuntimeError as error:
                if "Event loop is closed" not in str(error):
                    raise

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
        if self._client.is_closed:
            self._client = self._build_client()

        prompt = self._build_prompt(request, evidence_pack, plan)
        response_schema = self._build_response_schema(plan)
        generated: GeminiGeneratedDocument | None = None
        last_error: Exception | None = None

        for attempt in range(self.settings.response_parse_retries + 1):
            body = await self._request_sections(
                prompt=prompt if attempt == 0 else self._build_retry_prompt(prompt),
                response_schema=response_schema,
            )
            raw_text = self._extract_text(body)
            try:
                generated = GeminiGeneratedDocument.model_validate_json(self._strip_code_fence(raw_text))
                break
            except Exception as error:
                last_error = error
                finish_reason = ((body.get("candidates") or [{}])[0]).get("finishReason")
                logger.warning(
                    "gemini response parse failed | model=%s attempt=%s finish_reason=%s",
                    self.settings.model_name,
                    attempt + 1,
                    finish_reason,
                    exc_info=True,
                )
                if attempt >= self.settings.response_parse_retries:
                    raise RuntimeError("gemini response did not match expected document schema") from error

        if generated is None or not generated.sections:
            raise RuntimeError("gemini response did not contain any document sections")

        log_info(
            logger,
            "gemini document sections generated",
            context,
            model=self.settings.model_name,
            section_count=len(generated.sections),
        )
        return generated.sections

    async def _request_sections(
        self,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
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
        return response.json()

    def _build_retry_prompt(self, original_prompt: str) -> str:
        return "\n".join(
            [
                original_prompt,
                "",
                "중요: 직전 응답은 JSON schema를 지키지 못했다.",
                "설명 없이 responseJsonSchema와 정확히 일치하는 JSON 한 개만 다시 반환하라.",
            ]
        )

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
        instructions = self._build_prompt_instructions(request, plan)
        instructions.extend(
            [
                "",
                json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str),
            ]
        )
        return "\n".join(instructions)

    def _build_prompt_instructions(
        self,
        request: DocumentGenerationRequest,
        plan: DocumentPlan,
    ) -> list[str]:
        prompt_profile = request.constraints.prompt_profile
        if prompt_profile == "fact_finding_report":
            return self._build_fact_finding_report_instructions(plan)
        if prompt_profile == "committee_reference":
            return self._build_committee_reference_instructions(plan)
        if prompt_profile == "disciplinary_resolution":
            return self._build_disciplinary_resolution_instructions(plan)
        if prompt_profile == "attendance_notice":
            return self._build_attendance_notice_instructions(plan)
        return self._build_default_instructions()

    def _build_default_instructions(self) -> list[str]:
        return [
            "당신은 한국어 법률 문서 작성 보조 시스템이다.",
            "주어진 사실관계와 근거 범위를 벗어나 새로운 사실을 만들지 마라.",
            "각 section_id별로 실무 문안 수준의 본문을 2~4문장으로 작성하라.",
            "문서 전체는 정중하고 공식적인 톤으로 작성하라.",
            "형사 유죄 확정, 단정적 결론, 과도한 추정 표현은 피하라.",
            "open_issues에는 추가 확인이 필요한 항목만 짧게 넣고, 없으면 빈 배열을 넣어라.",
            "citations는 backend가 별도로 붙이므로 citation id나 각주 형식을 쓰지 마라.",
            "출력은 반드시 JSON schema를 따르는 JSON 한 개만 반환하라.",
        ]

    def _build_fact_finding_report_instructions(self, plan: DocumentPlan) -> list[str]:
        section_guide = {
            "overview": "조사 목적과 사건 개요만 간결하게 작성한다. 제목 번호는 쓰지 말고 본문만 작성한다.",
            "subject_profile": "다음 형식을 지켜 작성한다: '- 소속:', '- 직위/직급:', '- 성명:', '- 사건명:'. 확인되지 않으면 '자료상 명확하지 않음' 또는 '확인되지 않음'을 쓴다.",
            "allegations": "다음 형식을 지켜 작성한다: '- 혐의사실 1:', '- 혐의사실 2:'. 날짜, 시간, 장소, 행위, 결과를 빠짐없이 넣고 시간순으로 정리한다.",
            "findings": "다음 소제목을 유지한다: '- 인정되는 사실', '- 다툼이 있는 사항', '- 확인되지 않은 사항'. 인정 사실과 미확정 사실을 분리한다.",
            "evidence_summary": "다음 형식을 지켜 작성한다: '- 증거 1:', '- 증거 2:', '- 각 증거로 확인되는 내용:'. 각 사실과 증거가 대응되게 쓴다.",
            "mitigating_aggravating": "다음 형식을 지켜 작성한다: '- 유리한 정상:', '- 불리한 정상:'. 자료가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "integrated_opinion": "확인된 자료 범위에서만 건조하고 공적인 보고문체로 종합 의견을 작성한다.",
            "recommendation": "다음 형식을 지켜 작성한다: '- 징계의결 요구 여부 또는 추가 조사 필요 여부'. 단정하지 말고 현재 자료에 근거한 건의만 적는다.",
            "attachments": "첨부자료 목록을 항목형으로 정리한다. 입력상 첨부자료가 없으면 '첨부자료 없음'으로 적는다.",
        }
        ordered_section_guidance = [
            f"- {section.section_id} ({section.title}): {section_guide.get(section.section_id, section.purpose)}"
            for section in plan.sections
        ]
        return [
            "당신은 공공기관 징계사건 문서를 작성하는 조사관 보조 AI다.",
            "목표: 주어진 사실관계와 증거자료를 바탕으로 '사실결과조사보고'를 작성하라.",
            "내부적으로는 다음 순서대로 차례대로 검토하라: 조사 목적과 사건 개요 정리, 조사대상자 인적사항 확인, 혐의사실 시간순 정리, 사실-증거 대응, 인정 사실과 미확정 사실 구분, 정상자료와 불리한 사정 분리, 최종 건의사항 도출.",
            "그러나 출력에는 위 내부 검토 과정을 드러내지 말고, 완성된 보고서의 각 section 본문만 작성하라.",
            "주어진 사실관계와 근거 범위를 벗어나 새로운 사실을 만들지 마라.",
            "추정이나 단정은 금지하고, 기록과 진술에 의해 확인된 범위만 쓴다.",
            "증거와 사실은 반드시 대응되게 작성한다.",
            "날짜, 시간, 장소, 행위, 결과를 빠짐없이 쓴다.",
            "문체는 건조하고 공적인 보고문체로 쓴다.",
            "비난, 감정표현, 수사적 표현은 쓰지 마라.",
            "불명확한 부분은 '확인되지 않음', '자료상 명확하지 않음'으로 표기하라.",
            "기관 내부 규정이나 기존 별지서식이 evidence 또는 form 정보로 주어지면 그 형식을 우선 반영하라.",
            "입력이 부족해도 JSON schema는 반드시 채워야 하므로, 본문에는 '자료상 명확하지 않음'을 사용하고 open_issues에는 추가 필요 정보를 최대 5개까지 적어라.",
            "각 section_id는 아래 형식 지시를 따른다.",
            *ordered_section_guidance,
            "heading 번호와 section title은 backend가 붙이므로 section.text 안에 다시 반복하지 마라.",
            "citations는 backend가 별도로 붙이므로 citation id나 각주 형식을 쓰지 마라.",
            "출력은 반드시 JSON schema를 따르는 JSON 한 개만 반환하라.",
        ]

    def _build_attendance_notice_instructions(self, plan: DocumentPlan) -> list[str]:
        section_guide = {
            "personal_info": "다음 형식을 지켜 작성한다: '- 성명:', '- 소속:', '- 직위(직급):', '- 주소:'. 확인되지 않으면 '자료상 명확하지 않음'으로 적는다.",
            "appearance_reason": "방어권 보장에 필요한 정도로 징계혐의 또는 심의대상 사유를 구체적으로 적고, 감정적 표현은 쓰지 않는다.",
            "appearance_datetime": "다음 형식을 지켜 작성한다: '- YYYY년 MM월 DD일 HH시 MM분'. 출석 일시가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "appearance_location": "회의실명 또는 주소를 포함해 출석 장소를 특정한다. 자료가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "notes": "다음 4개 문구를 모두 유지한다: 진술권 포기서 제출, 서면진술 제출, 정당한 사유 없는 불출석 처리, 소명자료 또는 증빙자료 제출.",
            "notice_statement": "다음 형식을 지켜 작성한다: '- 관련 규정에 따라 위와 같이 귀하의 출석을 통지합니다.' 관련 규정 문구가 있으면 우선 반영한다.",
            "sender": "다음 형식을 지켜 작성한다: '- 통지일:', '- 징계위원회명:', '- 위원회 청인 또는 직인 표시'. 확인되지 않으면 '자료상 명확하지 않음'으로 적는다.",
            "recipient": "다음 형식을 지켜 작성한다: '- 귀하'.",
            "appendix": "다음 형식을 지켜 작성한다: '- 필요 시 진술권 포기서 양식'. 별첨이 없으면 '별첨 없음'으로 적는다.",
        }
        ordered_section_guidance = [
            f"- {section.section_id} ({section.title}): {section_guide.get(section.section_id, section.purpose)}"
            for section in plan.sections
        ]
        return [
            "당신은 징계위원회 사무를 지원하는 행정 문서 작성 AI다.",
            "목표: 주어진 정보에 따라 징계위원회 '출석통지서'를 작성하라.",
            "내부적으로는 다음을 순서대로 점검하라: 수신자 인적사항, 출석 요구 사유 특정 여부, 출석 일시와 장소 특정 여부, 진술권/서면진술/불출석 처리 안내 누락 여부, 기관명·위원회명·통지일 포함 여부.",
            "그러나 출력에는 내부 검토 과정을 드러내지 말고, 통지서 각 section의 본문만 작성하라.",
            "문체는 명확하고 단정적으로 유지하고, 불필요한 설명은 넣지 마라.",
            "징계사유는 방어권 보장에 필요한 정도로만 특정하고, 과도한 감정적 표현은 쓰지 마라.",
            "안내문구는 절차적 권리 보장 중심으로 작성하라.",
            "기관 내부 규정의 통지기한이나 문구가 evidence 또는 form 정보로 주어지면 이를 우선 반영하라.",
            "입력값이 부족해도 JSON schema는 반드시 채워야 하므로, 본문에는 '자료상 명확하지 않음'을 사용하고 open_issues에는 누락정보를 최대 5개까지 적어라.",
            "각 section_id는 아래 형식 지시를 따른다.",
            *ordered_section_guidance,
            "heading 번호와 section title은 backend가 붙이므로 section.text 안에 다시 반복하지 마라.",
            "citations는 backend가 별도로 붙이므로 citation id나 각주 형식을 쓰지 마라.",
            "출력은 반드시 JSON schema를 따르는 JSON 한 개만 반환하라.",
        ]

    def _build_committee_reference_instructions(self, plan: DocumentPlan) -> list[str]:
        section_guide = {
            "case_overview": "다음 형식을 지켜 작성한다: '- 사건명:', '- 심의 일시:', '- 심의 대상자:', '- 사건 요약:'. 심의 일시는 자료가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "subject_profile": "다음 형식을 지켜 작성한다: '- 소속:', '- 직위/직급:', '- 성명:'. 비공개 민감정보는 최소한으로만 적고 없으면 '자료상 명확하지 않음'으로 적는다.",
            "fact_summary": "다음 형식을 지켜 작성한다: '- 사실관계 1', '- 사실관계 2', '- 사실관계 3'. 사실만 시간순으로 적고 결론을 단정하지 않는다.",
            "issues": "다음 형식을 지켜 작성한다: '- 쟁점 1:', '- 쟁점 2:', '- 쟁점 3:'. 사실, 주장, 평가를 섞지 말고 위원회 판단 포인트만 요약한다.",
            "evidence_summary": "다음 형식을 지켜 작성한다: '- 증거 1: 무엇을 입증하는지', '- 증거 2: 무엇을 입증하는지', '- 증거 3: 무엇을 입증하는지'. 각 쟁점과 증거를 연결한다.",
            "statements": "다음 형식을 지켜 작성한다: '- 대상자 진술 요지:', '- 참고인/관계인 진술 요지:', '- 다툼이 있는 부분:'. 찬반 양쪽 요소를 균형 있게 적는다.",
            "mitigating_aggravating": "다음 형식을 지켜 작성한다: '- 유리한 정상:', '- 불리한 정상:'. 자료가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "applicable_rules": "다음 형식을 지켜 작성한다: '- 관련 법령/규정:', '- 검토 포인트:'. 최종 의결 결론이 아니라 심의 참고용 문체를 유지한다.",
            "judgment_points": "다음 형식을 지켜 작성한다: '- 사실인정 포인트', '- 양정 판단 포인트', '- 추가 확인 필요 사항'. 위원회가 추가로 확인할 사항을 분리한다.",
            "attachments": "첨부자료 목록을 항목형으로 정리한다. 입력상 자료가 없으면 '첨부자료 없음'으로 적는다.",
        }
        ordered_section_guidance = [
            f"- {section.section_id} ({section.title}): {section_guide.get(section.section_id, section.purpose)}"
            for section in plan.sections
        ]
        return [
            "당신은 징계위원회 위원들에게 배포할 '위원회 참고자료'를 작성하는 AI다.",
            "목표: 위원들이 징계사건을 신속하고 균형 있게 심의할 수 있도록, 사실, 쟁점, 증거, 정상사유를 구조적으로 정리한 참고자료를 작성하라.",
            "중요: 이 문서는 최종 의결서가 아니라 심의 보조자료다.",
            "결론을 단정하지 말고, 위원회 판단에 필요한 정보와 쟁점을 균형 있게 정리하라.",
            "내부적으로는 다음 순서대로 차례대로 검토하라: 사건 개요 요약, 심의대상자 인적사항 정리, 징계혐의 사실 시간순 배열, 쟁점별 증거 연결, 당사자 소명 요약, 정상참작 및 불리사정 분리, 적용 가능 규정과 양정 검토 포인트 도출, 위원회 판단 포인트 정리.",
            "그러나 출력에는 내부 검토 과정을 드러내지 말고, 참고자료 각 section의 본문만 작성하라.",
            "한 페이지에 들어온다고 가정하고 밀도 있게 요약하되 핵심 누락이 없게 쓴다.",
            "사실, 주장, 증거, 평가를 섞지 말고 구획을 나눠 적는다.",
            "찬반 양쪽 요소를 모두 적는다.",
            "위원회가 추가로 확인해야 할 사항이 있으면 별도 항목으로 뺀다.",
            "비공개 민감정보는 필요 최소한으로만 쓴다.",
            "최종 징계결론을 단정하지 말고 심의 참고용 문체를 유지하라.",
            "기관 내부 참고자료 양식이 evidence 또는 form 정보로 주어지면 그 형식을 우선 적용하라.",
            "입력이 부족해도 JSON schema는 반드시 채워야 하므로, 본문에는 '자료상 명확하지 않음'을 사용하고 open_issues에는 추가 필요 정보를 최대 5개까지 적어라.",
            "각 section_id는 아래 형식 지시를 따른다.",
            *ordered_section_guidance,
            "문서 제목은 backend가 별도로 표시하므로 section.text 안에 '제목:'이나 section title을 다시 반복하지 마라.",
            "citations는 backend가 별도로 붙이므로 citation id나 각주 형식을 쓰지 마라.",
            "출력은 반드시 JSON schema를 따르는 JSON 한 개만 반환하라.",
        ]

    def _build_disciplinary_resolution_instructions(self, plan: DocumentPlan) -> list[str]:
        section_guide = {
            "subject_profile": "다음 형식을 지켜 작성한다: '- 소속:', '- 직위(직급):', '- 성명:'. 확인되지 않으면 '자료상 명확하지 않음'으로 적는다.",
            "decision_order": "다음 형식을 지켜 작성한다: '- [예: 감봉 1월에 처한다 / 견책으로 의결한다]'. 최종 의결결론이 없으면 '자료상 명확하지 않음'으로 적는다.",
            "reasoning": "다음 구조를 반드시 유지한다: '가. 인정되는 사실', '나. 증거의 판단', '다. 적용 규정', '라. 양정 판단'과 그 아래 '- 비위의 정도', '- 고의/과실', '- 조직 영향', '- 유리한 정상', '- 불리한 정상'. 이유는 '징계의 원인이 된 사실 → 증거 판단 → 관계규정 → 양정 판단' 순서를 지킨다.",
            "decision_date": "다음 형식을 지켜 작성한다: '- 의결일자:'. 날짜가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "committee_name": "다음 형식을 지켜 작성한다: '- 징계위원회명:'. 자료가 없으면 '자료상 명확하지 않음'으로 적는다.",
            "committee_members": "다음 형식을 지켜 작성한다: '- 위원장 및 위원 표시'. 자료가 없으면 '자료상 명확하지 않음'으로 적는다.",
        }
        ordered_section_guidance = [
            f"- {section.section_id} ({section.title}): {section_guide.get(section.section_id, section.purpose)}"
            for section in plan.sections
        ]
        return [
            "당신은 징계위원회의 의결 내용을 공식 문서로 정리하는 AI다.",
            "목표: 주어진 심의 결과에 따라 '징계의결서'를 작성하라.",
            "내부적으로는 다음 순서대로 검토하라: 피징계자 인적사항 확인, 의결주문 확정, 인정 사실과 증거의 대응관계 정리, 적용 법령·규정 확인, 정상참작 또는 가중사유 반영 여부 점검, 이유 부분이 주문을 충분히 뒷받침하는지 검토.",
            "그러나 출력에는 내부 검토 과정을 드러내지 말고, 의결서 각 section의 본문만 작성하라.",
            "이유는 반드시 '징계의 원인이 된 사실 → 증거 판단 → 관계규정 → 양정 판단' 순서가 살아 있도록 쓴다.",
            "문체는 판단문 스타일로 쓰고, 사실과 평가를 혼동하지 마라.",
            "감경·가중 사유가 있으면 구체적으로 적는다.",
            "증거 없는 단정은 금지한다.",
            "기관 내부 서식이 evidence 또는 form 정보로 주어지면 그 형식을 우선 반영하라.",
            "이유는 짧아도 논리 구조가 무너지지 않게 작성하라.",
            "입력값이 부족해도 JSON schema는 반드시 채워야 하므로, 본문에는 '자료상 명확하지 않음'을 사용하고 open_issues에는 누락정보를 최대 5개까지 적어라.",
            "각 section_id는 아래 형식 지시를 따른다.",
            *ordered_section_guidance,
            "문서 제목은 backend가 별도로 표시하므로 section.text 안에 '제목:'이나 section title을 다시 반복하지 마라.",
            "citations는 backend가 별도로 붙이므로 citation id나 각주 형식을 쓰지 마라.",
            "출력은 반드시 JSON schema를 따르는 JSON 한 개만 반환하라.",
        ]

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
