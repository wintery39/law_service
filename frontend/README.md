# MILO Frontend

MILO(Military Legal OS)는 군 내 사건 처리와 법률 문서 생성을 단계별로 보여주는 React 데모 프론트엔드입니다. 실제 백엔드 없이 `src/mocks/*.json`을 기반으로 동작하며, 사건 등록부터 문서 생성, 추가 질문 응답, 워크플로우 시각화까지 한 흐름으로 시연할 수 있게 구성했습니다.

## 실행 방법

검증된 런타임:

- Node.js `12.22.9`
- npm `8.5.1`

환경 변수:

```bash
cp .env.example .env
```

`VITE_API_BASE_URL` 에 프론트가 호출할 API 주소를 넣어야 합니다. 현재 저장소에서는 `frontend/.env` 가 Git에 포함되지 않도록 설정되어 있습니다.

```bash
npm install
npm run dev
```

빌드 확인:

```bash
npm run build
```

## 기술 스택

- React + TypeScript
- Vite
- Tailwind CSS
- React Router
- JSON mock data + Promise 기반 mock API

## 주요 화면

- `/`
  사건 대시보드, 검색/필터, 상태 요약 카드, 사건 목록
- `/cases/new`
  신규 사건 등록 폼, 유효성 검사, 등록 후 상세 화면 이동
- `/cases/:caseId`
  사건 기본 정보, 진행률, 문서 단계, LLM 추가 질문, 활동 타임라인
- `/cases/:caseId/documents/:documentId`
  문서 본문 프리뷰, 법률 근거, 버전 이력, 질문/보완 이력
- `/workflow/:caseId`
  사건 처리 전체 흐름을 단계별로 설명하는 발표용 시각화 페이지

## 폴더 구조

```text
src/
  app/
    router.tsx
  components/
    case/
    common/
    dashboard/
    document/
    layout/
    workflow/
  context/
    ToastContext.tsx
  mocks/
    case-detail.json
    cases.json
    documents.json
    legal-basis.json
    questions.json
  pages/
    CaseCreatePage.tsx
    CaseDetailPage.tsx
    DashboardPage.tsx
    DocumentDetailPage.tsx
    NotFoundPage.tsx
    WorkflowPage.tsx
  services/
    mockApi.ts
    caseService.ts
    documentService.ts
    questionService.ts
  types/
    case.ts
    common.ts
    document.ts
    legalBasis.ts
    question.ts
  utils/
    formatDate.ts
    progress.ts
    status.ts
```

## 데모 포인트

- 형사, 징계, 기타 사건이 함께 포함되어 있고 사건별 문서 수와 상태가 다릅니다.
- 일부 사건은 `waiting_for_input` 상태로, LLM 추가 질문과 답변 반영 흐름을 시연할 수 있습니다.
- 질문 답변 제출 시 mock API 내부 상태가 갱신되고 사건 진행률, 문서 상태, 타임라인이 함께 변경됩니다.
- 문서 상세 화면에서 법률적 근거와 버전 이력을 함께 보여줘 발표 시 설명 포인트를 확보할 수 있습니다.

## 참고 사항

- 데이터는 브라우저 세션 동안 메모리에서 갱신되며 새로고침 시 mock seed 기준으로 초기화됩니다.
- 실제 법률 자문 시스템이 아니라 발표용 프로토타입이므로, 조항명과 설명은 시연 목적에 맞춰 단순화되어 있습니다.
