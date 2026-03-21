너는 숙련된 프론트엔드 엔지니어다.
React 기반으로 “군 내 법률 문서 생성 지원 서비스”의 데모용 프론트엔드를 구현해라.

# 1. 프로젝트 목적

이 서비스는 군 조직 내에서 사용자가 법률적 처리(예: 형사 사건, 징계 사건 등)를 진행할 때,
사건 내용을 입력하면 필요한 문서들을 순서대로 생성하고, 각 문서에 대해 법률적 근거와 작성 상태를 보여주는 서비스다.

사용자는 사건이 발생할 때 사건 내용을 작성한다.
시스템은 해당 사건을 처리하기 위해 필요한 문서 목록을 도출하고,
각 문서를 단계적으로 생성하며,
필요한 경우 LLM이 추가 질문을 던져 정보를 보완한 뒤 최종 문서를 완성한다.

이 프로젝트는 실제 백엔드 없이, 모든 데이터를 `.json` mock data로 처리하는 데모 프론트엔드다.
군대 창업경진대회 발표용이므로, “복잡한 법률 절차를 쉽게 정리해주는 서비스”라는 인상을 주는 UI/UX가 중요하다.

# 2. 기술 요구사항

- React + TypeScript 기반으로 작성
- 빌드 환경은 Vite 사용
- 스타일링은 Tailwind CSS 사용
- 상태 관리는 React 기본 훅 또는 가벼운 방식으로 구현
- 라우팅은 React Router 사용
- 실제 API 호출은 하지 말고, `/src/mocks/*.json` 파일을 읽어와 사용하는 방식으로 구성
- 서비스/리포지토리 계층 느낌을 살리기 위해 mock API wrapper를 만들어라
- 코드 구조는 유지보수하기 쉽게 컴포넌트, pages, mocks, types, services로 분리
- 데모 발표용이므로 UI는 깔끔하고 신뢰감 있게 구성
- 군용/법률 서비스 느낌이 나도록 과도하게 화려하지 않고 정돈된 디자인 사용
- 반응형으로 작성하되 데스크톱 우선
- 접근성과 가독성을 고려
- 모든 주요 상태에 대해 로딩 / 빈 상태 / 에러 상태 UI를 만들어라

# 3. 서비스 컨셉

서비스 이름은 임시로 “LawFlow” 또는 “군법 문서 도우미” 중 하나를 사용해도 된다.
전체 사용 흐름은 다음과 같다.

1. 사용자가 사건을 생성한다.
2. 사건 기본 정보와 사실관계를 입력한다.
3. 시스템이 사건 유형(형사 / 징계 / 기타)을 기반으로 필요한 문서 목록을 제시한다.
4. 각 문서는 순서대로 생성되며, 문서별 진행 상태가 표시된다.
5. 문서 생성 과정에서 추가 정보가 필요하면 “LLM 추가 질문”이 나타난다.
6. 사용자가 답변하면 문서 초안이 보완된다.
7. 완성된 문서는 상세 화면에서 확인할 수 있고, 법률적 근거(조항/사유)도 함께 볼 수 있다.
8. 최종적으로 사건 단위로 전체 문서 진행 현황을 볼 수 있다.

# 4. 구현해야 할 핵심 화면

다음 페이지를 구현해라.

## A. 대시보드 페이지 `/`
목적:
- 전체 사건 목록을 확인
- 사건 진행 상태를 빠르게 파악
- 새 사건 생성 진입

포함 요소:
- 상단 헤더: 서비스명, 간단한 설명, 새 사건 생성 버튼
- 요약 카드:
  - 전체 사건 수
  - 진행 중 사건 수
  - 문서 작성 완료 사건 수
  - 추가 질문 대기 사건 수
- 사건 리스트 테이블 또는 카드:
  - 사건명
  - 사건 유형
  - 상태
  - 생성일
  - 마지막 수정일
  - 진행률
- 검색/필터:
  - 사건명 검색
  - 사건 유형 필터
  - 상태 필터

## B. 사건 생성 페이지 `/cases/new`
목적:
- 사용자가 사건을 신규 등록

입력 폼:
- 사건 제목
- 사건 유형 (형사 / 징계 / 기타)
- 발생 일시
- 발생 장소
- 작성자
- 관련자
- 사건 개요
- 상세 사실관계
- 첨부자료 유무 (mock checkbox 정도)
- 긴급도

요구사항:
- 폼 validation
- 제출 시 mock 데이터에 기반해 새 사건 생성된 것처럼 UI 처리
- 제출 후 해당 사건 상세 페이지로 이동

## C. 사건 상세 페이지 `/cases/:caseId`
목적:
- 사건 개요, 진행 상태, 필요한 문서 목록, 추가 질문 현황을 한 화면에서 확인

레이아웃:
왼쪽 또는 상단:
- 사건 기본 정보 카드
- 사건 요약
- 상태 배지
- 진행률 바

오른쪽 또는 하단:
- 문서 생성 단계 리스트
  - 문서명
  - 설명
  - 상태 (대기 / 작성 중 / 추가정보 필요 / 완료)
  - 법률적 근거 요약
  - 상세 보기 버튼
- LLM 추가 질문 섹션
  - 현재 질문
  - 사용자 답변 입력
  - 답변 제출 버튼
- 최근 활동 타임라인
  - 사건 생성
  - 문서 초안 생성
  - 질문 요청
  - 답변 반영
  - 문서 완료

## D. 문서 상세 페이지 `/cases/:caseId/documents/:documentId`
목적:
- 문서 초안과 법률적 근거를 보여줌

포함 요소:
- 문서 제목
- 문서 상태
- 생성 순서 단계 정보
- 문서 본문 미리보기
- 법률적 근거 패널
  - 관련 법 조항명
  - 조항 요약
  - 왜 이 조항이 적용되는지 설명
- 문서 버전 이력(mock)
- 수정 요청 또는 추가 질문 이력(mock)
- 이전/다음 문서 이동 버튼

## E. 추가 질문 응답 페이지 또는 모달
목적:
- 문서 생성 과정에서 LLM이 요청한 추가 정보 응답

포함 요소:
- 질문 제목
- 질문 설명
- 왜 이 정보가 필요한지 설명
- 답변 입력란
- 관련 문서 표시
- 제출 후 상태 변경

## F. 전체 문서 흐름 페이지 `/workflow/:caseId` (선택이 아니라 구현)
목적:
- 군대 창업경진대회 데모에서 핵심 흐름을 한눈에 보여주기 위한 시각화 페이지

포함 요소:
- 사건 → 사실관계 입력 → 문서 목록 생성 → 추가 질문 → 문서 완성 → 법무관 제출
- 각 단계를 stepper 또는 flow diagram으로 표현
- 현재 어느 단계인지 강조
- 각 단계 클릭 시 관련 데이터 표시

# 5. 반드시 포함해야 할 주요 UI 컴포넌트

재사용 가능한 컴포넌트로 분리해라.

- Header
- Sidebar 또는 Top Navigation
- SummaryCard
- StatusBadge
- ProgressBar
- CaseCard / CaseTable
- DocumentStepCard
- LegalBasisCard
- QuestionBox
- Timeline
- EmptyState
- ErrorState
- LoadingSpinner
- SearchFilterBar
- PageSection
- KeyValueInfoList

# 6. 상태 설계

다음 상태들을 명확히 표현해라.

사건 상태 예시:
- draft
- in_progress
- waiting_for_input
- completed

문서 상태 예시:
- pending
- generating
- needs_input
- completed

질문 상태 예시:
- open
- answered

각 상태는 배지 색상과 텍스트로 명확히 보이게 만들어라.

# 7. mock 데이터 구조

아래 JSON 파일들을 `/src/mocks` 폴더에 만들어 사용해라.

## `/src/mocks/cases.json`
사건 목록
필드 예시:
- id
- title
- caseType
- status
- occurredAt
- location
- author
- relatedPersons
- summary
- details
- priority
- createdAt
- updatedAt
- progressPercent
- activeQuestionCount
- documentCount

## `/src/mocks/case-detail.json`
단일 사건 상세
필드 예시:
- id
- title
- caseType
- status
- summary
- details
- timeline[]
- documents[]
- questions[]
- legalReviewSummary

## `/src/mocks/documents.json`
문서 목록/상세
필드 예시:
- id
- caseId
- title
- type
- order
- status
- description
- content
- legalBasis[]
- versionHistory[]
- updatedAt

## `/src/mocks/questions.json`
추가 질문 목록
필드 예시:
- id
- caseId
- documentId
- title
- prompt
- reason
- status
- answer
- createdAt
- answeredAt

## `/src/mocks/legal-basis.json`
법률적 근거
필드 예시:
- id
- lawName
- article
- summary
- rationale
- relatedDocumentIds[]

데이터는 최소 5개 사건, 각 사건당 3~5개 문서, 일부는 질문 대기 상태가 되도록 구성해라.
형사 사건과 징계 사건 예시를 모두 포함해라.

# 8. mock API 계층

실제 API처럼 보이도록 다음 구조를 만들어라.

- `/src/services/mockApi.ts`
- `/src/services/caseService.ts`
- `/src/services/documentService.ts`
- `/src/services/questionService.ts`

요구사항:
- `Promise` 기반으로 비동기 처리
- `setTimeout`을 이용해 네트워크 지연을 흉내 내기
- 목록 조회, 상세 조회, 생성, 상태 변경, 질문 답변 제출 등의 함수 제공
- 실제 서버는 없지만 프론트에서는 API를 호출하는 것처럼 보이게 만들어라

예시 함수:
- getCases()
- getCaseById(caseId)
- createCase(payload)
- getDocumentsByCaseId(caseId)
- getDocumentById(caseId, documentId)
- getOpenQuestions(caseId)
- submitQuestionAnswer(questionId, answer)

# 9. UX/디자인 가이드

디자인 방향:
- 신뢰감
- 정돈됨
- 법률/행정 서비스 느낌
- 발표용 데모답게 직관적
- 사용자가 “복잡한 절차가 단계별로 정리된다”고 느끼게 할 것

권장 UI 특징:
- 카드 중심 레이아웃
- stepper / timeline 적극 활용
- 중요 상태는 배지와 아이콘으로 구분
- 본문은 너무 빽빽하지 않게 section 단위로 분리
- 문서 본문은 실제 공문/진술서 초안처럼 보이게 프리뷰 스타일 제공
- 법률적 근거는 별도 강조 박스로 시각 분리
- “LLM이 추가 질문을 통해 문서를 보완한다”는 점이 눈에 띄게 보여야 함

# 10. 정보 구조와 사용자 흐름

사용자가 처음 들어오면 대시보드에서 사건 현황을 확인한다.
그 후 새 사건을 생성하거나 기존 사건을 선택한다.
사건 상세 페이지에서는:
- 사건 정보
- 필요한 문서 목록
- 각 문서의 상태
- 추가 질문 필요 여부
를 바로 파악할 수 있어야 한다.

문서 상세 페이지에서는:
- 문서 초안
- 어떤 법률적 근거로 생성되었는지
- 추가 질문이 왜 필요한지
를 쉽게 이해할 수 있어야 한다.

전체 workflow 페이지에서는 “이 서비스가 단순 문서 편집기가 아니라, 사건 처리 흐름 전체를 안내하는 시스템”처럼 보이게 만들어라.

# 11. 구현 품질 요구사항

- 타입 정의를 명확히 작성
- 하드코딩 남발하지 말고 enum 또는 상수 분리
- 컴포넌트 props 타입 분리
- 중복 UI는 재사용 컴포넌트로 추출
- 페이지 컴포넌트는 너무 비대해지지 않게 구성
- mock 데이터 구조와 타입을 일치시켜라
- 라우팅, 서비스, 타입, UI 컴포넌트가 명확히 구분되게 작성
- 초심자도 읽기 쉬운 구조로 작성
- 코드에는 필요한 수준의 주석만 추가
- 데모 시연을 위해 README에 실행 방법과 화면 설명을 작성

# 12. 폴더 구조 예시

다음과 같이 구성해라.

src/
  app/
    router.tsx
  components/
    common/
    dashboard/
    case/
    document/
    workflow/
  pages/
    DashboardPage.tsx
    CaseCreatePage.tsx
    CaseDetailPage.tsx
    DocumentDetailPage.tsx
    WorkflowPage.tsx
  mocks/
    cases.json
    case-detail.json
    documents.json
    questions.json
    legal-basis.json
  services/
    mockApi.ts
    caseService.ts
    documentService.ts
    questionService.ts
  types/
    case.ts
    document.ts
    question.ts
    legalBasis.ts
    common.ts
  utils/
    formatDate.ts
    status.ts
    progress.ts
  App.tsx
  main.tsx

# 13. 반드시 구현해야 하는 세부 기능

- 사건 목록 조회
- 사건 검색 및 필터
- 사건 생성 폼
- 사건 상세 조회
- 문서 목록 및 상태 표시
- 문서 상세 조회
- 질문 응답 제출
- 질문 제출 후 UI 상태 갱신
- workflow 시각화
- 로딩/에러/빈 상태 처리
- 주요 버튼 hover/focus 상태
- 최소한의 토스트 또는 성공 메시지

# 14. 데모 시나리오를 고려한 데이터

아래와 같은 시나리오가 보이도록 mock 데이터를 설계해라.

시나리오 예시 1:
- 형사 사건
- 사건 등록 완료
- 진술서 초안 생성됨
- 사건경위서 생성 중
- 추가 질문 1건 대기
- 법률적 근거 표시 가능

시나리오 예시 2:
- 징계 사건
- 필요한 문서 4개 중 4개 완료
- 법무관 제출 직전 상태

시나리오 예시 3:
- 입력이 부족하여 질문이 여러 번 발생한 사건
- 질문-답변 이력이 타임라인에 남아 있음

# 15. 최종 산출물

다음 결과를 모두 만들어라.

1. 실행 가능한 React 프로젝트 코드
2. mock JSON 데이터
3. 주요 타입 정의
4. mock service 계층
5. 모든 페이지 및 핵심 컴포넌트
6. README
7. 보기 좋은 기본 UI

# 16. 작업 방식

- 먼저 전체 파일 구조를 설계하라
- 그 다음 타입 정의와 mock 데이터를 만들고
- 이후 services를 만들고
- 공통 컴포넌트
- 페이지
- 라우팅
- 마지막으로 README를 작성하라

중간에 불필요한 확인 질문 없이 합리적으로 판단해서 진행해라.
단, 타입 안정성과 가독성을 우선하라.

# 17. 추가 요구사항

- 문서 본문은 너무 짧지 않게 실제 초안처럼 여러 문단으로 구성
- 법률적 근거 설명도 단순 제목만 두지 말고 적용 이유를 서술
- 군 조직에서 사용하는 서비스처럼 포멀한 문구를 사용
- 하지만 지나치게 딱딱하지 않게 현대적인 UI를 유지
- 색상은 남색/회색 계열 중심의 안정적인 팔레트 사용
- 데모 발표자가 설명하기 좋은 구조로 만들어라

이제 위 요구사항을 충족하는 프론트엔드 프로젝트를 구현해라.
우선 전체 파일 구조와 핵심 타입 정의부터 작성하고, 이어서 각 파일의 코드를 차례대로 제시해라.

중요: 결과물은 “실무용 MVP + 발표용 데모”의 중간 정도 퀄리티를 목표로 하고, 단순 예제가 아니라 실제 서비스 프로토타입처럼 보이게 구현해라.