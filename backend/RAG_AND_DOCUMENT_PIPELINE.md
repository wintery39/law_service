# RAG 및 LLM 문서 생성 파이프라인 상세

이 문서는 `backend`가 사건 입력을 받아 어떤 RAG 단계를 거쳐 어떤 LLM/heuristic 생성 단계를 수행한 뒤 최종 문서를 반환하는지 코드 기준으로 정리한 구현 문서다. 대상 독자는 다음과 같다.

- `/services/documents/generate` 또는 `/services/related-articles/find`를 직접 디버깅해야 하는 개발자
- `/api/cases` 생성 시 어떤 내부 파이프라인이 동시에 실행되는지 확인해야 하는 프론트/백엔드 개발자
- prompt profile, evidence grounding, evaluator 경고가 어떤 순서로 붙는지 이해해야 하는 운영자

이 문서는 "목표 아키텍처"가 아니라 2026-04-01 기준 현재 코드가 실제로 수행하는 순서를 설명한다.

## 1. 한눈에 보는 전체 흐름

### 1-1. 독립 문서 생성 엔진 호출

```text
POST /services/documents/generate
  -> CaseDocumentGenerationRequest
  -> build_document_generation_request()
  -> DocumentGenerationService.generate()
       -> stream()
          -> _prepare_generation()
             -> EvidenceCollector.collect()
                -> RelatedArticleFinderService.handle()
                   -> StructuredCaseService.structure()
                   -> DomainRouter.classify()
                   -> RetrievalPipeline.retrieve()
                   -> RetrievalEvaluator.evaluate()
                -> CASE / REGULATION / FORM evidence 보강
             -> DocumentPlanner.create_plan()
             -> collect_additional_for_plan()   # 옵션
          -> _generate_sections()
             -> Gemini or heuristic
             -> Gemini 성공 시 heuristic citation/open_issues와 merge
          -> _build_response()
             -> DocumentDraftEvaluator.evaluate()
             -> EvidenceReport 생성
  -> DocumentGenerationResponse
```

### 1-2. 프론트의 사건 생성 호출

```text
POST /api/cases
  -> CaseWorkflowService.create_case()
     -> _generate_initial_document_artifacts()
        -> 사실결과조사보고
        -> 출석통지서
        -> 위원회 참고자료
        -> 징계의결서
        -> 각 문서별로 DocumentGenerationService.generate() 병렬 실행
     -> _build_document_templates()
     -> _render_generated_document_content()
     -> CaseDetail / DocumentRecord / workflow stage 조립
  -> 프론트가 바로 쓰는 사건 상세 응답
```

즉, `backend`에는 문서 생성 경로가 2개 있다.

- 엔진 직접 호출 경로
  - `/services/documents/generate`
  - 문서 생성 파이프라인만 독립적으로 검증할 때 사용한다.
- 프론트 오케스트레이션 경로
  - `/api/cases`
  - 사건 생성과 동시에 여러 문서 초안을 한 번에 만들고 프론트용 shape로 감싼다.

## 2. 서비스 객체가 어떻게 연결되는가

서비스 초기화는 [`main.py`](./main.py) 의 `ServiceContainer`에서 이뤄진다.

```text
InMemoryCorpusRepository
InMemoryGraphStore
InMemoryTextSearchStore
InMemoryVectorStore
  -> RelatedArticleFinderService
     -> InProcessRelatedArticlesClient
        -> EvidenceCollector
           -> DocumentGenerationService
              -> CaseWorkflowService
```

현재 기본 조합은 다음과 같다.

- 코퍼스 저장소: in-memory
- graph 저장소: in-memory adjacency
- text search: token overlap 기반 in-memory search
- vector search: token count cosine 기반 pseudo-vector search
- 문서 생성 provider: `DocumentGenerationSettings(generation_provider="auto")`
  - `GEMINI_API_KEY`가 있으면 Gemini 우선
  - Gemini 호출 실패 시 heuristic fallback

이 때문에 현재 `backend`의 RAG는 "실제 OpenSearch + embedding DB + graph DB"가 아니라, 동일한 인터페이스를 가진 데모 구현 위에서 동작한다.

## 3. 입력이 문서 생성 요청으로 바뀌는 단계

문서 생성 엔진이 직접 받는 내부 요청 객체는 `DocumentGenerationRequest`다. 프론트나 외부 API는 이 스키마를 직접 보내지 않고, 먼저 `CaseDocumentGenerationRequest`를 보낸다.

변환은 [`schemas/documents.py`](./schemas/documents.py) 의 `build_document_generation_request()`가 담당한다.

### 3-1. 입력 스키마

외부 입력 `CaseDocumentGenerationRequest`는 다음 필드를 가진다.

- `title`
- `caseType`
- `occurredAt`
- `location`
- `author`
- `relatedPersons`
- `summary`
- `details`

### 3-2. 내부 narrative 생성

변환기는 먼저 `_build_case_narrative()`로 아래와 같은 서술형 텍스트를 만든다.

```text
사건 제목: ...
사건 유형: ...
발생 일시: ...
발생 장소: ...
작성자: ...
관련자: ...
사건 개요: ...
상세 사실관계: ...
```

이 narrative는 이후 여러 단계에서 재사용된다.

- 구조화 입력
- Gemini prompt payload
- heuristic generator의 narrative field 파싱
- prompt profile용 추가 보조 필드 주입

### 3-3. 초기 `StructuredCase` seed 생성

`build_document_generation_request()`는 빈 상태에서 시작하지 않는다. 사건 생성 시점에 이미 알고 있는 메타데이터로 `StructuredCase` seed를 만든다.

- `actors`
  - `작성자 ...`, `관련자 ...` description이 들어간다.
- `time`
  - `occurredAt` 기준일이 들어간다.
- `place`
  - `location`이 들어간다.
- `legal_terms`
  - 사건 유형 label과 alias가 들어간다.
- `keyphrases`
  - 사건 제목, 장소, 작성자, 관련자, summary/details token이 들어간다.

이 seed는 이후 `StructuredCaseService.structure()`가 heuristic extraction 결과와 merge한다.

### 3-4. 초기 doc_type 추론

기본 추론 규칙은 `_infer_doc_type()`에 있다.

- `disciplinary` 사건이면 기본 `disciplinary_opinion`
- defense hint가 있으면 `defense_draft`
- 그 외는 case type별 자동 매핑

주의할 점:

- `/services/documents/generate`를 직접 호출하면 이 기본 추론 규칙이 적용된다.
- `/api/cases` 경로는 이 기본값을 그대로 쓰지 않고 문서별로 `user_intent.doc_type`과 `prompt_profile`을 다시 덮어쓴다.

## 4. RAG 1단계: EvidenceCollector가 관련 조항 찾기 파이프라인을 호출한다

문서 생성 파이프라인에서 RAG의 시작점은 [`documents/evidence.py`](./documents/evidence.py) 의 `EvidenceCollector.collect()`다.

이 단계는 단순히 "법령 몇 건 찾기"가 아니라, 문서 생성기가 바로 쓸 수 있는 `EvidencePack`을 조립하는 단계다.

### 4-1. RelatedArticleRequest 생성

`collect()`는 `DocumentGenerationRequest`를 `RelatedArticleRequest`로 변환한다.

- `session_id`
- `user_text`
- `structured_case`
- `as_of_date`
- `jurisdiction`
- `user_profile`

이 요청은 `InProcessRelatedArticlesClient`를 통해 같은 프로세스 내부의 `RelatedArticleFinderService.handle()`로 전달된다.

즉, 문서 생성 RAG는 검색용 엔진을 다시 HTTP로 치는 구조가 아니라, 같은 DI container 안에서 직접 호출하는 구조다.

## 5. RAG 2단계: RelatedArticleFinderService 내부 파이프라인

관련 조항 찾기 서비스는 [`search/pipeline.py`](./search/pipeline.py) 의 `RelatedArticleFinderService.handle()`에 있다.

### 5-1. 사실관계 구조화

구조화는 [`search/structuring.py`](./search/structuring.py) 의 `StructuredCaseService.structure()`가 수행한다.

현재 기본 구현은 `HeuristicSchemaFillingLLM`이다. 이름은 LLM 인터페이스를 따르지만 실제 기본 동작은 heuristic extraction이다.

추출되는 주요 요소:

- `actors`
- `actions`
- `objects`
- `time`
- `place`
- `intent`
- `damage`
- `relationships`
- `roles`
- `legal_terms`
- `keyphrases`

입력 narrative에서 다음과 같은 heuristic을 사용한다.

- `ACTION_KEYWORDS`
  - 예: `반출` -> `무단반출`, `명령거부` -> `명령거부`
- `OBJECT_KEYWORDS`
  - 예: `기밀`, `군용물`, `재물`, `명령`
- `PLACE_KEYWORDS`
  - 예: `생활관`, `보안구역`, `창고`
- 상대시간 / 날짜 regex
- `고의`, `실수`, `과실`, `징계`, `상해`, `손해` 등의 intent/damage 힌트

구조화 결과는 기존 partial case와 merge되고, `detect_missing_slots()`로 다음 누락 슬롯을 계산한다.

- `actors`
- `actions`
- `objects`
- `time`
- `place`

### 5-2. clarify 분기

다음 조건이면 검색으로 바로 가지 않고 `ClarifyResponse`를 반환한다.

- critical missing slot 존재
  - `actors`, `actions`, `objects`
- 또는 누락 슬롯 개수가 4개 이상

이 경우 반환값은 다음과 같다.

- `type: "clarify"`
- `questions`
- `missing_slots`
- `partial_structured_case`

문서 생성 서비스는 이 결과를 받아도 중단하지 않고 계속 진행한다. 다만 이 경우 관련 조항 찾기 서비스가 돌려준 `final` 법령 후보는 비어 있고, 이후 `EvidenceCollector`가 CASE/REGULATION/FORM library와 form evidence를 별도로 보강한다. 즉, 현재 구조는 "clarify가 오면 문서 생성 자체를 멈추는" 구조가 아니라 "missing info를 checklist로 들고, 검색 근거가 부족한 상태의 초안을 계속 만드는" 구조다.

### 5-3. 도메인 라우팅

clarify가 아니면 [`search/routing.py`](./search/routing.py) 의 `DomainRouter.classify()`가 실행된다.

이 라우터는 다음 term pool을 보고 점수를 쌓는다.

- `structured_case.legal_terms`
- `structured_case.keyphrases`
- `actions[].verb`
- `objects[].name`

도메인 후보:

- `criminal`
- `disciplinary`
- `administrative`
- `civil`
- `military_special`

출력은 `DomainRoute`다.

- `labels`
- `scores`
- `filter_hints`

현재 구현에서 route의 실질 영향은 제한적이다. in-memory retrieval 본체는 route를 hard filter로 쓰지 않고, route 정보는 주로 `build_opensearch_query()` debug payload와 후속 evidence metadata에 남는다. 즉 "현재 코드 기준"으로는 route가 검색을 강하게 좁히기보다, 분류 결과를 보존하는 역할에 더 가깝다.

### 5-4. hybrid retrieval

실제 retrieval은 [`search/retrieval.py`](./search/retrieval.py) 의 `RetrievalPipeline.retrieve()`가 담당한다.

이 단계는 3개 채널을 동시에 사용한다.

#### 채널 A. text search

`InMemoryTextSearchStore.search()`

- 문서 heading/body token overlap 점수 사용
- query는 `build_query_terms()`로 만든 전체 query term을 합친 문자열

현재는 BM25가 아니라 token overlap 기반의 데모 구현이다.

#### 채널 B. pseudo-vector search

`InMemoryVectorStore.similarity_search()`

- token count embedding
- cosine similarity

즉 현재 vector 검색은 실제 embedding 모델이 아니라 "bag-of-words cosine"에 가까운 단순화 구현이다.

#### 채널 C. graph expansion

`RetrievalPipeline._expand_graph()`

1. query term 상위 8개를 seed로 삼는다.
2. 각 seed별 text search top 3 unit을 graph seed hit로 잡는다.
3. graph neighbor를 BFS로 최대 2 hop 탐색한다.
4. depth가 깊어질수록 가중치를 줄여 점수를 누적한다.

graph edge 출처는 [`graph/store.py`](./graph/store.py) 에서 적재된다.

- parent-child
- reference outbound/inbound

### 5-5. RRF fusion

세 채널 결과는 `reciprocal_rank_fusion()`으로 합쳐진다.

- 입력 채널: `text`, `vector`, `graph`
- 출력: `rrf_score`, `source_channels`를 가진 fused candidate list

이 단계 결과는 아직 "후보"일 뿐이다. 실제로 쓸 수 있는 근거인지 판단하는 evaluator가 다음 단계에 있다.

### 5-6. retrieval evaluator

후보 검증은 [`search/evaluation.py`](./search/evaluation.py) 의 `RetrievalEvaluator.evaluate()`가 담당한다.

#### hard filter

다음 조건에 걸리면 `filtered_out`으로 빠지고 final candidate로 가지 않는다.

- 관할 불일치 `jurisdiction_mismatch`
- 최소 인용 단위 미달 `not_minimum_unit`
  - article, paragraph, item, subitem만 허용
- 기준일보다 아직 시행 전
  - `not_effective_yet`
  - `unit_not_effective_yet`
- 폐지 또는 실효 상태
  - `repealed_or_expired`

#### rerank / scoring

통과한 후보는 다음 점수로 다시 계산된다.

- `rrf_score`
- `coverage_score`
  - 사건 term이 unit text에 얼마나 들어가는지
- `rubric_score`
  - `HeuristicRubricScorer`가 relevance/evidence/overclaim risk를 계산
- `final_score`
  - 위 값을 조합한 최종 점수

반환 결과는 3종이다.

- `candidates`
  - 필터 통과 후 정렬된 전체 후보
- `final`
  - 상위 `top_n`개
- `debug.filtered_out`

## 6. RAG 3단계: 검색 결과를 문서 생성용 EvidencePack으로 바꾼다

`EvidenceCollector.collect()`는 `ResultResponse.final`을 그대로 넘기지 않고 `EvidencePack`으로 재구성한다.

### 6-1. 법령/규정 evidence 변환

`RelatedArticleCandidate`는 `_candidate_to_evidence()`를 거쳐 `EvidenceItem`으로 변환된다.

- `law_name`에 `규정`, `규율`, `훈령`, `예규`, `지침`, `규칙`이 있으면 `EvidenceType.REGULATION`
- 아니면 `EvidenceType.LAW`

즉 retrieval final 결과는 먼저 `laws`와 `regulations`로 분리된다.

### 6-2. 문서 타입별 library evidence 보강

현재 문서 생성은 retrieval final만 쓰지 않는다. 아래 보강 source도 함께 사용한다.

- `CASE_LIBRARY`
- `REGULATION_LIBRARY`
- `FORM_LIBRARY`

의미:

- `CASE_LIBRARY`
  - 징계 판단례, 사전통지 판단례 같은 데모용 case reference
- `REGULATION_LIBRARY`
  - 문서 작성 기준, 징계 양정 기준 같은 보조 규정
- `FORM_LIBRARY`
  - 문서 기본 양식 evidence

선택 방식:

- `StructuredCase`와 request에서 뽑은 keyword로 library item을 score
- 현재 문서 `doc_type`에 맞는 항목만 추린다.
- form evidence는 문서 타입당 1개 기본 양식을 항상 넣는다.

### 6-3. 최종 EvidencePack 구조

최종 `EvidencePack`은 다음 필드를 가진다.

- `structured_case`
- `route_labels`
- `laws`
- `cases`
- `regulations`
- `forms`
- `source_debug`

`source_debug`에는 최소한 아래 정보가 들어간다.

- `related_articles_type`
  - `clarify` 또는 `result`
- `related_checklist_missing_info`
- `base_keywords`

## 7. 문서 계획 단계

계획은 [`documents/planning.py`](./documents/planning.py) 의 `DocumentPlanner.create_plan()`에서 생성된다.

### 7-1. 어떤 template를 쓸 것인가

기본 선택 순서는 다음과 같다.

1. `request.constraints.prompt_profile`이 있으면 `PROMPT_PROFILE_PLAN_TEMPLATES`
2. 없으면 `PLAN_TEMPLATES[request.user_intent.doc_type]`

즉 prompt profile은 단순 프롬프트 문구만 바꾸는 게 아니라, section set 자체를 바꾼다.

예:

- 기본 `disciplinary_opinion`
  - `violation_summary`, `applicable_rules`, `mitigation_aggravation`, `opinion`
- `committee_reference`
  - `case_overview`, `issues`, `judgment_points` 등 10개 섹션
- `disciplinary_resolution`
  - `subject_profile`, `decision_order`, `reasoning`, `decision_date`, `committee_name`, `committee_members`

### 7-2. 각 section에 무엇이 붙는가

각 section은 `SectionPlan`으로 변환된다.

- `section_id`
- `title`
- `purpose`
- `keyphrases`
- `required_evidence_types`
- `required_evidence_ids`
- `prohibited_phrases`

`required_evidence_ids`는 evidence type별 첫 번째 evidence를 붙이는 방식으로 채워진다. 즉 planner 단계에서 이미 "이 섹션은 어떤 유형의 근거를 최소 하나는 가져야 하는가"가 선언된다.

### 7-3. planner notes와 추가 retrieval keyword

planner는 두 가지 부가 산출물을 남긴다.

- `notes`
  - 누락 정보
  - extra instruction
- `additional_retrieval_keywords`
  - section keyphrases를 모아 만든 후속 검색 키워드

이 추가 키워드는 다음 단계의 plan retrieval loop에서 사용된다.

## 8. plan retrieval loop

`DocumentGenerationService._prepare_generation()`은 planner 이후 선택적으로 `collect_additional_for_plan()`을 한 번 더 호출한다.

동작 조건:

- `DocumentGenerationSettings.enable_plan_retrieval_loop == True`
- `request.constraints.enable_plan_retrieval_loop == True`

현재 기본값은 둘 다 `True`다.

### 8-1. 무엇을 추가로 찾는가

`EvidenceCollector.collect_additional_for_plan()`은 `plan.additional_retrieval_keywords[:6]`를 순회하면서:

- text search top 2 law/regulation unit을 추가
- `CASE_LIBRARY`를 같은 키워드로 다시 조회
- `REGULATION_LIBRARY`도 다시 조회

### 8-2. 중복 제거

이미 있는 법령 unit은 `source_ref` 기준으로 걸러낸다.

### 8-3. planner note 보강

추가 회수된 evidence 개수는 plan note에 기록된다.

- 예: `추가 근거 회수: 3건`

즉 현재 문서 생성은 "retrieval 1회 -> generate"가 아니라, 최소한 설계상으로는 "retrieval -> planning -> 추가 retrieval -> generate" 순서를 가진다.

## 9. 생성 provider 선택

provider 선택은 [`documents/service.py`](./documents/service.py) 의 `_should_use_gemini()`와 `DocumentGenerationSettings.generation_provider`로 결정된다.

값은 3가지다.

- `auto`
- `heuristic`
- `gemini`

동작:

- `heuristic`
  - 무조건 heuristic
- `gemini`
  - 무조건 Gemini
  - Gemini 호출 실패 시 예외를 그대로 올린다.
- `auto`
  - `gemini_generator`가 있고 `GEMINI_API_KEY`가 설정되어 있으면 Gemini 시도
  - 실패하면 warning log 후 heuristic fallback

현재 기본 container는 `auto`다.

## 10. Gemini 경로

Gemini 경로는 [`documents/gemini.py`](./documents/gemini.py) 의 `GeminiDocumentGenerator.generate_sections()`가 담당한다.

### 10-1. prompt payload

Gemini prompt는 다음 정보로 구성된다.

- document title
- document type
- `user_text`
- objective / audience
- `constraints`
- `structured_case`
- `plan`
- evidence 상위 10개

즉 LLM은 원문 narrative만 보는 것이 아니라:

- 구조화된 case object
- section 목적
- 금지 표현
- evidence list

를 함께 본다.

### 10-2. prompt profile별 전문 프롬프트

`_build_prompt_instructions()`는 prompt profile에 따라 전용 지시문을 만든다.

- `fact_finding_report`
- `attendance_notice`
- `committee_reference`
- `disciplinary_resolution`
- 그 외 기본 generic prompt

전용 프롬프트는 공통적으로 다음 원칙을 가진다.

- 출력은 JSON schema 하나만 반환
- section title을 다시 쓰지 않음
- citation id를 본문에 직접 쓰지 않음
- 부족한 정보는 본문에 `자료상 명확하지 않음`, `open_issues`에 누락항목으로 표현

### 10-3. response schema

Gemini는 자유 텍스트를 바로 반환하지 않는다. `responseMimeType=application/json`, `responseJsonSchema`를 함께 보낸다.

schema는 section 수와 section id를 planner가 정한 값으로 고정한다.

즉 LLM이 임의 섹션을 늘리거나 줄일 수 없게 설계돼 있다.

### 10-4. parse retry

Gemini 응답이 malformed JSON이면:

1. `_extract_text()`로 raw text를 꺼낸다.
2. code fence를 제거한다.
3. `GeminiGeneratedDocument`로 validation한다.
4. 실패 시 `_build_retry_prompt()`를 붙여 1회 재시도한다.

기본 설정:

- `max_output_tokens = 8192`
- `response_parse_retries = 1`

### 10-5. Gemini가 반환하는 것은 무엇인가

Gemini는 section별로 다음만 반환한다.

- `section_id`
- `text`
- `open_issues`

중요:

- citation은 Gemini가 반환하지 않는다.
- evidence id도 Gemini가 직접 반환하지 않는다.

즉 grounding은 LLM 출력 자체보다 backend merge 단계에서 보강된다.

## 11. heuristic 생성 경로

heuristic 생성은 [`documents/generator.py`](./documents/generator.py) 의 `DocumentSectionGenerator`가 담당한다.

### 11-1. 기본 문서 타입

기본 `fact_summary`, `disciplinary_opinion`, `defense_draft`는 아래 방식으로 생성한다.

- section purpose에 맞는 opening sentence
- 사건 요약 sentence
- 사실 상세
- evidence summary
- open issue / next step

`required_evidence_types`가 있는데 citation이 하나도 없으면 `필요 근거 부족: ...`를 `open_issues`에 추가한다.

### 11-2. prompt profile 전용 heuristic

prompt profile 문서들은 generic generator를 쓰지 않고 전용 분기로 생성된다.

- `_generate_fact_finding_report_section()`
- `_generate_attendance_notice_section()`
- `_generate_committee_reference_section()`
- `_generate_disciplinary_resolution_section()`

이 전용 분기들은 `request.user_text`의 narrative를 다시 파싱해:

- 사건 제목
- 발생 시각/장소
- 관련자
- 첨부자료 요약
- 의결일자 / 위원회명 같은 보조 필드

를 section format에 맞게 강제로 채운다.

즉 Gemini가 실패해도 prompt profile 문서의 형식은 유지된다.

### 11-3. citation 부여 방식

heuristic generator는 section별 `required_evidence_types`에 맞춰 evidence를 고른 뒤 `citations`를 채운다.

이 citation은 나중에 Gemini merge 시에도 그대로 유지된다.

## 12. Gemini 결과와 heuristic 결과를 어떻게 합치는가

Gemini가 성공하면 backend는 heuristic을 버리지 않는다. [`documents/service.py`](./documents/service.py) 의 `_merge_sections_with_heuristics()`가 다음 방식으로 합친다.

1. planner의 각 section에 대해 heuristic section을 먼저 생성한다.
2. Gemini가 같은 `section_id`를 반환했으면:
   - `text`는 Gemini text로 교체
   - `citations`는 heuristic citation 유지
   - `open_issues`는 Gemini + heuristic을 merge
3. Gemini가 해당 section을 반환하지 않았으면 heuristic section 그대로 사용

이 설계의 의미는 다음과 같다.

- LLM은 문안 품질 담당
- backend heuristic은 grounding metadata 담당

즉 현재 시스템은 "LLM이 citation까지 직접 결정하는 구조"가 아니라 "backend가 grounding skeleton을 유지하면서 LLM 텍스트를 얹는 구조"다.

## 13. prompt profile text normalization

Gemini 출력은 종종 bullet이나 소제목 줄바꿈이 깨질 수 있다. 이를 위해 `DocumentGenerationService._normalize_generated_text()`가 prompt profile별 marker를 기준으로 줄바꿈을 보정한다.

예:

- `- 소속:`
- `- 혐의사실 1:`
- `가. 인정되는 사실`
- `- 관련 법령/규정:`

이 단계 덕분에 LLM이 한 줄로 붙여 반환해도 frontend에는 읽을 수 있는 구조로 내려간다.

## 14. Draft Evaluator 단계

최종 응답 조립 전, [`documents/evaluation.py`](./documents/evaluation.py) 의 `DocumentDraftEvaluator.evaluate()`가 다음 검사를 수행한다.

### 14-1. schema 검사

- planner에 있는 필수 section이 draft에 존재하는가
- section text가 비어 있지 않은가

### 14-2. citation 검사

- section citation이 실제 evidence pack id에 존재하는가
- 근거가 필요한 section인데 citation이 비어 있지 않은가

### 14-3. 날짜 검사

section text 안의 날짜가 다음 known date와 맞는지 본다.

- `request.as_of_date`
- `structured_case.as_of_date`
- `structured_case.time.as_of_date`
- evidence metadata의 `effective_at`, `amended_at`

### 14-4. 용어 / 금지 표현 검사

- structured case 핵심 용어가 초안에 충분히 반영됐는지
- doc_type별 치환 권고 용어가 있는지
  - 예: `disciplinary_opinion`에서 `처벌` 대신 `징계 검토`
- planner 금지 표현이 남아 있는지

Evaluator는 문서를 막지 않고 `warnings`를 반환한다. 즉 현재 구현은 regeneration loop를 자동으로 돌리지 않고, 경고를 응답에 남기는 구조다.

## 15. 최종 응답 객체

`DocumentGenerationService._build_response()`는 아래 결과를 만든다.

- `draft`
  - `doc_type`
  - `title`
  - `sections`
  - `compiled_text`
- `checklist_missing_info`
- `evidence_report`
- `warnings`

### 15-1. evidence_report

`EvidenceReport`에는 다음이 들어간다.

- `totals_by_type`
- `used_evidence_ids`
- `unused_evidence_ids`
- `section_coverage`
- `source_mode`
  - `clarify` 또는 `result`

즉 응답만 봐도:

- 실제로 어떤 근거 유형을 몇 개 모았는지
- 어떤 section이 어떤 evidence를 사용했는지
- retrieval이 clarify 상태였는지 result 상태였는지

를 확인할 수 있다.

## 16. Streaming 경로

`DocumentGenerationService.stream()`은 문서 생성 과정을 event stream으로 흘린다.

event 순서는 다음과 같다.

1. `start`
2. `evidence`
3. `plan`
4. `section` x N
5. `evaluation`
6. `complete`
7. 또는 `error`

외부 노출 경로는 [`main.py`](./main.py)에 2개 있다.

- `POST /services/documents/generate/stream`
  - SSE
- `WS /services/documents/generate/ws`
  - WebSocket

이 경로는 LLM timeout, parse mismatch, evidence 부족 같은 문제를 단계별로 추적할 때 가장 유용하다.

## 17. `/api/cases`는 어떻게 이 엔진을 감싸는가

프론트는 보통 `/services/documents/generate`를 직접 치지 않고 `/api/cases`를 호출한다. 이 경로는 [`case_management/service.py`](./case_management/service.py) 의 `CaseWorkflowService.create_case()`에서 처리한다.

### 17-1. 병렬 문서 생성

`_generate_initial_document_artifacts()`는 `asyncio.gather()`로 4개 문서를 병렬 생성한다.

- `fact_finding_report`
  - `doc_type = fact_summary`
  - `prompt_profile = fact_finding_report`
- `attendance_notice`
  - `doc_type = fact_summary`
  - `prompt_profile = attendance_notice`
- `committee_reference`
  - `doc_type = disciplinary_opinion`
  - `prompt_profile = committee_reference`
- `disciplinary_resolution`
  - `doc_type = disciplinary_opinion`
  - `prompt_profile = disciplinary_resolution`

즉 `/api/cases`는 "한 사건 -> 한 문서"가 아니라 "한 사건 -> 문서 패키지 병렬 생성" 구조다.

### 17-2. 문서별 보조 instruction 주입

`_build_pipeline_request()`는 기본 `DocumentGenerationRequest`에 추가 정보를 덧붙인다.

- `첨부자료 요약`
- prompt profile별 extra instruction
- 징계의결서인 경우:
  - `최종 의결결론: 자료상 명확하지 않음`
  - `인정 사실: ...`
  - `의결일자: 자료상 명확하지 않음`
  - `징계위원회명: 자료상 명확하지 않음`
  - `위원장 및 위원 표시: 자료상 명확하지 않음`

이런 보조 line은:

- `request.user_text`
- `structured_case.narrative`
- `constraints.extra_instructions`

에 함께 반영된다.

즉 `/api/cases` 경로는 단순히 동일 엔진을 호출하는 수준이 아니라, 프론트 문서 타입별 prompt profile과 narrative suffix를 주입한 뒤 호출한다.

### 17-3. 생성 실패 시 처리

문서별 생성 결과는 `responses`와 `failures`로 나뉘어 저장된다.

- 성공
  - generated content를 렌더링
- 실패
  - 해당 문서는 입력 보존형 fallback template를 사용

`_build_legal_review_summary()`는 성공한 문서의 evidence count, warning count, missing info를 요약하고, 실패 문서가 있으면 템플릿 fallback 사용 사실까지 적는다.

### 17-4. 프론트용 content 렌더링

문서 생성 엔진이 반환하는 것은 `sections`다. 프론트 상세 페이지에서 보는 최종 `content` 문자열은 `CaseWorkflowService._render_generated_document_content()`에서 만들어진다.

이 단계에서:

- 제목 line 추가
- 누락정보 섹션 추가
- section 번호 부여
- 일부 profile 전용 formatting

이 붙는다.

즉 frontend document content는 "LLM이 그대로 쓴 원문"이 아니라:

- LLM/heuristic이 만든 `section.text`
- backend가 붙인 numbering/title/checklist

가 합쳐진 결과다.

## 18. 어떤 경우에 사용자는 LLM 생성이 아니라 heuristic을 보게 되는가

현재 `auto` 모드에서는 다음 경우 heuristic으로 내려간다.

- `GEMINI_API_KEY` 미설정
- Gemini HTTP 오류
- rate limit
- malformed JSON response
- schema mismatch

Gemini가 실패해도 `auto` 모드에서는 문서 생성 전체가 실패하지 않고 warning log 후 heuristic section generator가 대신 동작한다.

반대로 `generation_provider="gemini"`로 강제하면 Gemini 실패 시 예외가 바로 올라간다.

## 19. 실제 디버깅 포인트

문제가 생겼을 때 가장 먼저 볼 지점은 다음이다.

### 19-1. 관련 조항이 이상할 때

- `/services/related-articles/find`
- 확인할 것
  - `type`
  - `structured_case.missing_slots`
  - `route.labels`
  - `debug.retrieval.query_terms`
  - `debug.evaluation.filtered_out`

### 19-2. 문서가 형식은 맞는데 근거가 빈약할 때

- `/services/documents/generate/stream`
- 확인할 것
  - `evidence.totals_by_type`
  - `plan.additional_retrieval_keywords`
  - `evaluation.warnings`
  - `complete.response.evidence_report.section_coverage`

### 19-3. 프론트에서 보는 문서 content가 이상할 때

- `case_management/service.py`
  - `_render_generated_document_content()`
  - `_build_document_templates()`

엔진 output이 정상이어도 frontend용 numbered content로 렌더링하는 단계에서 보이는 형식이 달라질 수 있다.

## 20. 현재 한계

현재 파이프라인은 grounded generation 구조를 갖고 있지만, 아직 다음 한계가 있다.

- text search는 BM25가 아니라 token overlap
- vector search는 실제 embedding이 아니라 token cosine
- graph ontology가 깊지 않다.
- `CASE_LIBRARY`, `REGULATION_LIBRARY`, `FORM_LIBRARY` 같은 hardcoded supplement가 남아 있다.
- Gemini가 `used_evidence_ids`를 직접 반환하지 않으므로 citation grounding은 backend heuristic에 의존한다.
- clarify 결과가 case workflow의 persisted question record로 완전히 자동 연결되지는 않는다.
- evaluator 경고 이후 자동 재생성 loop는 없다.

즉 현재 구조는 "RAG + sectioned generation + evaluator"까지는 갖췄지만, "강한 citation-grounded regeneration loop"까지는 아직 도달하지 않았다.

## 21. 요약

현재 `backend`의 문서 생성 파이프라인은 다음 문장으로 요약할 수 있다.

1. 사건 payload를 narrative + structured seed로 바꾼다.
2. 같은 프로세스의 관련 조항 찾기 파이프라인을 호출해 법령 후보를 만든다.
3. case/regulation/form demo evidence를 보강해 `EvidencePack`을 만든다.
4. prompt profile 또는 doc_type 기준으로 section plan을 만든다.
5. planner keyword로 추가 retrieval을 한 번 더 돌린다.
6. Gemini 또는 heuristic으로 section text를 생성한다.
7. Gemini가 성공해도 heuristic citation/open_issues는 유지한다.
8. evaluator가 schema, citation, 날짜, 용어를 검사한다.
9. `/api/cases` 경로에서는 이 결과를 4종 문서 패키지와 workflow stage로 감싸 프론트에 넘긴다.

이 문서를 읽고 나면 다음 질문에 답할 수 있어야 한다.

- 왜 문서 생성이 retrieval 없이 동작하지 않는가
- 왜 Gemini가 성공해도 citation은 backend가 들고 있는가
- 왜 `/api/cases`와 `/services/documents/generate` 결과가 문서 종류 면에서 다를 수 있는가
- 왜 문서 본문에 `자료상 명확하지 않음`과 `누락정보`가 같이 붙는가
