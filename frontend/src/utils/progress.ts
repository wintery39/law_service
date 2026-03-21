import type { CaseDetail } from '../types/case';
import type { DashboardMetrics, DocumentStatus } from '../types/common';
import type { CaseSummary } from '../types/case';

const DOCUMENT_STATUS_SCORE: Record<DocumentStatus, number> = {
  pending: 18,
  generating: 58,
  needs_input: 46,
  completed: 100,
};

export interface WorkflowStep {
  id: WorkflowStepId;
  title: string;
  caption: string;
  description: string;
  detail: string;
  completed: boolean;
  active: boolean;
}

export type WorkflowStepId = 'created' | 'facts' | 'documents' | 'question' | 'completed' | 'submitted';

export function calculateProgressByDocuments(statuses: DocumentStatus[]) {
  if (!statuses.length) {
    return 0;
  }

  const total = statuses.reduce((sum, status) => sum + DOCUMENT_STATUS_SCORE[status], 0);
  return Math.round(total / statuses.length);
}

export function calculateMetrics(cases: CaseSummary[]): DashboardMetrics {
  return {
    totalCases: cases.length,
    inProgressCases: cases.filter((item) => item.status === 'in_progress').length,
    completedCases: cases.filter((item) => item.status === 'completed').length,
    waitingCases: cases.filter((item) => item.status === 'waiting_for_input').length,
  };
}

export function buildWorkflowSteps(caseDetail: CaseDetail): WorkflowStep[] {
  const documentsCompleted = caseDetail.documents.every((document) => document.status === 'completed');
  const hasQuestions = caseDetail.questions.length > 0;
  const hasOpenQuestion = caseDetail.questions.some((question) => question.status === 'open');
  const hasGeneratedDocument = caseDetail.documents.some(
    (document) => document.status === 'completed' || document.status === 'generating',
  );
  const activeStepId: WorkflowStepId = hasOpenQuestion
    ? 'question'
    : documentsCompleted
      ? caseDetail.status === 'completed'
        ? 'submitted'
        : 'completed'
      : hasGeneratedDocument
        ? 'completed'
        : caseDetail.documents.length > 0
          ? 'documents'
          : 'facts';

  return [
    {
      id: 'created',
      title: '사건 등록',
      caption: '1단계',
      description: '기본 사건 식별 정보와 우선순위를 등록했습니다.',
      detail: `${caseDetail.author} 작성자가 사건을 등록하고 기초 메타데이터를 확정했습니다.`,
      completed: true,
      active: false,
    },
    {
      id: 'facts',
      title: '사실관계 입력',
      caption: '2단계',
      description: '사건 개요와 상세 사실관계를 입력해 문서 생성 기반을 마련합니다.',
      detail: caseDetail.details,
      completed: Boolean(caseDetail.details),
      active: activeStepId === 'facts',
    },
    {
      id: 'documents',
      title: '문서 목록 생성',
      caption: '3단계',
      description: '사건 유형에 맞는 필수 문서 패키지를 자동 구성했습니다.',
      detail: `${caseDetail.documents.length}개의 문서가 생성 흐름에 연결되어 있습니다.`,
      completed: caseDetail.documents.length > 0,
      active: activeStepId === 'documents',
    },
    {
      id: 'question',
      title: '추가 질문',
      caption: '4단계',
      description: '부족한 사실관계를 보완하기 위해 LLM이 추가 정보를 요청합니다.',
      detail: hasQuestions
        ? `${caseDetail.questions.length}건의 질문 기록이 있으며, 현재 ${
            hasOpenQuestion ? '응답 대기 중인 질문이 있습니다.' : '모든 질문이 처리되었습니다.'
          }`
        : '현재까지 추가 질문은 발생하지 않았습니다.',
      completed: hasQuestions && !hasOpenQuestion,
      active: activeStepId === 'question',
    },
    {
      id: 'completed',
      title: '문서 완성',
      caption: '5단계',
      description: '문서 초안이 보완되고 법률 근거가 연결됩니다.',
      detail: documentsCompleted
        ? '모든 문서가 완료 상태입니다.'
        : '일부 문서는 생성 중이거나 추가 정보 확인이 필요합니다.',
      completed: documentsCompleted,
      active: activeStepId === 'completed',
    },
    {
      id: 'submitted',
      title: '법무관 제출',
      caption: '6단계',
      description: '최종 검토가 끝난 문서 패키지를 보고 체계에 맞춰 제출합니다.',
      detail: documentsCompleted
        ? '제출 직전 상태입니다. 최종 결재 라인 확인만 남았습니다.'
        : '제출 전 필수 문서와 질문 응답 상태를 먼저 정리해야 합니다.',
      completed: caseDetail.status === 'completed',
      active: activeStepId === 'submitted',
    },
  ];
}
