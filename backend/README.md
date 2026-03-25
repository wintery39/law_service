# Law Corpus Backend

법령 코퍼스 공통 기반 백엔드입니다.

- 캐노니컬 스키마: `Law`, `Unit`, `Version`, `Reference`, `SourceMeta`
- 수집기: 국가법령정보 공동활용 OPEN API 연동용 클라이언트 및 변환기
- 저장소 추상화: `GraphStore`, `TextSearchStore`, `VectorStore`, `CorpusRepository`
- 기본 구현: 모두 in-memory 구현 포함
- API: FastAPI 기반 조회/수집/검색/그래프 엔드포인트

## 실행

```bash
uv sync
uv run uvicorn main:app --reload
```

## 테스트

```bash
uv run pytest
```
