# LawFlow Backend

프론트엔드 데모를 우선 지원하는 FastAPI 백엔드다. 외부에는 사건 중심 API를 제공하고, 내부에서는 `관련 조항 찾기 파이프라인`과 `법률 문서 생성 파이프라인`이 순차적으로 동작하도록 설계한다.

## 설계 원칙

- 외부 계약은 프론트 기준으로 고정한다.
  - 대시보드, 사건 상세, 문서 상세, 워크플로우 화면이 필요로 하는 `/api/cases*`, `/api/questions*`, `/api/legal-basis` 응답 shape를 우선한다.
- 내부 구현은 파이프라인 기준으로 분리한다.
  - 사건 관리 API와 검색/생성 엔진을 같은 레이어로 섞지 않고, 프론트용 오케스트레이션과 도메인 파이프라인을 구분한다.
- 문서 생성은 반드시 근거 기반으로 동작한다.
  - 문서 생성은 독립적인 text generation이 아니라 관련 조항 검색 결과를 재사용하는 grounded generation이어야 한다.
- 1차 범위는 `disciplinary` 사건이다.
  - 프론트 연동용 `/api/cases` 계열은 현재 징계 사건만 생성 가능하다.
- 현재 저장소는 데모/프로토타입 모드다.
  - 저장소와 검색 인덱스는 기본적으로 in-memory이고, 서버 기동 시 `mock_data`와 `case_management/seed`를 다시 적재한다.

## 아키텍처 개요

```text
Frontend Screens
  Dashboard / Case Create / Case Detail / Document Detail / Workflow
    |
    v
Frontend-first API Layer
  /api/cases*
  /api/questions*
  /api/legal-basis
    |
    v
CaseWorkflowService
  - 프론트 화면이 바로 쓰는 사건/문서/질문/타임라인/워크플로우 조립
  - 내부 파이프라인 상태를 프론트용 stage/status로 요약
    |
    +--> Related Article Pipeline
    |     [1] 사실관계 구조화
    |     [2] 법체계 라우팅
    |     [3] Graph RAG + 보조 검색
    |     [4] Retrieval Evaluator
    |
    +--> Document Generation Pipeline
          [1] 근거 수집
          [2] 문단/조항 계획
          [3] 섹션별 생성
          [4] Draft Evaluator
          [5] 안전장치

Infrastructure Layer
  ingestion / graph / storage / eval / schemas
```

핵심은 다음 두 가지다.

- 프론트는 사건 중심으로 본다.
  - 사건 생성, 문서 목록, 추가 질문, 검토 이력, 워크플로우 단계가 먼저 보인다.
- 백엔드는 파이프라인 중심으로 일한다.
  - 관련 조항 검색과 문서 생성을 별도 엔진으로 유지하되, 그 결과를 `CaseDetail.workflowStages`, `documents`, `questions`, `timeline`으로 요약해 프론트에 전달한다.

## 상세 파이프라인 문서

README에는 구조와 책임 분리를 요약하고, 실제 RAG/LLM 실행 순서는 별도 문서로 분리했다.

- [`RAG_AND_DOCUMENT_PIPELINE.md`](./RAG_AND_DOCUMENT_PIPELINE.md)
  - 단계별로 "왜 이 단계가 필요한지"를 설명하는 추상화 문서
  - RAG 파이프라인과 문서 생성 파이프라인의 역할 분리
  - 전체 흐름, RAG 전용 흐름, 문서 생성 전용 흐름을 mermaid 그래프로 시각화
  - grounded generation, 질문 루프, evaluator, fallback의 필요성 설명
  - 마지막 절에서만 현재 코드 모듈과 개념 단계를 매핑

문서 생성이 왜 retrieval 이후에 와야 하는지, 왜 planner와 evaluator가 따로 필요한지, 왜 본문과 내부 진단 정보를 분리해야 하는지 설명할 때는 위 문서를 먼저 보는 편이 빠르다.

## 프론트 우선 API 설계

| 프론트 화면 | 주요 엔드포인트 | 백엔드 역할 |
| --- | --- | --- |
| 대시보드 `/` | `GET /api/cases`, `GET /api/cases/metrics` | 사건 목록, 진행률, 질문/검토 집계를 제공 |
| 사건 생성 `/cases/new` | `POST /api/cases` | 프론트 입력을 사건/문서 패키지 초기 상태로 변환 |
| 사건 상세 `/cases/:caseId` | `GET /api/cases/{case_id}` | 사건 요약, 문서 목록, 질문, 타임라인, workflow stage를 조립 |
| 문서 상세 `/cases/:caseId/documents/:documentId` | `GET /api/cases/{case_id}/documents/{document_id}` | 문서 본문, 법적 근거, 버전/리뷰 이력을 제공 |
| 질문 응답 | `GET /api/cases/{case_id}/questions*`, `POST /api/questions/{question_id}/answer` | 누락 정보 보완과 문서 상태 재동기화 |
| 검토/피드백 | `POST /api/cases/{case_id}/documents/{document_id}/reviews*` | 리뷰 등록, 반영, 상태/타임라인 업데이트 |
| 워크플로우 `/workflow/:caseId` | `GET /api/cases/{case_id}` | 내부 파이프라인 상태를 5단계 워크플로우로 시각화 가능하게 제공 |

`/services/related-articles/*` 와 `/services/documents/*` 는 프론트 화면에서 직접 쓰는 1차 API라기보다, 사건 워크플로우 뒤에서 돌아가는 엔진을 독립적으로 호출/검증할 수 있게 둔 내부 서비스 API다.

## 내부 파이프라인 설계

### 1. 관련 조항 찾기 서비스

목표 파이프라인:

```text
사용자 입력
  -> [1] 사실관계 구조화
  -> [2] 법체계 라우팅
  -> [3] Graph RAG + 보조 검색
  -> [4] Retrieval Evaluator
  -> 관련 조항 최종 결과
```

모듈 매핑:

- `[1] 사실관계 구조화`
  - `search/structuring.py`
  - 자연어 입력을 `StructuredCase` 로 변환하고 누락 슬롯을 탐지한다.
- `[2] 법체계 라우팅`
  - `search/routing.py`
  - 민사/형사/행정/징계/군 특수 영역을 soft prior로 추정한다.
- `[3] Graph RAG + 보조 검색`
  - `search/retrieval.py`
  - text search, pseudo-vector search, graph expansion을 합치고 RRF로 fusion한다.
- `[4] Retrieval Evaluator`
  - `search/evaluation.py`
  - 관할, 시행시점, 최소 인용 단위, 폐지 여부를 필터링하고 최종 후보를 rerank한다.
- 서비스 진입점
  - `search/pipeline.py`
  - `RelatedArticleFinderService`

설계 포인트:

- 구조화와 검색을 분리해, 사용자 자연어를 그대로 검색하지 않는다.
- 라우팅은 hard filter가 아니라 검색 우선순위 힌트다.
- graph는 단독 검색기가 아니라 hybrid retrieval 채널 중 하나다.
- evaluator는 "찾은 것" 중 실제로 써도 되는 근거만 남기는 단계다.

### 2. 법률 문서 생성 서비스

목표 파이프라인:

```text
사용자 입력
  -> [1] 근거 수집
  -> [2] 문단 / 조항 계획
  -> [3] 섹션별 생성기
  -> [4] Draft Evaluator / 적법성·정합성 검사
  -> [5] 안전장치
  -> 최종 문서 초안
```

모듈 매핑:

- `[1] 근거 수집`
  - `documents/evidence.py`
  - 내부적으로 관련 조항 찾기 서비스를 재사용해 `EvidencePack` 을 만든다.
- `[2] 문단 / 조항 계획`
  - `documents/planning.py`
  - 문서 종류별 section plan과 추가 retrieval keyword를 구성한다.
- `[3] 섹션별 생성기`
  - `documents/generator.py`, `documents/gemini.py`
  - heuristic 또는 Gemini를 사용해 section 단위로 생성한다.
- `[4] Draft Evaluator`
  - `documents/evaluation.py`
  - 필수 섹션 누락, 근거 인용 누락, 날짜 불일치, 금지 표현 등을 검사한다.
- `[5] 안전장치`
  - `documents/service.py`
  - warning, stream event, fallback, error event를 조립해 최종 응답을 만든다.
- 서비스 진입점
  - `documents/service.py`
  - `DocumentGenerationService`

설계 포인트:

- 문서 생성은 항상 retrieval 결과를 선행 근거로 사용한다.
- plan 없이 장문을 한 번에 만들지 않는다.
- evaluator는 문장 자연스러움보다 형식 완전성, 근거 정합성, 내부 일관성을 먼저 본다.
- Gemini가 없으면 heuristic fallback으로 동작한다.

## 프론트 워크플로우와 내부 파이프라인의 연결

프론트의 5단계 워크플로우는 내부적으로 다음 의미를 가진다.

1. `case_registration`
   - 사건 메타데이터와 사실관계를 수집한다.
   - 내부 `StructuredCase` 후보와 문서 생성 입력의 원천이 된다.
2. `attachment_registration`
   - 첨부 근거를 연결한다.
   - retrieval 보조 자료와 evidence pack seed를 확보한다.
3. `information_request`
   - 구조화 단계 누락 슬롯 또는 evaluator 결과를 질문으로 만든다.
   - 사용자 답변이 들어오면 문서 상태와 타임라인을 갱신한다.
4. `document_generation`
   - 관련 조항 파이프라인과 문서 생성 파이프라인이 실제로 실행되는 단계다.
   - 문서 상태(`pending`, `generating`, `needs_input`, `completed`)는 이 단계의 세부 진행도를 나타낸다.
5. `review_feedback`
   - Draft evaluator 결과와 사용자 피드백을 반영한다.
   - 문서 버전 이력과 review history를 남긴다.

즉, 프론트는 5단계만 알면 되지만, 백엔드는 그 안에서 검색/생성/검수 파이프라인을 더 세밀하게 수행한다.

## 디렉터리 책임

```text
backend/
  main.py                    FastAPI entrypoint, DI container, endpoint wiring
  case_management/           프론트용 사건 워크플로우 조립과 seed 상태 관리
  documents/                 법률 문서 생성 파이프라인
  search/                    관련 조항 검색 파이프라인
  ingestion/                 국가법령정보/모의 데이터 적재
  graph/                     graph store abstraction + in-memory 구현
  storage/                   corpus repository / vector store / observability
  schemas/                   API 및 도메인 스키마
  eval/                      retrieval / generation / safety 평가 러너
  tests/                     API 계약 및 파이프라인 테스트
```

권장 책임 분리:

- `case_management`
  - 프론트 응답 조립 전용
  - 화면 계약을 안정적으로 유지
- `search`
  - 관련 조항 검색 전용
  - `StructuredCase -> RelatedArticleCandidate[]`
- `documents`
  - 문서 초안 생성 전용
  - `DocumentGenerationRequest -> DocumentGenerationResponse`
- `ingestion`, `graph`, `storage`
  - corpus/infra 계층

## 실행

```bash
cd /home/desktopuser/Desktop/code/lawer_service/backend
cp .env.example .env
uv sync --python 3.13
uv run uvicorn main:app --reload
```

루트에서 바로 실행:

```bash
cd /home/desktopuser/Desktop/code/lawer_service
./scripts/dev.sh
```

기본 서버 주소:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

환경 변수:

- `LAW_API_OC`
  - 국가법령정보 OPEN API 실제 수집에 필요
- `GEMINI_API_KEY`
  - Gemini 기반 문서 생성 사용 시 필요
- `GEMINI_MODEL_NAME`
  - 기본값 `gemini-2.5-flash`

## 주요 엔드포인트

### 프론트 연동 API

```http
GET  /api/cases
GET  /api/cases/metrics
GET  /api/cases/{case_id}
POST /api/cases
GET  /api/cases/{case_id}/documents
GET  /api/cases/{case_id}/documents/{document_id}
POST /api/cases/{case_id}/documents/{document_id}/reviews
POST /api/cases/{case_id}/documents/{document_id}/reviews/{review_id}/resolve
GET  /api/cases/{case_id}/questions
GET  /api/cases/{case_id}/questions/open
POST /api/questions/{question_id}/answer
GET  /api/legal-basis?ids=lb-003&ids=lb-005
```

### 검색/생성 엔진 API

```http
POST /services/related-articles/find
POST /services/documents/generate
POST /services/documents/generate/stream
WS   /services/documents/generate/ws
```

### 코퍼스/디버그 API

```http
GET  /health
GET  /ingestions/mock-data/status
POST /ingestions/mock-data/load
POST /ingestions/laws
GET  /laws/{official_law_id}
GET  /laws/{official_law_id}/versions/as-of?date=2024-03-01
GET  /search/text?q=사전통지&limit=10
GET  /graph/units/{unit_id}/neighbors
```

## 현재 동작 특성

- `/api/cases*` 는 프론트가 기대하는 shape를 우선 유지한다.
- 새 사건 생성은 현재 `disciplinary` 만 허용한다.
- 문서 상세의 `legalBasis` 는 `case_management/seed/legal-basis.json` 카탈로그를 기준으로 채워진다.
- `/services/related-articles/find` 는 필요 시 `type: "clarify"` 응답을 반환한다.
- `/services/documents/generate` 는 프론트 사건 payload를 받아 내부 `DocumentGenerationRequest` 로 변환한다.
- 저장소는 기본 in-memory 이므로 서버 재시작 시 동적 변경 사항은 초기화된다.

## 테스트

```bash
cd /home/desktopuser/Desktop/code/lawer_service/backend
uv run pytest
```

계약 변경 시 우선 확인할 테스트:

- `tests/test_frontend_case_management_api.py`
- `tests/test_related_article_service.py`
- `tests/test_document_generation_service.py`

## 한계와 다음 단계

- `/api/cases` 계열은 아직 징계 사건 중심이다.
- vector search는 실제 embedding 기반이 아니라 단순화된 데모 구현이다.
- graph ontology는 더 깊게 확장할 수 있지만, 현재는 in-memory abstraction 단계다.
- case workflow와 검색/생성 파이프라인은 아직 완전한 run-level persistence를 가지지 않는다.
- 장기적으로는 다음 순서가 적절하다.
  1. ontology와 retrieval evaluator를 강화한다.
  2. query normalization과 clarification memory를 고도화한다.
  3. section별 evidence grounding을 더 엄격히 검증한다.
  4. 이후 외부 GraphDB나 실제 search engine 도입을 검토한다.
