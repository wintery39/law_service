# Review

## Resolved

1. 생성 실패 시 사용자 입력이 유실되던 문제를 수정했습니다.
   질문 답변과 문서 피드백은 이제 재생성 전에 먼저 저장됩니다. 생성이 실패해도 answer, review history, 타임라인 기록이 유지됩니다.

2. 질문 답변이 원문 문서 하나만 갱신하던 문제를 수정했습니다.
   질문이 달린 문서부터 이후 순서의 문서까지 함께 재생성해서, 상위 문서의 보완 정보가 후속 문서 change set에도 반영됩니다.

3. 피드백 기반 수정안을 적용해도 review가 열린 채 남던 문제를 수정했습니다.
   review feedback에서 만들어진 change set은 linked review id를 같이 저장하고, apply 시 해당 review를 자동으로 `resolved` 처리합니다.

## Verification

- `backend/.venv/bin/pytest backend/tests/test_frontend_case_management_api.py -q`
- `cd frontend && npm run build`
