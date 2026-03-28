# Backend 구현 계획

## 1. 목표

- 프론트엔드의 `mock_data` 의존을 제거하고, 프론트가 `backend`의 실제 API만 호출해도 동작하도록 백엔드를 완성한다.
- 법령 데이터의 원천은 `backend/mock_data/*.json`만 사용한다.
- 외부 법령 수집용 API를 새로 만들거나 확장하는 작업은 이번 범위에 포함하지 않는다.
- 프론트엔드 수정은 나중에 진행하므로, 먼저 백엔드가 자체적으로 데이터 소유권과 상태 전이를 책임지도록 만든다.
- 1차 완성 범위는 `disciplinary` 사건 유형으로 제한한다.
- 프론트의 현재 API 호출 방식과 응답 shape를 최대한 유지한다.
- 프론트 mock에서 사용 중인 문서명과 문서 흐름 구조를 가능한 한 그대로 보존하는 것을 목표로 한다.

## 1-1. 현재 구현 상태

- `CaseWorkflowService`가 `backend/case_management/seed/*.json`을 읽도록 전환되었다.
- `/api/cases` 계열은 더 이상 `frontend/src/mocks`를 읽지 않는다.
- 1차 범위인 `disciplinary` 사건의 목록/상세/문서/질문/답변 루프가 backend seed 기준으로 동작한다.
- 문서 상세의 `legalBasis`와 `legalBasisIds`는 `backend/mock_data/military_discipline_rule_demo.json` 기반 카탈로그로 채워진다.
- `create case`는 현재 `disciplinary`만 허용하며, 다른 사건 유형은 `422`를 반환한다.

## 1-2. 확정된 범위

- 지원 사건 유형: `disciplinary`만 1차 지원
- 우선 보존할 계약
  - `/api/cases`
  - `/api/cases/metrics`
  - `/api/cases/{case_id}`
  - `/api/cases/{case_id}/documents`
  - `/api/cases/{case_id}/documents/{document_id}`
  - `/api/cases/{case_id}/questions`
  - `/api/cases/{case_id}/questions/open`
  - `/api/questions/{question_id}/answer`
- 우선 보존할 문서 패키지 방향
  - 프론트 mock이 기대하는 문서명
  - 프론트 mock이 기대하는 `DocumentRecord` / `DocumentDetail` 구조
  - 프론트 mock이 기대하는 workflow/timeline 흐름

## 2. 현재 상태 요약

### 이미 있는 것

- `backend/main.py`
  - `/api/cases`
  - `/api/cases/metrics`
  - `/api/cases/{case_id}`
  - `/api/cases/{case_id}/documents`
  - `/api/cases/{case_id}/documents/{document_id}`
  - `/api/cases/{case_id}/questions`
  - `/api/cases/{case_id}/questions/open`
  - `/api/questions/{question_id}/answer`
- `backend/ingestion/mock_data.py`
  - `backend/mock_data/*.json`을 canonical corpus로 적재하는 기능
- `backend/search/*`
  - 관련 조항 탐색
  - 텍스트 검색
  - 그래프 기반 확장
- `backend/documents/*`
  - 단일 문서 생성
  - evidence 수집
  - streaming

### 기존 핵심 문제와 현재 상태

- 기존에는 `backend/case_management/service.py`의 `FrontendCaseManagementService`가 `frontend/src/mocks/*.json`을 직접 읽고 있었다.
- 현재는 `CaseWorkflowService`가 `backend/case_management/seed/*.json`을 읽도록 변경되어, `/api/cases` 계열 API의 프론트 폴더 의존은 제거되었다.

### 추가로 확인된 구조적 갭

- 현재 문서 생성 엔진은 `fact_summary`, `disciplinary_opinion`, `defense_draft` 중심의 "단일 결과 문서" 생성기다.
- 반면 프론트 계약은 사건 하나에 대해 여러 문서가 순차적으로 생기는 "문서 패키지/워크플로우"를 전제로 한다.
- `backend/documents/evidence.py`는 `CASE_LIBRARY`, `REGULATION_LIBRARY`, `FORM_LIBRARY` 같은 하드코딩된 보조 근거를 사용한다.
- 사용자가 원하는 방향은 "법령은 `backend/mock_data`의 JSON만 제공"이므로, 하드코딩 근거와 JSON 기반 근거의 역할을 정리해야 한다.
- 현재 `backend/mock_data`에는 `military_discipline_rule_demo.json` 1개만 있다.
- 그런데 현재 프론트 mock 사건은 `criminal`, `disciplinary`, `other` 전체를 포함하고, 법적 근거도 `군형법`, `군사법원법`, `국방 정보보호 업무훈령` 등 여러 법령을 가정한다.
- 즉, 현재 mock_data만으로는 지금 프론트 mock 전체를 동일하게 재현할 수 없다.
- 다만 현재 사용자가 1차 완성 범위를 `disciplinary`로 줄였으므로, `military_discipline_rule_demo.json` 중심으로 먼저 완성하는 것이 합리적이다.

## 3. 이번 작업의 핵심 원칙

- 백엔드가 자신의 seed/state를 소유해야 한다.
- 프론트 폴더를 읽지 않는 상태에서 서버가 단독으로 기동 가능해야 한다.
- 법령 근거는 `backend/mock_data/*.json`에서 적재된 corpus를 기준으로 만든다.
- 초기 단계에서는 DB보다 backend 내부 in-memory + seed/bootstrap 구조가 더 현실적이다.
- 문서 생성과 질문 생성은 우선 deterministic/rule-based로 구현하고, LLM 의존은 나중으로 미룬다.
- 프론트가 나중에 붙더라도 API 응답 shape는 최대한 지금 프론트 타입과 맞춘다.
- `disciplinary` 흐름에서 먼저 완결성을 확보하고, 이후 다른 사건 유형은 별도 확장 작업으로 본다.
- 문서 taxonomy는 backend 편의보다 현재 프론트 mock 계약 보존을 우선한다.

## 4. 반드시 구현해야 할 항목

### A. 백엔드가 사건/문서/질문 데이터를 직접 소유하도록 구조 변경

#### 해야 하는 이유

- 기존 구조에서는 `backend`가 `frontend/src/mocks/*.json` 없이는 제대로 동작하지 않았다.
- 프론트 변경 시 백엔드도 함께 깨질 가능성이 높다.

#### 구현 항목

- `CaseWorkflowService` 중심 구조로 정리
- `backend/case_management/seed/`를 실제 seed source로 사용
- 아래 seed 데이터를 backend 기준으로 이동
  - cases
  - case details
  - documents
  - questions
- seed loading 로직을 `frontend/src/mocks`가 아니라 `backend/case_management/seed/*.json` 또는 backend 내부 bootstrap 코드로 옮기기
- case/document/question 저장 구조를 명시적으로 분리
- 추후 DB 교체가 가능하도록 repository 계층 또는 store 추상화 추가

#### 권장 산출물

- `CaseRepository` 또는 이에 준하는 저장 추상화
- `InMemoryCaseStore`
- `seed_loader.py` 또는 `bootstrap.py`
- `CaseWorkflowService` 같은 backend 중심 이름의 서비스

### B. 사건 생성 API와 문서 생성 엔진 사이의 실제 연결 계층 만들기

#### 현재 문제

- `/api/cases` 생성은 단순 템플릿 문자열로 문서를 만든다.
- `/services/documents/generate`는 별도 엔진으로 동작하며, case workflow와 직접 연결되지 않는다.
- 즉, "사건 생성 -> 필요한 문서 패키지 생성 -> 법적 근거 연결 -> 추가 질문 생성" 흐름이 아직 하나의 backend orchestration으로 묶여 있지 않다.

#### 구현 항목

- 사건 생성 시 실행되는 오케스트레이터 추가
- 역할
  - 사건 기본 정보 저장
  - case type에 맞는 초기 문서 패키지 계획 수립
  - 각 문서의 상태 초기화
  - 필요 시 즉시 생성 가능한 문서부터 생성
  - 부족 정보가 있으면 질문 생성
  - timeline/workflow stage 반영
- 현재 `CaseCreatePayload`의 필드와 문서 생성 엔진 입력 사이의 gap 해소
  - 현재 문서 생성 요청은 `priority`, `attachmentProvided`, `attachmentSummary`를 사용하지 않음
  - 이 값들을 내부 generation context에 반영할지 결정 필요

#### 권장 방향

- `CaseCreationOrchestrator`
- `DocumentPackagePlanner`
- `QuestionPlanner`
- `TimelineBuilder`

### C. "문서 패키지" 개념을 backend에 명시적으로 도입

#### 현재 문제

- 문서 생성 엔진은 단일 결과 문서 중심
- 프론트는 사건당 여러 문서가 순차적으로 존재하는 UI/UX를 기대

#### 구현 항목

- case type별 문서 패키지 정의
  - `disciplinary`
- 각 패키지에 대해 아래를 정의
  - 문서 종류
  - 순서
  - 초기 상태
  - 생성 조건
  - 필요한 추가 정보
  - 추천 법적 근거 종류
- 문서별 생성 전략 정의
  - 즉시 생성 가능한 문서
  - 추가 질문이 있어야 생성 가능한 문서
  - 앞 문서가 완료돼야 생성되는 후속 문서

#### 이번 단계의 확정 방향

- `disciplinary` 문서 패키지는 현재 프론트 mock의 문서명과 순서를 최대한 유지한다.
- backend 내부 구현은 바꿔도 되지만, API로 나가는 문서 타입과 문서명은 프론트가 기대하는 형태에 맞춘다.
- 즉, 이번 단계에서는 backend 중심 taxonomy 재설계보다 프론트 계약 호환성을 우선한다.

### D. 법령 corpus와 `LegalBasisEntry`를 실제로 연결하는 계층 구현

#### 현재 문제

- 기존에는 `DocumentDetail.legalBasis`가 프론트 mock의 `legal-basis.json`에 의존했다.
- 하지만 사용자는 앞으로 법령 데이터를 `backend/mock_data` JSON만 제공하겠다고 했다.
- 따라서 문서 상세에 붙는 법적 근거도 이제는 corpus 검색 결과에서 만들어야 한다.

#### 구현 항목

- `RelatedArticleCandidate` 또는 `EvidenceItem`을 `LegalBasisEntry`로 변환하는 resolver 추가
- 최소 포함 정보
  - stable id
  - lawName
  - article
  - summary
  - rationale
  - relatedDocumentIds
- `legalBasisIds`의 의미 재정의
  - 기존처럼 임의의 `lb-001` 형식을 유지할지
  - 아니면 `unit_id` 또는 `evidence_id` 기반으로 바꿀지
- `DocumentRecord`에는 최소한 원본 근거 참조를 남겨야 함
  - `unit_id`
  - `official_law_id`
  - `citation_label`
  - `evidence_type`

#### 권장 방향

- 내부 저장은 corpus 기준 식별자 사용
- API 응답 직전에 `LegalBasisEntry`로 projection
- 즉, 저장 모델과 API 모델을 분리

### E. `mock_data` 스키마를 문서 생성 흐름에서 실제 활용

#### 현재 확인된 점

- `backend/mock_data` 스키마에는 아래 정보가 이미 있다.
  - `articles`
  - `appendices`
  - `forms`
  - `search_synonyms`
  - `document_generation_hints`
- 하지만 현재 문서 생성 흐름은 이 힌트들을 거의 직접 사용하지 않는다.

#### 구현 항목

- `document_generation_hints`를 문서 패키지 planning에 반영
- `forms`를 문서 템플릿/서식 근거로 연결
- `appendices`를 징계 양정 기준 등 보조 근거로 적극 사용
- `search_synonyms`를 질문 생성 또는 근거 검색 정밀도 향상에 활용

#### 기대 효과

- 하드코딩된 `FORM_LIBRARY` 의존 감소
- 사용자가 `mock_data` JSON만 수정해도 문서 생성 품질이 개선되는 구조 확보

### F. 하드코딩된 evidence library 정리

#### 현재 문제

- `backend/documents/evidence.py` 안의 정적 라이브러리는 빠른 데모에는 유용하지만, 사용자가 말한 "JSON 기반 법령 제공" 방향과 충돌할 수 있다.

#### 구현 선택지

1. 당장은 유지하되 역할을 명확히 제한
- law/regulation은 `mock_data` corpus에서만 가져오기
- case/form 보조 라이브러리만 유지

2. 중기적으로 `mock_data` 스키마로 흡수
- case examples
- form hints
- document template hints

#### 권장안

- 이번 backend 완성 단계에서는 1안이 현실적이다.
- 다만 `law`와 `regulation` 근거는 corpus 우선 원칙으로 바꿔야 한다.

### G. 질문 생성과 답변 반영 루프 구현 강화

#### 현재 문제

- 지금은 `submit_question_answer()`가 상태만 바꾸는 수준에 가깝다.
- 실제로는 질문 생성 사유, 문서 재생성, 버전 증가, timeline 반영이 더 명확해야 한다.

#### 구현 항목

- 질문 생성 규칙 정립
  - `structured_case.missing_slots`
  - 문서 타입별 필수 입력 누락
  - `checklist_missing_info`
- 질문과 문서의 연결 명확화
  - 어떤 문서 때문에 생긴 질문인지
  - 어떤 섹션/근거 보강을 위한 질문인지
- 답변 제출 시 처리
  - 질문 상태 변경
  - 대상 문서 재생성
  - `versionHistory` 추가
  - 필요 시 `reviewHistory` 추가
  - case progress/status 재계산
  - timeline event 추가

#### 최소 완료 기준

- 질문 답변 후 문서 본문 또는 근거가 실제로 바뀌어야 함
- 단순 상태 토글만으로 끝나면 안 됨

### H. timeline / workflow stage 계산을 seed 기반이 아니라 상태 기반으로 재정리

#### 현재 문제

- 현재 timeline과 workflow stage는 프론트 mock seed를 hydrate하는 방식이 강하다.
- 실제 backend workflow에서는 상태 변화가 먼저이고, timeline/stage는 그 결과여야 한다.

#### 구현 항목

- 이벤트 중심 timeline 생성
  - case_registered
  - attachment_registered / attachment_skipped
  - information_requested
  - information_received
  - document_generated
  - document_completed
  - review_requested
  - review_completed
- workflow stage 계산을 현재 persisted 상태에서 유도
- stage 계산 로직과 case status 계산 로직을 분리

#### 기대 효과

- seed가 없어도 일관된 상태 재구성이 가능
- 추후 persistence 추가 시 복원 로직이 쉬워짐

### I. `legal-basis` API와 문서 상세 응답의 계약 재점검

#### 현재 상태

- 프론트 서비스는 별도의 `/legal-basis`를 쓰지 않고 문서 상세 내부의 `legalBasis`를 사용한다.
- `backend`에는 `/api/legal-basis`가 이미 있지만 우선순위가 높지는 않다.

#### 구현 방향

- 1순위: `GET /api/cases/{case_id}/documents/{document_id}`가 완전한 `legalBasis`를 반환하도록 보장
- 2순위: 필요하면 `/api/legal-basis?ids=...`를 유지
- 3순위: 내부 전용이면 추후 정리 가능

### J. 테스트를 "프론트 mock 계약 보존 + backend 독립성" 기준으로 재작성

#### 반드시 추가해야 할 테스트

- 서버가 `frontend/src/mocks` 없이도 기동 가능한지
- `backend/case_management/seed`만으로 `/api/cases`가 동작하는지
- 사건 생성 시 문서 패키지가 생성되는지
- 문서 상세가 corpus 기반 `legalBasis`를 반환하는지
- 질문 생성/답변 제출 후 문서 버전과 case 상태가 바뀌는지
- `mock_data` 법령 재적재 후 관련 조항 검색과 문서 생성이 계속 동작하는지

#### 수정이 필요한 기존 테스트 성격

- 현재 `backend/tests/test_frontend_case_management_api.py`는 사실상 "프론트 mock을 backend가 잘 읽는지"를 검증한다.
- 앞으로는 "backend가 자체 seed와 상태 관리만으로 프론트 계약을 만족하는지"를 검증하도록 바꿔야 한다.

## 5. 파일 단위로 보면 어디를 손대야 하는가

### 거의 확실히 수정될 파일

- `backend/case_management/service.py`
- `backend/case_management/schemas.py`
- `backend/main.py`
- `backend/documents/evidence.py`
- `backend/tests/test_frontend_case_management_api.py`
- `backend/README.md`

### 새로 생길 가능성이 높은 파일

- `backend/case_management/repository.py`
- `backend/case_management/bootstrap.py`
- `backend/case_management/orchestrator.py`
- `backend/case_management/legal_basis.py`
- `backend/case_management/workflow.py`
- `backend/case_management/seed/*.json`

### 조건부로 수정될 파일

- `backend/ingestion/mock_data.py`
- `backend/schemas/documents.py`
- `backend/search/*`

## 6. 권장 구현 순서

### Phase 1. 프론트 의존 제거

- `backend/case_management/seed` 구축
- seed loading 경로 변경
- `CaseWorkflowService`가 더 이상 `frontend/src/mocks`를 읽지 않도록 수정
- `disciplinary` seed만 우선 구성

#### 완료 기준

- `frontend` 폴더를 읽지 않아도 `/api/cases` 테스트가 통과한다.
- `disciplinary` 사건 seed만으로 기본 목록/상세/문서/질문 조회가 동작한다.

### Phase 2. backend 전용 case/document/question 저장 구조 정리

- repository/store 계층 추가
- hydrate 중심 로직을 aggregate 중심 로직으로 전환
- case summary 계산, stage 계산, timeline 생성 분리

#### 완료 기준

- 사건 생성, 조회, 문서 조회, 질문 조회가 모두 backend 내부 상태만으로 동작한다.

### Phase 3. 법령 corpus 기반 근거 연결

- `LegalBasisResolver` 구현
- `DocumentRecord` 또는 내부 문서 엔티티에 corpus evidence ref 저장
- 문서 상세 응답에서 `legalBasis` 구성
- `military_discipline_rule_demo.json` 기준으로 `disciplinary` 문서 근거를 연결

#### 완료 기준

- 문서 상세 응답의 법적 근거가 더 이상 frontend `legal-basis.json`에 의존하지 않는다.
- `disciplinary` 문서 상세에서 법적 근거가 `backend/mock_data` corpus에서 유도된다.

### Phase 4. 문서 패키지 planning + 생성 orchestration

- `disciplinary` 문서 패키지 정의
- 초기 문서 생성 규칙 추가
- `document_generation_hints` 연결
- 프론트 mock의 문서명/순서/상태 흐름 최대한 유지

#### 완료 기준

- 사건 생성 후 실제 문서 패키지가 생성되고, 상태가 `pending/generating/completed/needs_input` 중 하나로 합리적으로 배정된다.
- 생성된 문서명이 프론트 mock 구조와 최대한 호환된다.

### Phase 5. 질문/답변 루프와 문서 재생성

- 질문 생성 규칙 추가
- 답변 제출 시 재생성 및 versionHistory 반영
- timeline/workflow 갱신

#### 완료 기준

- 질문 답변 전후로 문서 상태, 버전, case 상태, timeline이 실제로 변한다.

### Phase 6. 테스트/문서 정리

- 테스트 재작성
- README 업데이트
- 운영상 필요 없는 endpoint는 우선순위 낮춤 또는 문서상 비활성 취급

#### 완료 기준

- 현재 범위의 핵심 API에 대한 회귀 테스트가 존재한다.

## 7. 이번 범위에서 우선 제외해도 되는 것

- 외부 법령 OPEN API를 더 풍부하게 붙이는 작업
- RDB 도입 및 migration
- 사용자 인증/권한
- 첨부파일 바이너리 업로드/저장
- 실시간 작업 큐
- 프론트 최적화

## 8. 가장 중요한 오픈 이슈

### 1. 현재 `mock_data`가 징계 계열 1개 파일뿐이다

- 현재 데이터는 `disciplinary` 1차 범위와는 잘 맞는다.
- 따라서 이번 단계에서는 이 이슈를 blocker로 보지 않는다.
- 다만 다음 단계에서 `criminal`, `other`를 확장하려면 추가 법령 JSON이 필요하다.

### 2. 문서 taxonomy를 어디까지 유지할지 결정이 필요하다

- 이 항목은 이번 단계에서 이미 결정되었다.
- 현재 프론트 mock 문서명과 구조를 최대한 유지한다.

### 3. 서버 재시작 시 상태 초기화가 허용되는지 확인이 필요하다

- 데모라면 in-memory로 충분할 수 있다.
- 하지만 사용 흐름 시연 중 재시작 복원이 필요하면 file-based persistence까지 고려해야 한다.

## 9. 결론

- 가장 먼저 해야 할 일은 "프론트 mock 읽는 백엔드"를 "자기 seed/state를 가진 백엔드"로 바꾸는 것이다.
- 그 다음 핵심은 "case workflow"와 "law corpus"를 연결하는 것이다.
- 특히 문서 상세의 법적 근거와 질문/답변 후 문서 재생성 루프가 실제 backend답게 동작해야 프론트 API 전환이 의미가 생긴다.
- 현재 범위에서는 `disciplinary`를 실제로 완성하고, 프론트의 현 API 호출 방식과 문서명 구조를 최대한 그대로 맞추는 것이 최우선 목표다.

## 10. 현재 남은 개선 과제

- 프론트가 아직 직접 읽고 있는 `legal-basis.json` 의존을 제거하고, `/api/cases/.../documents/...` 응답만 사용하도록 정리
- `disciplinary` 문서별 법적 근거 선택을 현재의 규칙 기반 매핑에서 retrieval 보강 방식으로 확장
- `criminal`, `other` 사건 유형을 지원하려면 별도 `mock_data` 법령 JSON과 문서 패키지 정의 추가
