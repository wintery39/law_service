import type { CaseDetail, CaseSummary, WorkflowStage, WorkflowStageId } from '../types/case';
import type { DashboardMetrics, DocumentStatus } from '../types/common';

const DOCUMENT_STATUS_SCORE: Record<DocumentStatus, number> = {
  pending: 18,
  generating: 58,
  needs_input: 46,
  completed: 100,
};

export const WORKFLOW_STAGE_META: Record<
  WorkflowStageId,
  Pick<WorkflowStage, 'title' | 'caption' | 'description'>
> = {
  case_registration: {
    title: '새 사건 등록',
    caption: '1단계',
    description: '사건 기본 정보와 관련 사실관계를 등록합니다.',
  },
  attachment_registration: {
    title: '첨부 자료 등록',
    caption: '2단계',
    description: '필요한 첨부 자료를 등록하고, 없으면 이 단계를 건너뜁니다.',
  },
  information_request: {
    title: '필요한 정보 요청',
    caption: '3단계',
    description: 'LLM이 문서 작성을 위해 필요한 추가 정보를 요청합니다.',
  },
  document_generation: {
    title: '문서 생성',
    caption: '4단계',
    description: '최종적으로 필요한 문서 초안과 패키지를 생성합니다.',
  },
  review_feedback: {
    title: '문서 검토 및 유저 피드백',
    caption: '5단계',
    description: '생성된 문서를 검토하고 사용자 피드백을 반영해 재검토합니다.',
  },
};

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

export function buildWorkflowStages(caseDetail: CaseDetail): WorkflowStage[] {
  const documentsCompleted =
    caseDetail.documents.length > 0 && caseDetail.documents.every((document) => document.status === 'completed');
  const openQuestions = caseDetail.questions.filter((question) => question.status === 'open');
  const answeredQuestions = caseDetail.questions.filter((question) => question.status === 'answered');
  const documentsNeedingInput = caseDetail.documents.filter((document) => document.status === 'needs_input').length;
  const generatingDocuments = caseDetail.documents.filter((document) => document.status === 'generating').length;
  const pendingDocuments = caseDetail.documents.filter((document) => document.status === 'pending').length;
  const reviewItems = caseDetail.documents.flatMap((document) => document.reviewHistory);
  const openReviews = reviewItems.filter((item) => item.status === 'open').length;
  const resolvedReviews = reviewItems.filter((item) => item.status === 'resolved').length;
  const hasReviewHistory = reviewItems.length > 0;

  return [
    {
      id: 'case_registration',
      ...WORKFLOW_STAGE_META.case_registration,
      detail: `${caseDetail.author} 작성자가 사건을 등록하고 발생 시점, 관련자, 사실관계를 입력했습니다.`,
      status: 'completed',
    },
    {
      id: 'attachment_registration',
      ...WORKFLOW_STAGE_META.attachment_registration,
      detail: caseDetail.attachmentProvided
        ? caseDetail.attachmentSummary || '첨부 자료가 등록되어 이후 문서 생성에 활용됩니다.'
        : '첨부 자료 없이 진행하기로 선택해 이 단계를 건너뛰었습니다.',
      status: caseDetail.attachmentProvided ? 'completed' : 'skipped',
    },
    {
      id: 'information_request',
      ...WORKFLOW_STAGE_META.information_request,
      detail:
        openQuestions.length > 0
          ? `${openQuestions.length}건의 추가 정보 요청이 열려 있으며, ${
              documentsNeedingInput > 0 ? `${documentsNeedingInput}개 문서가 답변을 기다리고 있습니다.` : '관련 문서가 답변을 기다리고 있습니다.'
            }`
          : answeredQuestions.length > 0
            ? `${answeredQuestions.length}건의 요청 정보가 반영되어 문서 작성이 다시 진행 중입니다.`
            : '현재까지 추가 정보 요청 없이 문서 생성이 진행되고 있습니다.',
      status:
        openQuestions.length > 0 || documentsNeedingInput > 0
          ? 'active'
          : answeredQuestions.length > 0
            ? 'completed'
            : 'skipped',
    },
    {
      id: 'document_generation',
      ...WORKFLOW_STAGE_META.document_generation,
      detail: documentsCompleted
        ? `${caseDetail.documents.length}개의 문서가 모두 생성 완료되었습니다.`
        : `${caseDetail.documents.length}개 문서 중 ${generatingDocuments}개 작성 중, ${pendingDocuments}개 대기, ${documentsNeedingInput}개 추가 정보 필요 상태입니다.`,
      status: documentsCompleted
        ? 'completed'
        : caseDetail.documents.length === 0 || openQuestions.length > 0 || documentsNeedingInput > 0
          ? 'pending'
          : 'active',
    },
    {
      id: 'review_feedback',
      ...WORKFLOW_STAGE_META.review_feedback,
      detail: !documentsCompleted
        ? '문서 생성이 완료되면 검토와 피드백 반영 단계로 넘어갑니다.'
        : openReviews > 0
          ? `${openReviews}건의 검토 요청이 열려 있으며, 사용자 피드백 반영이 필요합니다.`
          : hasReviewHistory
            ? `${resolvedReviews}건의 검토 이력이 정리되었고 현재 열린 피드백은 없습니다.`
            : '검토 요청 없이 문서 패키지가 마무리되었습니다.',
      status: !documentsCompleted ? 'pending' : openReviews > 0 ? 'active' : 'completed',
    },
  ];
}
