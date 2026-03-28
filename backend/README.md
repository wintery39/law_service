# Law Corpus Backend

법령 코퍼스 공통 기반과 법률 RAG API를 제공하는 FastAPI 백엔드입니다.

- 캐노니컬 스키마: `Law`, `Unit`, `Version`, `Reference`, `SourceMeta`
- 수집기: 국가법령정보 공동활용 OPEN API 연동용 클라이언트 및 변환기
- 저장소 추상화: `GraphStore`, `TextSearchStore`, `VectorStore`, `CorpusRepository`
- 기본 구현: 모두 in-memory 구현 포함
- API: 조회, 수집, 검색, 그래프, 관련 조항 탐색, 문서 생성, 평가
- 데모 코퍼스: `mock_data/*.json`을 canonical corpus로 자동 적재
- 사건 워크플로우 API: `backend/case_management/seed/*.json` 기반의 frontend-compatible case workflow 제공

## What The API Can Do

이 서버는 다음 작업을 처리합니다.

- 법령 수집: 국가법령정보 OPEN API에서 법령 본문과 연혁 메타를 가져와 내부 코퍼스로 적재
- 법령 조회: 특정 법령의 버전 목록과 기준일 기준 유효 버전 조회
- 텍스트 검색: 조문 본문에 대한 BM25 스타일 검색
- 그래프 탐색: 조문 간 연결 관계 확인
- 관련 조항 찾기: 사용자 서술을 구조화하고 관련 조항 후보를 반환
- 문서 생성: 사실관계 정리서, 징계 의견서, 항변서 초안 생성
- 문서 스트리밍: 생성 진행을 SSE 또는 WebSocket 이벤트로 수신
- 평가: retrieval / generation / safety 실험 실행

## Runtime Notes

- 저장소는 기본적으로 in-memory 입니다. 서버를 재시작하면 적재한 코퍼스가 사라집니다.
- 단, 서버 시작 시 `mock_data/*.json`은 다시 자동 적재됩니다.
- 실제 OPEN API 수집에는 `LAW_API_OC` 값이 필요합니다.
- `/services/related-articles/find`는 경우에 따라 바로 결과를 주지 않고 `clarify` 응답을 반환합니다.
- 문서 생성 스트림은 정상 이벤트 외에 `error` 이벤트를 보낼 수 있습니다.
- `/api/cases*` 계열은 현재 `disciplinary` 사건 유형만 1차 지원합니다.
- 사건 생성 API는 `caseType != "disciplinary"` 입력에 대해 `422`를 반환합니다.
- 문서 상세의 `legalBasis`와 `legalBasisIds`는 `backend/mock_data/military_discipline_rule_demo.json` 기준으로 채워집니다.

## Case Workflow Scope

- 현재 `/api/cases`, `/api/cases/{case_id}`, `/api/cases/{case_id}/documents`, `/api/questions/{question_id}/answer` 는 frontend 연동을 위한 사건 워크플로우 API입니다.
- 이 데이터는 더 이상 `frontend/src/mocks`를 읽지 않고, `backend/case_management/seed/*.json`에서 bootstrap 됩니다.
- 1차 범위는 `disciplinary` 전용입니다.
- 문서 패키지 이름과 응답 shape는 기존 프론트 mock 계약을 최대한 유지하도록 맞춰져 있습니다.

## 실행

```bash
cp .env.example .env
uv sync --python 3.13
uv run uvicorn main:app --reload
```

`.env`에서 `LAW_API_OC`를 읽습니다. 실제 국가법령정보 OPEN API를 호출하려면 값을 채우세요.

루트에서 바로 실행하려면:

```bash
cd /home/desktopuser/Desktop/code/lawer_service
./scripts/dev.sh
```

## Key Endpoints

### 0. Mock Data Bootstrap

```http
GET /ingestions/mock-data/status
POST /ingestions/mock-data/load
```

- `backend/mock_data/*.json` 파일을 canonical law/unit/reference corpus로 적재합니다.
- 서버 시작 시 자동 실행됩니다.
- JSON을 수정한 뒤 재시작 없이 다시 반영하려면 `POST /ingestions/mock-data/load`를 호출하면 됩니다.

### 1. Health

```http
GET /health
```

서버 상태와 현재 in-memory 엔티티 수를 반환합니다.
추가로 현재 자동 적재된 `mock_data` 요약도 함께 반환합니다.

### 1-1. Case Workflow

```http
GET /api/cases
GET /api/cases/metrics
GET /api/cases/{case_id}
POST /api/cases
GET /api/cases/{case_id}/documents
GET /api/cases/{case_id}/documents/{document_id}
GET /api/cases/{case_id}/questions
GET /api/cases/{case_id}/questions/open
POST /api/questions/{question_id}/answer
GET /api/legal-basis?ids=mdr-art-006&ids=mdr-form-001
```

- 사건/문서/질문 응답은 현재 프론트가 기대하는 shape를 최대한 유지합니다.
- 새 사건 생성은 `disciplinary`만 허용합니다.
- 질문 답변 제출 후 관련 문서 상태, 버전 이력, 사건 진행 상태가 함께 갱신됩니다.
- `legalBasis`는 `mock_data` 기반 카탈로그를 통해 구성됩니다.

### 2. Ingest Law

```http
POST /ingestions/laws
```

예시:

```json
{
  "law_id": "100004"
}
```

`law_id` 또는 `mst` 또는 `query`를 사용할 수 있습니다.

### 3. Get Law And Versions

```http
GET /laws/{official_law_id}
GET /laws/{official_law_id}/versions/as-of?date=2024-03-01
```

### 4. Text Search

```http
GET /search/text?q=사전통지&limit=10
```

### 5. Graph Neighbors

```http
GET /graph/units/{unit_id}/neighbors
```

### 6. Find Related Articles

```http
POST /services/related-articles/find
```

예시:

```json
{
  "session_id": "sess-1",
  "user_text": "행정청이 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
  "as_of_date": "2024-03-01",
  "jurisdiction": "kr",
  "user_profile": {
    "role": "민원인"
  }
}
```

응답 유형:

- `type: "clarify"`: 누락 슬롯과 추가 질문 반환
- `type: "result"`: 구조화된 사건, 라우팅, 후보 조문, 최종 조문 반환

### 7. Generate Document

```http
POST /services/documents/generate
```

예시:

```json
{
  "title": "창고 자산 반출 의혹 조사",
  "caseType": "disciplinary",
  "occurredAt": "2026-03-19T09:00:00Z",
  "location": "제3보급대대 창고동",
  "author": "대위 홍길동",
  "relatedPersons": ["병장 최민수", "중사 이영호"],
  "summary": "정식 승인 없이 장비 상자가 외부 적재 구역으로 이동한 정황이 확인되었습니다.",
  "details": "창고 출입기록과 CCTV 확인 결과, 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다. 관련자 진술과 재물 관리대장 사이에 차이가 있어 추가 확인이 진행 중입니다."
}
```

입력 키는 다음 8개만 받습니다.

- `title`
- `caseType`
- `occurredAt`
- `location`
- `author`
- `relatedPersons`
- `summary`
- `details`

서버는 이 입력만으로 내부 `structured_case`와 문서 타입을 자동 파생합니다.

### 8. Stream Document Generation

```http
POST /services/documents/generate/stream
WS /services/documents/generate/ws
```

SSE 이벤트 타입:

- `start`
- `evidence`
- `plan`
- `section`
- `evaluation`
- `complete`
- `error`

## Example Flow With curl

### Check Mock Data Bootstrap

```bash
curl http://127.0.0.1:8000/ingestions/mock-data/status
```

### Reload Mock Data

```bash
curl -X POST http://127.0.0.1:8000/ingestions/mock-data/load
```

### List Seeded Case Workflow Items

```bash
curl http://127.0.0.1:8000/api/cases
curl http://127.0.0.1:8000/api/cases/metrics
curl http://127.0.0.1:8000/api/cases/case-005
```

`case-005`는 open question이 포함된 `disciplinary` 예시 사건입니다.

### Answer A Workflow Question

```bash
curl -X POST http://127.0.0.1:8000/api/questions/question-005-001/answer \
  -H 'Content-Type: application/json' \
  -d '{
    "answer": "재발 방지 교육은 2026년 3월 21일 전 부서원을 대상으로 실시하고, 외부 장비 연결은 사전 승인 체크리스트를 통과한 경우에만 허용하며, 지휘관은 주간 점검 결과를 직접 확인하기로 했습니다."
  }'
```

이 요청은 관련 문서 본문, 버전 이력, 리뷰 이력, 사건 상태를 함께 갱신합니다.

### Resolve Legal Basis Entries

```bash
curl 'http://127.0.0.1:8000/api/legal-basis?ids=mdr-art-006&ids=mdr-form-001'
```

이 응답은 `backend/mock_data/military_discipline_rule_demo.json` 기반 법적 근거 카탈로그를 반환합니다.

### Ingest

```bash
curl -X POST http://127.0.0.1:8000/ingestions/laws \
  -H 'Content-Type: application/json' \
  -d '{
    "law_id": "100004"
  }'
```

### Find Related Articles

```bash
curl -X POST http://127.0.0.1:8000/services/related-articles/find \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "sess-1",
    "user_text": "병사가 생활관에서 상관의 명령을 거부해 징계가 문제입니다.",
    "as_of_date": "2026-03-01",
    "jurisdiction": "kr"
  }'
```

이 요청은 `backend/mock_data/military_discipline_rule_demo.json`에서 적재된 조문·별표·서식 단위를 대상으로 검색합니다.

### Search Mock Evidence Directly

```bash
curl 'http://127.0.0.1:8000/search/text?q=갑질&limit=5'
```

`search_synonyms`가 unit text에 확장 반영되므로 `갑질`, `부업`, `술먹고 운전` 같은 표현도 검색됩니다.

### Generate Document

```bash
curl -X POST http://127.0.0.1:8000/services/documents/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "생활관 명령 거부 징계 검토",
    "caseType": "disciplinary",
    "occurredAt": "2026-03-20T10:00:00Z",
    "location": "생활관",
    "author": "중위 김수현",
    "relatedPersons": ["병사 김민준", "상관 이도현"],
    "summary": "병사가 상관의 정당한 명령을 거부해 징계 검토가 필요한 사안입니다.",
    "details": "생활관에서 병사가 상관의 정당한 명령을 거부했고 복무질서에 영향을 줄 수 있다는 보고가 접수되었습니다."
  }'
```

문서 생성 시 `/services/related-articles/find`를 먼저 호출해 `mock_data` 코퍼스에서 근거를 회수하고, 그 결과가 `evidence_report`와 초안 생성에 반영됩니다.

## Mock Data Schema Design

`backend/mock_data/*.json`은 다음 계층으로 해석됩니다.

- `articles`
  핵심 조문 단위
- `appendices`
  별표/양정 기준 단위
- `forms`
  실무 서식 단위
- `search_synonyms`
  질의 표현 확장용 동의어 사전
- `document_generation_hints`
  현재는 데이터셋 내부 설명값으로 유지하며, 향후 문서 유형별 retrieval hint로 확장 가능

적재 시 내부적으로 다음으로 변환됩니다.

- `Law`
  하나의 데모 법령
- `Version`
  `effective_date + dataset_version` 기반 버전
- `Unit`
  조문/별표/서식 각각을 검색 가능한 최소 근거 단위로 변환
- `Reference`
  본문과 연관 용어에 등장하는 `제N조`, `별표 N`, `별지 제N호서식`를 내부 참조 그래프로 연결

즉, `mock_data`는 단순 파일 보관이 아니라 실제 RAG corpus 입력층으로 동작합니다.

### Stream Document

```bash
curl -N -X POST http://127.0.0.1:8000/services/documents/generate/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "지휘 명령 거부 사건",
    "caseType": "disciplinary",
    "occurredAt": "2026-03-19T09:00:00Z",
    "location": "생활관",
    "author": "중위 김수현",
    "relatedPersons": ["병장 최민수"],
    "summary": "상관의 정당한 명령을 거부한 정황이 접수되었습니다.",
    "details": "병사가 상관의 정당한 명령을 거부했고 당시 복무 질서에 영향을 줄 수 있는 상황이었다는 보고가 접수되었습니다."
  }'
```

## Evaluation

```bash
uv run python -m eval --gold-cases ./path/to/gold_cases.jsonl
```

품질 게이트 임계치를 같이 줄 수도 있습니다.

```bash
uv run python -m eval \
  --gold-cases ./path/to/gold_cases.jsonl \
  --thresholds '{"retrieval":[{"experiment":"hybrid","min_metrics":{"recall@5":0.5}}]}'
```

## 테스트

```bash
uv run pytest
```
