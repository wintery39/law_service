# Law Corpus Backend

법령 코퍼스 공통 기반과 법률 RAG API를 제공하는 FastAPI 백엔드입니다.

- 캐노니컬 스키마: `Law`, `Unit`, `Version`, `Reference`, `SourceMeta`
- 수집기: 국가법령정보 공동활용 OPEN API 연동용 클라이언트 및 변환기
- 저장소 추상화: `GraphStore`, `TextSearchStore`, `VectorStore`, `CorpusRepository`
- 기본 구현: 모두 in-memory 구현 포함
- API: 조회, 수집, 검색, 그래프, 관련 조항 탐색, 문서 생성, 평가

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
- 실제 OPEN API 수집에는 `LAW_API_OC` 값이 필요합니다.
- `/services/related-articles/find`는 경우에 따라 바로 결과를 주지 않고 `clarify` 응답을 반환합니다.
- 문서 생성 스트림은 정상 이벤트 외에 `error` 이벤트를 보낼 수 있습니다.

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

### 1. Health

```http
GET /health
```

서버 상태와 현재 in-memory 엔티티 수를 반환합니다.

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
    "user_text": "행정청이 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
    "as_of_date": "2024-03-01",
    "jurisdiction": "kr"
  }'
```

### Generate Document

```bash
curl -X POST http://127.0.0.1:8000/services/documents/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "창고 자산 반출 의혹 조사",
    "caseType": "disciplinary",
    "occurredAt": "2026-03-19T09:00:00Z",
    "location": "제3보급대대 창고동",
    "author": "대위 홍길동",
    "relatedPersons": ["병장 최민수", "중사 이영호"],
    "summary": "정식 승인 없이 장비 상자가 외부 적재 구역으로 이동한 정황이 확인되었습니다.",
    "details": "창고 출입기록과 CCTV 확인 결과, 장비 상자 2개가 정식 반출 절차 없이 이동한 정황이 포착되었습니다. 관련자 진술과 재물 관리대장 사이에 차이가 있어 추가 확인이 진행 중입니다."
  }'
```

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
