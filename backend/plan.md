# Backend RAG 및 문서 생성 고도화 계획

## 1. 문서 목적

- 현재 backend의 관련 조항 찾기 서비스와 문서 생성 서비스를, 실제 법률 RAG 시스템과 법률 문서 생성 시스템으로 발전시키기 위한 구현 계획을 정리한다.
- 이 문서는 "아이디어 요약"이 아니라 실제 코드 수정 순서, 책임 분리, 데이터 계약, 평가 기준까지 포함한 실행 계획서다.
- 1차 구현 범위는 현재 프로젝트 상태와 동일하게 `disciplinary` 중심으로 잡는다.
- 법령 데이터의 1차 원천은 계속 `backend/mock_data/*.json`으로 둔다.
- 프론트 연동 계약은 유지하되, 내부 구현은 RAG 중심 구조로 재조직한다.

## 2. 전제와 범위

- 현재 사건 워크플로우의 1차 완성 범위는 `disciplinary`다.
- 관련 조항 찾기와 문서 생성은 backend가 단독으로 동작 가능해야 한다.
- 문서 생성에는 Gemini API를 사용할 수 있다.
- 관련 조항 찾기에도 LLM을 도입하되, 검색 전체를 LLM에 맡기지 않고 구조화, rerank, grounded generation 보조에 사용한다.
- `backend/mock_data`는 1차 corpus이므로, 없는 판례나 법령은 "없음"으로 처리해야지 임의로 만들면 안 된다.
- GraphDB 도입은 장기적으로 유효하지만, 1차 핵심은 DB 종류보다 ontology와 retrieval/eval 품질이다.

## 3. 현재 구현 진단

### 3-1. 관련 조항 찾기 서비스

- 현재 진입점은 `backend/search/pipeline.py`의 `RelatedArticleFinderService`다.
- 파이프라인 형태는 이미 존재한다.
  - 사실관계 구조화
  - 라우팅
  - retrieval
  - evaluator
  - 최종 결과 반환
- 현재 구조화는 `backend/search/structuring.py`의 `HeuristicSchemaFillingLLM`이 담당한다.
- 현재 라우팅은 `backend/search/routing.py`의 키워드 기반 분류다.
- 현재 retrieval은 `backend/search/retrieval.py`에서 다음을 결합한다.
  - text search
  - pseudo-vector search
  - graph expansion
- 현재 evaluator는 `backend/search/evaluation.py`에서 시행시점/관할/단위 타입 필터와 heuristic rerank를 수행한다.

### 3-2. 현재 RAG의 강점

- 검색 파이프라인의 뼈대는 이미 맞게 나뉘어 있다.
- `mock_data`가 `Law/Version/Unit/Reference`로 canonical하게 적재된다.
- graph, text, vector 저장소가 추상화되어 있어 교체가 가능하다.
- retrieval debug와 evaluation 체계가 이미 존재한다.
- 문서 생성이 retrieval 결과를 `EvidencePack`으로 받아 쓰도록 연결돼 있다.

### 3-3. 현재 RAG의 한계

- 구조화가 아직 heuristic 중심이라 질의 해석 성능이 낮다.
- vector 검색은 실제 embedding이 아니라 token count cosine이다.
- text 검색도 BM25/FTS가 아니라 overlap 기반이다.
- routing이 현재는 사실상 키워드 분류이며, soft prior가 아니라 hard intuition에 가깝다.
- graph retrieval은 reference/parent-child 구조는 있으나 법률 ontology가 아직 얕다.
- evaluator가 hard filter와 semantic rerank를 명확히 분리하지 못한다.
- `search_synonyms`는 index enrichment에는 쓰이지만 query normalization에 충분히 재사용되지 않는다.
- candidate 설명 가능성은 있으나, 왜 최종 채택됐는지에 대한 이유가 충분히 구조화되어 있지 않다.

### 3-4. 문서 생성 서비스

- 현재 진입점은 `backend/documents/service.py`의 `DocumentGenerationService`다.
- evidence 수집, 문서 계획, 섹션 생성, evaluator, streaming 구조가 이미 존재한다.
- 최근 수정으로 Gemini 기반 섹션 생성이 가능해졌고, 미설정 시 heuristic fallback도 가능하다.
- 현재 evidence 수집은 `/services/related-articles/find` 결과에 더해 `CASE_LIBRARY`, `REGULATION_LIBRARY`, `FORM_LIBRARY`를 혼합 사용한다.

### 3-5. 현재 문서 생성의 한계

- retrieval 결과와 section text 사이의 grounding 계약이 아직 약하다.
- Gemini 생성 결과가 `used_evidence_ids`를 직접 내지 않기 때문에, citation은 backend heuristic에 의존한다.
- hardcoded library 의존이 남아 있어 "JSON 기반 corpus 중심" 원칙과 어긋나는 부분이 있다.
- section generation 이후의 draft evaluator는 유효하지만, citation-grounded regeneration loop가 아직 없다.
- 질문 생성과 문서 재생성 루프는 case workflow에는 일부 들어가 있으나, RAG pipeline과 완전히 통합되지는 않았다.

## 4. 목표 아키텍처

### 4-1. 관련 조항 찾기 서비스 목표 파이프라인

사용자 입력  
↓  
[1] 사실관계 구조화  
↓  
[2] 법체계 라우팅  
↓  
[3] Graph RAG + 보조 검색  
↓  
[4] Retrieval Evaluator  
↓  
관련 조항 최종 결과

### 4-2. 문서 생성 서비스 목표 파이프라인

사용자 입력  
↓  
[1] 근거 수집  
↓  
[2] 문단 / 조항 계획  
↓  
[3] 섹션별 생성기  
↓  
[4] Draft Evaluator / 적법성·정합성 검사  
↓  
[5] 안전장치  
↓  
최종 문서 초안

### 4-3. 두 서비스의 연결 원칙

- 문서 생성의 근거 수집은 관련 조항 찾기 서비스를 재사용해야 한다.
- retrieval service와 document generation service는 같은 `StructuredCase`, `RelatedArticleCandidate`, `EvidenceItem` 계열 계약을 공유해야 한다.
- 구조화, retrieval, generation이 서로 다른 용어 체계를 쓰면 안 된다.
- 문서 생성은 retrieval 결과를 "그럴듯한 참고자료"가 아니라 "인용 가능한 근거 단위"로 취급해야 한다.

## 5. 설계 개선 포인트

### 5-1. 법체계 라우팅은 제거가 아니라 "soft prior"로 유지

- 개선안
  - 라우팅은 검색 범위를 좁히는 힌트로만 사용한다.
  - low confidence인 경우 다중 도메인을 병렬 검색한다.
  - routing 결과가 retrieval를 막는 hard filter가 되면 안 된다.
- 이유
  - 법률 문제는 징계와 형사, 행정과 징계처럼 경계가 겹치는 경우가 많다.
  - 초기 라우팅 오분류가 전체 retrieval 실패로 이어지는 구조는 위험하다.

### 5-2. Retrieval Evaluator는 hard filter와 reranker를 분리

- 개선안
  - stage A: 최신성, 시행 여부, 관할, 최소 인용 단위, 폐지 여부 등 hard filter
  - stage B: 사건 적합성, 근거 품질, 설명 가능성을 평가하는 reranker
- 이유
  - "쓰면 안 되는 근거"와 "덜 적합한 근거"는 다른 문제다.
  - 법률 도메인에서는 무효 근거를 먼저 걸러내는 단계가 반드시 분리되어야 한다.

### 5-3. Graph RAG는 "graph 단독"이 아니라 hybrid retrieval의 한 채널이어야 한다

- 개선안
  - graph, BM25/FTS, vector, query rewrite retrieval을 동등한 채널로 두고 fusion한다.
- 이유
  - graph는 구조적 연결에 강하지만, 시작 seed가 약하면 놓치는 문서가 생긴다.
  - lexical과 semantic 보조 검색이 반드시 함께 있어야 recall이 올라간다.

### 5-4. `search_synonyms`를 corpus enrichment뿐 아니라 query normalization에도 사용

- 개선안
  - `mock_data.search_synonyms`를 양방향 사전처럼 사용한다.
  - 사용자 표현 -> 법률 용어 후보 생성에 반영한다.
- 이유
  - 현재는 index 쪽 보강이 중심이라 query side normalization이 약하다.
  - 법률 검색은 일상 표현을 법률 용어로 정규화하는 단계가 매우 중요하다.

### 5-5. 문서 생성 모델은 section text만이 아니라 근거 사용 결과를 같이 내야 한다

- 개선안
  - section generator의 structured output에 `used_evidence_ids`와 `open_issues`를 포함한다.
  - backend는 이 ID가 실제 evidence pack에 존재하는지 검증한다.
- 이유
  - 법률 문서 생성은 텍스트 품질보다 grounding이 더 중요하다.
  - citation이 backend heuristic에만 의존하면 section별 근거 연결이 약해진다.

### 5-6. GraphDB 도입은 ontology와 eval 이후에 진행

- 개선안
  - 1차는 현재 graph abstraction을 유지하면서 relation 설계를 먼저 강화한다.
  - ontology와 retrieval metrics가 안정되면 그때 Neo4j 등으로 이전한다.
- 이유
  - graph 성능의 핵심은 DB 제품보다 node/edge 설계와 retrieval 전략이다.
  - 지금 바로 외부 GraphDB를 붙이면 구현 복잡도만 올라가고 품질 개선은 제한적일 수 있다.

### 5-7. 없는 판례와 선례는 하드코딩으로 메우지 않는다

- 개선안
  - corpus에 없는 자료는 "미제공" 또는 "추가 수집 필요"로 처리한다.
  - 하드코딩 evidence는 점진적으로 제거하거나 명시적 demo fixture로 격리한다.
- 이유
  - 사용자가 제공한 corpus만으로 설명 가능한 시스템이어야 신뢰성이 높다.
  - 법률 시스템에서 fabricated precedent는 치명적이다.

## 6. 세부 구현 계획

### 6-1. 법률 데이터 전처리와 ontology 강화

#### 목표

- `backend/mock_data/*.json`을 Graph RAG에 적합한 unit/edge 구조로 변환한다.

#### 구현 항목

- `backend/ingestion/mock_data.py` 확장
- `Unit` metadata 강화
  - `source_type`: article, appendix, form
  - `domain_tags`
  - `authority_level`
  - `route_hints`
  - `keywords`
  - `aliases`
  - `sanction_category`
  - `document_relevance`
- `Reference` 유형 확장 또는 relation 분류 강화
  - parent-child
  - internal reference
  - appendix linkage
  - form linkage
  - sanction basis
  - procedure basis
  - exception relation
- `search_synonyms` 활용 확장
  - index expansion
  - query normalization dictionary

#### 개선 이유

- 현재 graph는 문서 구조와 일반 참조에는 대응하지만, 법률 reasoning에 중요한 관계를 충분히 담지 못한다.
- Graph RAG의 품질은 retrieval 전략 이전에 ontology 품질에 크게 좌우된다.

### 6-2. 사실관계 구조화 고도화

#### 목표

- 사용자의 자연어 입력을 legal retrieval에 적합한 `StructuredCase`로 안정적으로 변환한다.

#### 구현 항목

- `backend/search/structuring.py`에 Gemini 기반 `SchemaFillingLLM` 구현 추가
- heuristic fallback은 유지
- `StructuredCase` 확장 검토
  - actor
  - counterparty
  - action
  - object
  - time
  - place
  - intent
  - damage
  - requested_relief
  - procedural_stage
  - normalized_legal_terms
  - confidence
- query rewrite 산출물 추가
  - lexical terms
  - semantic paraphrases
  - graph seed terms
  - missing slots
- multi-turn clarification memory 유지

#### 파일 후보

- 수정
  - `backend/search/structuring.py`
  - `backend/schemas/related_articles.py`
- 신규
  - `backend/search/gemini.py`

#### 개선 이유

- 현재 heuristic 구조화는 간단한 질의에는 작동하지만, 복합 사실관계와 법률 용어 정규화에 약하다.
- retrieval 품질은 입력 구조화 성능에 크게 좌우된다.

### 6-3. 법체계 라우팅 재설계

#### 목표

- 도메인 분류를 검색 힌트로 사용하되, 잘못 분류됐을 때도 retrieval이 망가지지 않게 만든다.

#### 구현 항목

- `backend/search/routing.py`를 확률 기반 soft prior 구조로 수정
- 출력값을 다음처럼 재정의
  - `labels`
  - `scores`
  - `retrieval_budget`
  - `preferred_sources`
  - `fallback_domains`
- low confidence routing일 때 multi-domain retrieval 수행

#### 개선 이유

- 사용자 질의는 종종 둘 이상의 법 영역을 동시에 포함한다.
- routing을 hard gate로 두면 recall이 심하게 손상될 수 있다.

### 6-4. Graph RAG + 보조 검색 고도화

#### 목표

- graph, lexical, vector 검색을 실제 hybrid retrieval로 동작시키고, 필요한 후보를 빠짐없이 회수한다.

#### 구현 항목

- `backend/search/retrieval.py` 고도화
- retrieval 채널 분리
  - graph retrieval
  - BM25/FTS retrieval
  - embedding vector retrieval
  - query rewrite retrieval
- retrieval input 분리
  - original user text
  - normalized legal terms
  - graph seed terms
  - document intent aware subqueries
- fusion 개선
  - RRF 유지 가능
  - channel weights 도입
  - source별 calibration 필요
- unit dedupe 정책 강화
  - 같은 조문의 article/appendix/form 중복 정리
- graph expansion depth와 edge type별 가중치 도입

#### 파일 후보

- 수정
  - `backend/search/retrieval.py`
  - `backend/search/store.py`
  - `backend/storage/vector.py`
- 신규
  - `backend/search/query_rewrite.py`
  - `backend/search/reranker.py`
  - `backend/search/ontology.py`

#### 개선 이유

- 현재 vector는 semantic retrieval이 아니고, text search도 production 품질이 아니다.
- Graph RAG만 강조해도 시작 seed가 약하면 recall이 낮다.
- 법률 검색은 최소한 BM25 + real embedding + graph 확장 조합이 필요하다.

### 6-5. Retrieval Evaluator 재설계

#### 목표

- 많이 찾는 것보다 "쓸 수 있는 근거만 남기는 것"에 집중한다.

#### 구현 항목

- `backend/search/evaluation.py`를 2단계 구조로 개편
- hard filter
  - 관할
  - 시행시점
  - 폐지 여부
  - 최소 인용 단위
  - authority level
- rerank
  - 사건 적합성
  - 법적 직접성
  - 설명 가능성
  - overclaim risk
  - retrieval diversity
- 결과에 reason trace 포함
  - why selected
  - why filtered
  - matched terms
  - authority/freshness summary

#### 개선 이유

- 법률 retrieval에서는 top-k recall만으로는 충분하지 않다.
- 최종 후보가 왜 채택되었는지 설명 가능해야 문서 생성 단계에서 신뢰할 수 있다.

### 6-6. 근거 수집 계층 정리

#### 목표

- 문서 생성의 근거 수집을 retrieval 서비스와 동일한 evidence contract 위에서 동작시키고, corpus 외 하드코딩 의존을 줄인다.

#### 구현 항목

- `backend/documents/evidence.py` 개편
- `RelatedArticleCandidate -> EvidenceItem` 변환 규칙 강화
- law/regulation/form 근거는 가능하면 corpus 우선
- hardcoded library 역할 축소
  - 유지가 필요하면 `demo_only` metadata를 명시
- 문서 유형별 evidence requirement 정의
  - 필수 근거
  - 보조 근거
  - 부족 시 질문 생성
- active retrieval loop 강화
  - plan keywords
  - section-specific subqueries

#### 개선 이유

- 지금 구조는 retrieval 기반 근거와 하드코딩 보조 근거가 섞여 있다.
- 문서 생성의 신뢰성을 높이려면 evidence source를 더 명확하게 구분해야 한다.

### 6-7. 문단 / 조항 계획 고도화

#### 목표

- retrieval 결과를 그대로 이어붙이지 않고, 문서 목적에 맞는 계획을 먼저 세운다.

#### 구현 항목

- `backend/documents/planning.py` 확장
- plan 입력
  - document intent
  - structured case
  - evidence pack
  - missing info
- plan 출력
  - 전체 title
  - section order
  - section purpose
  - section key claims
  - required evidence ids
  - required slots
  - 추가 retrieval keywords
- 필요 시 plan 검수 단계 추가
- `Active Retrieval Augmented Generation` 방식으로
  - 계획
  - 추가 retrieval
  - 계획 보강
  - 생성
  순환 구조 지원

#### 개선 이유

- 법률 문서는 문단 순서와 조항 배치가 사실상 reasoning 구조다.
- 현재 plan 구조는 유효하지만, retrieval-driven subquery 설계가 아직 약하다.

### 6-8. 섹션별 생성기 고도화

#### 목표

- section 단위로 생성하면서도 각 section이 어떤 근거에 기대는지 backend가 추적할 수 있게 만든다.

#### 구현 항목

- Gemini section output schema 확장 검토
  - `section_id`
  - `text`
  - `used_evidence_ids`
  - `open_issues`
  - `confidence_note`
- section 생성 input 강화
  - current section plan
  - required evidence
  - previous section summaries
  - global constraints
- 이전 섹션은 full text보다 summary 중심으로 전달
- evidence 없는 section은 생성보다 질문 유도로 전환할 수 있게 설계

#### 파일 후보

- 수정
  - `backend/documents/gemini.py`
  - `backend/documents/service.py`
  - `backend/schemas/documents.py`

#### 개선 이유

- 현재는 Gemini가 section text를 잘 만들더라도 grounding trace가 약하다.
- 법률 문서 생성은 "잘 쓴 문장"보다 "무슨 근거로 썼는가"가 더 중요하다.

### 6-9. Draft Evaluator / 적법성·정합성 검사 강화

#### 목표

- 생성 후 검사를 단순 문장 품질이 아니라 법률 문서 기준으로 강화한다.

#### 구현 항목

- `backend/documents/evaluation.py` 확장
- 검사 항목
  - 필수 섹션 존재 여부
  - 인용 근거 존재 여부
  - 인용 ID 유효성
  - 날짜/인명/장소 일관성
  - 금지 표현
  - unsupported claim 탐지
  - 최신성/시행시점 위반
  - authority mismatch
- section별 patch suggestion 유지
- 필요 시 failed section만 selective regeneration

#### 개선 이유

- 법률 문서는 초안 생성 뒤의 검증 품질이 매우 중요하다.
- citation-grounded evaluator가 없으면 hallucination을 구조적으로 막기 어렵다.

### 6-10. 안전장치와 사용자 검토 패키지

#### 목표

- 문서 초안만 주지 말고, 검토가 필요한 정보도 함께 제공한다.

#### 구현 항목

- 최종 응답에 아래 항목 유지 또는 강화
  - 문서 초안
  - 누락 정보 체크리스트
  - 근거 리포트
  - low confidence section
  - human review required flags
- evidence report에 아래 추가 검토
  - section별 근거 커버리지
  - unused evidence
  - potentially weak evidence

#### 개선 이유

- 사용자는 법률 문서 초안만 받는 것보다, 무엇을 확인해야 하는지 함께 받아야 실무적으로 쓸 수 있다.

### 6-11. 사건 워크플로우와의 통합

#### 목표

- 관련 조항 찾기와 문서 생성이 `/api/cases` 워크플로우 내부에서도 실제 상태 전이로 이어지도록 만든다.

#### 구현 항목

- 사건 생성 시
  - 초기 `StructuredCase` 생성
  - 초기 retrieval preflight
  - 문서 패키지 계획 생성
  - 부족 정보 질문 생성
- 질문 답변 시
  - `StructuredCase` 업데이트
  - retrieval 재실행
  - 영향 받은 section만 재생성
  - `versionHistory`, `reviewHistory`, timeline 갱신
- `disciplinary` workflow 기준으로 우선 연결

#### 개선 이유

- 현재 case workflow와 RAG/generation은 연결되어 있지만 완전히 하나의 pipeline은 아니다.
- 실사용 시스템은 질문-답변-재검색-재생성 루프가 자연스럽게 연결되어야 한다.

## 7. 데이터 계약 정리

### 7-1. 관련 조항 찾기 응답

- `ResultResponse.final`은 최종 인용 가능한 최소 단위만 남긴다.
- 각 candidate에 다음 정보가 필요하다.
  - stable internal id
  - law name
  - official law id
  - unit path
  - snippet
  - source channels
  - rrf score
  - rerank score
  - authority summary
  - freshness summary
  - match reasons

### 7-2. EvidenceItem 계약

- `EvidenceItem`은 section generator가 직접 사용할 수 있는 형태여야 한다.
- 최소 포함 정보
  - evidence id
  - evidence type
  - title
  - summary
  - snippet
  - citation label
  - metadata
  - relevance score

### 7-3. SectionDraft 계약

- 향후 `SectionDraft`에는 다음을 고려한다.
  - `citations`
  - `open_issues`
  - `confidence_note`
  - `support_status`

## 8. 환경과 인프라 계획

### 8-1. LLM

- 이미 문서 생성에는 Gemini가 붙어 있다.
- 다음 단계에서는 구조화와 rerank에도 Gemini를 사용한다.
- 환경변수 예시
  - `GEMINI_API_KEY`
  - `GEMINI_MODEL_NAME`

### 8-2. Embedding / Vector

- 현재 `backend/storage/vector.py`는 pseudo-vector다.
- 향후 선택지
  - Gemini embedding
  - OpenAI embedding
  - 로컬 embedding model
- 저장소 선택지
  - in-memory 유지
  - pgvector
  - dedicated vector DB

### 8-3. Text Search

- 현재 token overlap search는 교체 대상이다.
- 향후 선택지
  - OpenSearch
  - PostgreSQL FTS
  - Tantivy 계열

### 8-4. Graph

- 현재 abstraction은 유지
- 1차는 in-memory graph store 유지 가능
- 중장기 선택지
  - Neo4j
  - Memgraph
  - relation-aware document store

## 9. 권장 파일 수정 목록

### 반드시 수정될 가능성이 높은 파일

- `backend/search/structuring.py`
- `backend/search/routing.py`
- `backend/search/retrieval.py`
- `backend/search/evaluation.py`
- `backend/documents/evidence.py`
- `backend/documents/planning.py`
- `backend/documents/gemini.py`
- `backend/documents/service.py`
- `backend/schemas/related_articles.py`
- `backend/schemas/documents.py`
- `backend/ingestion/mock_data.py`
- `backend/main.py`

### 새로 생길 가능성이 높은 파일

- `backend/search/gemini.py`
- `backend/search/query_rewrite.py`
- `backend/search/reranker.py`
- `backend/search/ontology.py`
- `backend/documents/grounding.py`
- `backend/documents/safety.py`

## 10. 단계별 구현 로드맵

### Phase 1. 구조화 계층 실전화

- Gemini 기반 `StructuredCase` 생성기 추가
- heuristic fallback 유지
- clarification loop 정리
- `search_synonyms`의 query-side 사용 추가

#### 완료 기준

- 동일 질의에서 heuristic보다 더 안정적으로 `actors/actions/objects`가 채워진다.
- 정보 부족 시 clarification 질문이 더 일관적으로 생성된다.

### Phase 2. Hybrid Retrieval 고도화

- BM25/FTS 검색 추가
- real embedding vector retrieval 추가
- graph expansion 가중치 개선
- multi-query retrieval 추가

#### 완료 기준

- `disciplinary` gold set에서 recall@k가 현재 baseline보다 개선된다.
- graph, text, vector 중 하나가 실패해도 전체 retrieval가 무너지지 않는다.

### Phase 3. Retrieval Evaluator 재설계

- hard filter와 rerank 분리
- reason trace 추가
- 최신성/권위 검사를 명시화

#### 완료 기준

- 최종 결과가 왜 채택되었는지 debug에서 설명 가능하다.
- 시행시점 위반 조문이 최종 후보에 남지 않는다.

### Phase 4. 문서 생성 grounding 강화

- evidence pack를 retrieval 중심으로 재정리
- Gemini section output에 근거 사용 결과 포함
- section별 evidence 검증 추가

#### 완료 기준

- 각 section이 어떤 evidence를 사용했는지 backend가 구조적으로 검증할 수 있다.
- hardcoded law/regulation dependency가 제거되거나 demo-only로 분리된다.

### Phase 5. Draft Evaluator / Safety 강화

- unsupported claim 탐지
- selective regeneration
- review package 강화

#### 완료 기준

- citation 없는 핵심 단락이 evaluator에서 명확히 감지된다.
- 최종 응답에 누락 정보와 근거 리포트가 안정적으로 포함된다.

### Phase 6. Case Workflow 통합

- `/api/cases` 생성과 RAG/generation 연결
- 질문 답변 후 re-structuring, re-retrieval, re-generation 연결
- versionHistory, timeline 자동 갱신

#### 완료 기준

- 사건 질문 답변 전후로 문서 근거와 초안이 실제로 바뀐다.
- 상태 전이가 seed hydration이 아니라 실제 pipeline 결과 기반으로 반영된다.

### Phase 7. 평가와 운영성 확보

- retrieval gold set 관리
- generation gold set 관리
- quality gate 정리
- logging, caching, failure fallback 정리

#### 완료 기준

- retrieval/generation/safety에 대한 품질 게이트가 문서화되고 자동 테스트에 포함된다.

## 11. 평가 지표

### 관련 조항 찾기

- structuring slot fill accuracy
- clarify rate
- recall@k
- precision@k
- MRR
- NDCG
- freshness violation rate
- authority mismatch rate

### 문서 생성

- citation coverage
- citation correctness
- unsupported claim rate
- missing section rate
- term consistency
- date/entity consistency
- human review required ratio

## 12. 이번 단계에서 제외해도 되는 것

- 모든 사건 유형에 대한 동시 확장
- 외부 GraphDB 즉시 도입
- 대규모 판례 corpus 동시 수집
- 인증/권한
- 멀티테넌시
- 대용량 장기 저장소 설계

## 13. 결론

- 현재 backend는 RAG와 문서 생성의 skeleton은 이미 갖고 있다.
- 그러나 핵심 단계가 아직 heuristic이므로, 실제 법률 시스템 수준으로 가려면 구조화, retrieval, rerank, grounding을 차례대로 강화해야 한다.
- 가장 중요한 개선은 "검색을 더 많이 하는 것"이 아니라 "입력을 더 잘 구조화하고, 최종 근거를 더 엄밀히 검증하는 것"이다.
- 문서 생성은 이미 Gemini 기반으로 진입했으므로, 다음 우선순위는 관련 조항 찾기 서비스의 구조화와 rerank를 LLM + hybrid retrieval 체계로 끌어올리는 것이다.
