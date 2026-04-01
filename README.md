# Lawer Service

군 내 사건 처리와 법률 문서 생성을 시연하기 위한 프론트엔드 + 백엔드 저장소다. 저장소의 기준은 `프론트 화면 계약 우선, 백엔드는 내부 파이프라인으로 동작` 이다.

## 저장소 구조

- `frontend/`
  - React + TypeScript + Vite 데모 UI
  - 사건 등록, 사건 상세, 문서 상세, 워크플로우 시각화 화면 제공
- `backend/`
  - FastAPI 기반 API 서버
  - 프론트용 사건 워크플로우 API와 내부 검색/문서생성 파이프라인 제공

## 백엔드 동작 원칙

백엔드는 두 층으로 이해하면 된다.

1. 외부 인터페이스
   - `/api/cases*`, `/api/questions*`, `/api/legal-basis`
   - 프론트 화면이 바로 사용하는 사건 중심 API
2. 내부 엔진
   - 관련 조항 찾기 파이프라인
     - 사실관계 구조화
     - 법체계 라우팅
     - Graph RAG + 보조 검색
     - Retrieval Evaluator
   - 법률 문서 생성 파이프라인
     - 근거 수집
     - 문단/조항 계획
     - 섹션별 생성
     - Draft Evaluator
     - 안전장치

즉, 프론트는 사건 단위 워크플로우를 보지만, 백엔드는 그 안에서 검색과 생성 파이프라인을 별도로 수행한다.

## 빠른 시작

### Backend

```bash
cd /home/desktopuser/Desktop/code/lawer_service
./scripts/dev.sh
```

기본 주소:

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd /home/desktopuser/Desktop/code/lawer_service/frontend
npm install
npm run dev
```

## 문서 위치

- 백엔드 상세 설계와 엔드포인트: [backend/README.md](/home/desktopuser/Desktop/code/lawer_service/backend/README.md)
- 프론트 실행 방법과 화면 구성: [frontend/README.md](/home/desktopuser/Desktop/code/lawer_service/frontend/README.md)

## 현재 범위

- 프론트 워크플로우 API는 현재 `disciplinary` 사건을 1차 범위로 본다.
- 저장소와 검색 인덱스는 기본적으로 in-memory다.
- `mock_data` 와 `case_management/seed` 를 기준으로 데모 데이터를 적재한다.
- 실제 법령 수집은 `LAW_API_OC`, Gemini 기반 문서 생성은 `GEMINI_API_KEY` 가 있어야 한다.
