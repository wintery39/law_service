# Lawer Service

법률 RAG 기반 서비스 저장소입니다.

- `frontend/`: Vite + React 기반 데모 UI
- `backend/`: FastAPI 기반 법령 코퍼스, 관련 조항 탐색, 문서 생성, 평가 모듈

## What The API Can Do

백엔드는 다음 기능을 제공합니다.

- 국가법령정보 OPEN API에서 법령을 수집해 in-memory 코퍼스로 적재
- 법령/버전/조문 조회
- 조문 텍스트 검색
- 법령 그래프 이웃 탐색
- 사용자 서술을 구조화하고 관련 조항 후보 검색
- 사실관계 정리서, 징계 의견서, 항변서 초안 생성
- 문서 생성 진행 상황을 SSE 또는 WebSocket으로 스트리밍
- retrieval / generation / safety 평가 실행

## Quick Start

```bash
cd /home/desktopuser/Desktop/code/lawer_service
./scripts/dev.sh
```

기본 서버 주소는 `http://127.0.0.1:8000` 입니다.

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

실제 법령 수집을 쓰려면 [backend/.env](/home/desktopuser/Desktop/code/lawer_service/backend/.env)에 `LAW_API_OC` 값을 넣어야 합니다.

## Main API Flow

1. 법령 수집
2. 관련 조항 찾기
3. 문서 생성
4. 필요하면 평가 실행

자세한 엔드포인트와 예시는 [backend/README.md](/home/desktopuser/Desktop/code/lawer_service/backend/README.md)에 정리되어 있습니다.
