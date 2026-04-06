import rawCases from '../mocks/cases.json';
import rawCaseDetails from '../mocks/case-detail.json';
import rawDocuments from '../mocks/documents.json';
import rawQuestions from '../mocks/questions.json';
import rawLegalBasis from '../mocks/legal-basis.json';
import { buildWorkflowStages, calculateMetrics, calculateProgressByDocuments } from '../utils/progress';
import { DISCIPLINARY_DOCUMENT_CATALOG } from '../utils/documentCatalog';
import type { CaseCreatePayload, CaseDetail, CaseSummary, TimelineEvent, WorkflowStageId } from '../types/case';
import type { CaseStatus, DashboardMetrics, DocumentStatus } from '../types/common';
import type { DocumentDetail, DocumentRecord } from '../types/document';
import type { LegalBasisEntry } from '../types/legalBasis';
import type { QuestionRecord } from '../types/question';

type LegacyTimelineEventType =
  | 'case_created'
  | 'document_generated'
  | 'question_requested'
  | 'question_answered'
  | 'document_completed'
  | 'status_updated';

type SeedTimelineEvent = Omit<TimelineEvent, 'stageId' | 'type'> & {
  stageId?: WorkflowStageId;
  type: TimelineEvent['type'] | LegacyTimelineEventType;
};

type SeedCaseDetail = Omit<CaseDetail, 'attachmentSummary' | 'documents' | 'questions' | 'timeline' | 'workflowStages'> & {
  attachmentSummary?: string;
  timeline: SeedTimelineEvent[];
  documents: unknown[];
  questions: unknown[];
};

interface MockDatabase {
  cases: CaseSummary[];
  caseDetails: SeedCaseDetail[];
  documents: DocumentRecord[];
  questions: QuestionRecord[];
  legalBasis: LegalBasisEntry[];
}

const seedDatabase: MockDatabase = {
  cases: rawCases as CaseSummary[],
  caseDetails: rawCaseDetails as SeedCaseDetail[],
  documents: rawDocuments as DocumentRecord[],
  questions: rawQuestions as QuestionRecord[],
  legalBasis: rawLegalBasis as LegalBasisEntry[],
};

let database = clone(seedDatabase);

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const LEGACY_TIMELINE_TYPE_MAP: Record<
  LegacyTimelineEventType,
  { type: TimelineEvent['type']; stageId: WorkflowStageId }
> = {
  case_created: {
    type: 'case_registered',
    stageId: 'case_registration',
  },
  document_generated: {
    type: 'document_generated',
    stageId: 'document_generation',
  },
  question_requested: {
    type: 'information_requested',
    stageId: 'information_request',
  },
  question_answered: {
    type: 'information_received',
    stageId: 'information_request',
  },
  document_completed: {
    type: 'document_completed',
    stageId: 'document_generation',
  },
  status_updated: {
    type: 'review_completed',
    stageId: 'review_feedback',
  },
};

const TIMELINE_STAGE_MAP: Record<TimelineEvent['type'], WorkflowStageId> = {
  case_registered: 'case_registration',
  attachment_registered: 'attachment_registration',
  attachment_skipped: 'attachment_registration',
  information_requested: 'information_request',
  information_received: 'information_request',
  document_generated: 'document_generation',
  document_completed: 'document_generation',
  review_requested: 'review_feedback',
  review_completed: 'review_feedback',
};

function simulate<T>(factory: () => T) {
  const delay = 280 + Math.floor(Math.random() * 360);
  return new Promise<T>((resolve, reject) => {
    window.setTimeout(() => {
      try {
        resolve(clone(factory()));
      } catch (error) {
        reject(error);
      }
    }, delay);
  });
}

function ensureCase(caseId: string) {
  const summary = database.cases.find((item) => item.id === caseId);
  const detail = database.caseDetails.find((item) => item.id === caseId);

  if (!summary || !detail) {
    throw new Error('사건 정보를 찾을 수 없습니다.');
  }

  return { summary, detail };
}

function ensureQuestion(questionId: string) {
  const question = database.questions.find((item) => item.id === questionId);

  if (!question) {
    throw new Error('질문 정보를 찾을 수 없습니다.');
  }

  return question;
}

function getDocumentsForCase(caseId: string) {
  return database.documents
    .filter((item) => item.caseId === caseId)
    .sort((left, right) => left.order - right.order);
}

function getQuestionsForCase(caseId: string) {
  return database.questions
    .filter((item) => item.caseId === caseId)
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt));
}

function getDocumentStatusProgress(documents: DocumentRecord[]) {
  return calculateProgressByDocuments(documents.map((document) => document.status));
}

function getAttachmentSummary(detail: Pick<SeedCaseDetail, 'attachmentProvided' | 'attachmentSummary'>) {
  if (!detail.attachmentProvided) {
    return '';
  }

  return detail.attachmentSummary?.trim() || '첨부 자료가 등록되어 문서 생성과 검토 단계의 기준 자료로 연결되었습니다.';
}

function normalizeTimelineEvent(event: SeedTimelineEvent): TimelineEvent {
  if (event.stageId) {
    return event as TimelineEvent;
  }

  const normalized = LEGACY_TIMELINE_TYPE_MAP[event.type as LegacyTimelineEventType];

  if (!normalized) {
    const type = event.type as TimelineEvent['type'];

    return {
      ...event,
      type,
      stageId: TIMELINE_STAGE_MAP[type],
    };
  }

  return {
    ...event,
    type: normalized.type,
    stageId: normalized.stageId,
  };
}

function buildAttachmentTimelineEvent(detail: Pick<SeedCaseDetail, 'id' | 'createdAt' | 'author' | 'attachmentProvided' | 'attachmentSummary'>): TimelineEvent {
  return {
    id: `${detail.id}-timeline-attachment`,
    stageId: 'attachment_registration',
    type: detail.attachmentProvided ? 'attachment_registered' : 'attachment_skipped',
    title: detail.attachmentProvided ? '첨부 자료 등록' : '첨부 자료 생략',
    description: detail.attachmentProvided
      ? getAttachmentSummary(detail)
      : '첨부 자료 없이 다음 단계로 진행하도록 설정했습니다.',
    occurredAt: detail.createdAt,
    actor: detail.author,
  };
}

function normalizeTimeline(
  detail: Pick<SeedCaseDetail, 'id' | 'createdAt' | 'updatedAt' | 'author' | 'attachmentProvided' | 'attachmentSummary' | 'timeline'>,
  documents: DocumentRecord[],
) {
  const events = detail.timeline.map(normalizeTimelineEvent);

  if (!events.some((item) => item.stageId === 'attachment_registration')) {
    events.push(buildAttachmentTimelineEvent(detail));
  }

  if (
    documents.length > 0 &&
    documents.every((document) => document.status === 'completed') &&
    !events.some((item) => item.stageId === 'review_feedback')
  ) {
    events.push({
      id: `${detail.id}-timeline-review`,
      stageId: 'review_feedback',
      type: 'review_completed',
      title: '문서 검토 완료',
      description: '최종 문서 검토가 끝나 사건 패키지가 완료 상태로 정리되었습니다.',
      occurredAt: detail.updatedAt,
      actor: 'MILO 시스템',
    });
  }

  return events.sort((left, right) => Date.parse(right.occurredAt) - Date.parse(left.occurredAt));
}

function deriveCaseStatus(progressPercent: number, documents: DocumentRecord[], questions: QuestionRecord[]): CaseStatus {
  const hasDocuments = documents.length > 0;
  const allCompleted = hasDocuments && documents.every((document) => document.status === 'completed');
  const openQuestions = questions.filter((question) => question.status === 'open').length;
  const openReviews = documents.flatMap((document) => document.reviewHistory).filter((item) => item.status === 'open')
    .length;

  if (allCompleted && openReviews === 0) {
    return 'completed';
  }

  if (openQuestions > 0) {
    return 'waiting_for_input';
  }

  if (progressPercent <= 24) {
    return 'draft';
  }

  return 'in_progress';
}

function syncCaseSummary(caseId: string) {
  const { summary, detail } = ensureCase(caseId);
  const documents = getDocumentsForCase(caseId);
  const questions = getQuestionsForCase(caseId);
  const progressPercent = getDocumentStatusProgress(documents);
  const openQuestionCount = questions.filter((question) => question.status === 'open').length;
  const openReviewCount = documents.flatMap((document) => document.reviewHistory).filter((item) => item.status === 'open')
    .length;
  const now = new Date().toISOString();

  summary.progressPercent = progressPercent;
  summary.activeQuestionCount = openQuestionCount;
  summary.openReviewCount = openReviewCount;
  summary.documentCount = documents.length;
  summary.status = deriveCaseStatus(progressPercent, documents, questions);
  summary.updatedAt = now;

  detail.status = summary.status;
  detail.progressPercent = progressPercent;
  detail.activeQuestionCount = openQuestionCount;
  detail.openReviewCount = openReviewCount;
  detail.documentCount = documents.length;
  detail.updatedAt = now;
}

function hydrateCaseDetail(caseId: string): CaseDetail {
  const { summary, detail } = ensureCase(caseId);
  const documents = getDocumentsForCase(caseId);
  const questions = getQuestionsForCase(caseId);
  const hydratedDetail: CaseDetail = {
    ...detail,
    ...summary,
    attachmentProvided: detail.attachmentProvided,
    attachmentSummary: getAttachmentSummary(detail),
    legalReviewSummary: detail.legalReviewSummary,
    urgencyNote: detail.urgencyNote,
    workflowStages: [],
    timeline: normalizeTimeline(detail, documents),
    documents,
    questions,
  };

  hydratedDetail.workflowStages = buildWorkflowStages(hydratedDetail);

  return hydratedDetail;
}

function buildDocumentDetail(caseId: string, documentId: string): DocumentDetail {
  const document = getDocumentsForCase(caseId).find((item) => item.id === documentId);

  if (!document) {
    throw new Error('문서 정보를 찾을 수 없습니다.');
  }

  const documents = getDocumentsForCase(caseId);
  const index = documents.findIndex((item) => item.id === documentId);

  return {
    ...document,
    legalBasis: database.legalBasis.filter((item) => document.legalBasisIds.includes(item.id)),
    questions: getQuestionsForCase(caseId).filter((item) => item.documentId === documentId),
    previousDocumentId: index > 0 ? documents[index - 1].id : undefined,
    nextDocumentId: index < documents.length - 1 ? documents[index + 1].id : undefined,
  };
}

function buildDocumentTemplates(payload: CaseCreatePayload, caseId: string) {
  const createdAt = new Date().toISOString();
  const templates = DISCIPLINARY_DOCUMENT_CATALOG.map((item) => {
    switch (item.type) {
      case 'fact_finding_report':
        return {
          ...item,
          status: 'completed' as DocumentStatus,
          description: '확인된 사실관계와 1차 조사 의견을 정리한 문서입니다.',
          content: `1. 조사 개요\n${payload.summary}\n\n2. 확인된 사실\n${payload.details}\n\n3. 조사 의견\n작성자 ${payload.author}가 입력한 사실관계를 기준으로 사실관계 정리를 완료했고, 이후 문서는 본 보고서를 기준으로 이어집니다.`,
          legalBasisIds: ['lb-003', 'lb-005'],
        };
      case 'attendance_notice':
        return {
          ...item,
          status: 'completed' as DocumentStatus,
          description: '위원회 출석 일정과 소명 기회를 안내하는 통지서입니다.',
          content: `1. 통지 대상\n${payload.relatedPersons.join(', ')}\n\n2. 통지 내용\n${payload.title} 사건과 관련해 위원회 출석 및 의견 제출 필요 사항을 통지합니다.\n\n3. 비고\n발생 장소는 ${payload.location}이며, 첨부 자료는 ${payload.attachmentProvided ? '등록 완료' : '미등록'} 상태입니다.`,
          legalBasisIds: ['lb-004'],
        };
      case 'committee_reference':
        return {
          ...item,
          status: 'generating' as DocumentStatus,
          description: '위원회가 사실관계와 쟁점을 빠르게 파악할 수 있도록 정리한 참고 자료입니다.',
          content: `1. 핵심 사실\n${payload.summary}\n\n2. 심의 포인트\n우선순위는 ${payload.priority}이며, 사건 상세 사실관계를 바탕으로 징계 판단 요소를 정리 중입니다.\n\n3. 현재 상태\n추가 보완 없이 위원회 상정이 가능한지 검토하면서 초안을 작성 중입니다.`,
          legalBasisIds: ['lb-003', 'lb-005'],
        };
      default:
        return {
          ...item,
          status: 'pending' as DocumentStatus,
          description: '위원회 의결 결과와 처분 방향을 반영하는 최종 문서입니다.',
          content:
            '1. 문서 목적\n위원회 의결 결과와 최종 처분 내용을 기록합니다.\n\n2. 현재 상태\n사실결과조사보고와 위원회 참고 자료가 정리된 이후 최종 문안이 확정됩니다.',
          legalBasisIds: ['lb-003', 'lb-004', 'lb-005'],
        };
    }
  });

  return templates.map((template, index) => ({
    id: `${caseId}-doc-${index + 1}`,
    caseId,
    title: template.title,
    type: template.type,
    order: template.order,
    status: template.status,
    description: template.description,
    content: template.content,
    legalBasisIds: template.legalBasisIds,
    versionHistory: [
      {
        version: template.status === 'completed' ? 'v1.0' : 'v0.1',
        updatedAt: createdAt,
        note:
          template.status === 'completed'
            ? '사건 등록 직후 필수 문서 초안이 완성되었습니다.'
            : '사건 등록 직후 기본 초안이 생성되었습니다.',
      },
    ],
    reviewHistory: [],
    updatedAt: createdAt,
  }));
}

function appendTimelineEvent(caseId: string, event: TimelineEvent) {
  const { detail } = ensureCase(caseId);
  detail.timeline.unshift(event);
}

export const mockApi = {
  reset() {
    database = clone(seedDatabase);
  },

  async getCases() {
    return simulate(() =>
      [...database.cases].sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt)),
    );
  },

  async getCaseMetrics(): Promise<DashboardMetrics> {
    return simulate(() => calculateMetrics(database.cases));
  },

  async getCaseById(caseId: string) {
    return simulate(() => hydrateCaseDetail(caseId));
  },

  async createCase(payload: CaseCreatePayload) {
    return simulate(() => {
      const now = new Date().toISOString();
      const caseId = `case-${Math.random().toString(36).slice(2, 10)}`;
      const documents = buildDocumentTemplates(payload, caseId);
      const progressPercent = getDocumentStatusProgress(documents);

      const summary: CaseSummary = {
        id: caseId,
        title: payload.title,
        caseType: payload.caseType,
        status: deriveCaseStatus(progressPercent, documents, []),
        occurredAt: payload.occurredAt,
        location: payload.location,
        author: payload.author,
        relatedPersons: payload.relatedPersons,
        summary: payload.summary,
        details: payload.details,
        priority: payload.priority,
        createdAt: now,
        updatedAt: now,
        progressPercent,
        activeQuestionCount: 0,
        openReviewCount: 0,
        documentCount: documents.length,
      };

      const detail: SeedCaseDetail = {
        ...summary,
        attachmentProvided: payload.attachmentProvided,
        attachmentSummary: payload.attachmentSummary,
        legalReviewSummary:
          '사건 등록 직후 생성된 기본 검토 메모입니다. 문서 초안이 보완되면 적용 조항과 위험 포인트가 자동으로 정리됩니다.',
        urgencyNote: '현재는 초기 등록 단계이며, 추가 입력이나 후속 자료가 들어오면 상태가 갱신됩니다.',
        timeline: [
          {
            id: `${caseId}-timeline-003`,
            stageId: 'document_generation',
            type: 'document_generated',
            title: '기본 문서 패키지 생성',
            description: `${documents.length}개의 기본 문서가 사건 유형에 맞춰 생성되었습니다.`,
            occurredAt: now,
            actor: 'MILO 시스템',
          },
          {
            id: `${caseId}-timeline-002`,
            stageId: 'attachment_registration',
            type: payload.attachmentProvided ? 'attachment_registered' : 'attachment_skipped',
            title: payload.attachmentProvided ? '첨부 자료 등록' : '첨부 자료 생략',
            description: payload.attachmentProvided
              ? payload.attachmentSummary || '첨부 자료가 등록되어 문서 생성 기준 자료로 연결되었습니다.'
              : '첨부 자료 없이 다음 단계로 넘어가도록 설정했습니다.',
            occurredAt: now,
            actor: payload.author,
          },
          {
            id: `${caseId}-timeline-001`,
            stageId: 'case_registration',
            type: 'case_registered',
            title: '사건 등록',
            description: `${payload.title} 사건이 신규 등록되었습니다.`,
            occurredAt: now,
            actor: payload.author,
          },
        ],
        documents: [],
        questions: [],
      };

      database.cases.unshift(summary);
      database.caseDetails.unshift(detail);
      database.documents.push(...documents);

      return hydrateCaseDetail(caseId);
    });
  },

  async getDocumentsByCaseId(caseId: string) {
    return simulate(() => getDocumentsForCase(caseId));
  },

  async getDocumentById(caseId: string, documentId: string): Promise<DocumentDetail> {
    return simulate(() => buildDocumentDetail(caseId, documentId));
  },

  async submitDocumentReview(caseId: string, documentId: string, title: string, description: string) {
    return simulate(() => {
      const document = getDocumentsForCase(caseId).find((item) => item.id === documentId);

      if (!document) {
        throw new Error('문서 정보를 찾을 수 없습니다.');
      }

      const now = new Date().toISOString();

      document.reviewHistory.unshift({
        id: `${document.id}-review-${Date.now()}`,
        title: title.trim(),
        description: description.trim(),
        createdAt: now,
        status: 'open',
      });
      document.status = document.status === 'needs_input' ? 'needs_input' : 'generating';
      document.updatedAt = now;

      appendTimelineEvent(caseId, {
        id: `${caseId}-timeline-${Date.now()}`,
        stageId: 'review_feedback',
        type: 'review_requested',
        title: '문서 피드백 등록',
        description: `${document.title} 문서에 대한 사용자 피드백이 등록되었습니다.`,
        occurredAt: now,
        actor: '사용자',
        relatedDocumentId: documentId,
      });

      syncCaseSummary(caseId);

      return buildDocumentDetail(caseId, documentId);
    });
  },

  async resolveDocumentReview(caseId: string, documentId: string, reviewId: string) {
    return simulate(() => {
      const document = getDocumentsForCase(caseId).find((item) => item.id === documentId);

      if (!document) {
        throw new Error('문서 정보를 찾을 수 없습니다.');
      }

      const review = document.reviewHistory.find((item) => item.id === reviewId);

      if (!review) {
        throw new Error('피드백 정보를 찾을 수 없습니다.');
      }

      if (review.status === 'resolved') {
        throw new Error('이미 반영 완료된 피드백입니다.');
      }

      const now = new Date().toISOString();

      review.status = 'resolved';
      const hasRemainingOpenReviews = document.reviewHistory.some((item) => item.id !== reviewId && item.status === 'open');
      const hasOpenQuestions = getQuestionsForCase(caseId).some(
        (item) => item.documentId === documentId && item.status === 'open',
      );

      document.status = hasOpenQuestions ? 'needs_input' : hasRemainingOpenReviews ? 'generating' : 'completed';
      document.updatedAt = now;
      document.versionHistory.unshift({
        version: `v${document.versionHistory.length + 1}.0`,
        updatedAt: now,
        note: `${review.title} 피드백을 반영해 문서를 수정했습니다.`,
      });

      appendTimelineEvent(caseId, {
        id: `${caseId}-timeline-${Date.now()}`,
        stageId: 'review_feedback',
        type: 'review_completed',
        title: '문서 피드백 반영 완료',
        description: `${document.title} 문서에 대한 사용자 피드백이 반영되었습니다.`,
        occurredAt: now,
        actor: '문서 생성 엔진',
        relatedDocumentId: documentId,
      });

      syncCaseSummary(caseId);

      return buildDocumentDetail(caseId, documentId);
    });
  },

  async getQuestionsByCaseId(caseId: string) {
    return simulate(() => getQuestionsForCase(caseId));
  },

  async getOpenQuestions(caseId: string) {
    return simulate(() => getQuestionsForCase(caseId).filter((item) => item.status === 'open'));
  },

  async submitQuestionAnswer(questionId: string, answer: string) {
    return simulate(() => {
      const question = ensureQuestion(questionId);
      const now = new Date().toISOString();

      question.status = 'answered';
      question.answer = answer;
      question.answeredAt = now;

      const document = database.documents.find((item) => item.id === question.documentId);

      if (document) {
        const nextStatus: DocumentStatus =
          document.status === 'needs_input' ? 'generating' : document.status;

        document.status = nextStatus;
        document.updatedAt = now;
        document.versionHistory.unshift({
          version: `v${document.versionHistory.length + 1}.0`,
          updatedAt: now,
          note: '추가 질문 답변이 반영되어 초안이 갱신되었습니다.',
        });
        document.reviewHistory.unshift({
          id: `${document.id}-review-${Date.now()}`,
          title: '질문 답변 반영',
          description: '사용자 입력을 반영해 문서 상태를 갱신했습니다.',
          createdAt: now,
          status: 'resolved',
        });
      }

      appendTimelineEvent(question.caseId, {
        id: `${question.caseId}-timeline-${Date.now()}`,
        stageId: 'information_request',
        type: 'information_received',
        title: '추가 질문 답변 반영',
        description: `${question.title}에 대한 답변이 제출되어 문서 초안이 갱신되었습니다.`,
        occurredAt: now,
        actor: '사용자',
        relatedQuestionId: question.id,
        relatedDocumentId: question.documentId,
      });

      syncCaseSummary(question.caseId);

      return hydrateCaseDetail(question.caseId);
    });
  },

  async getLegalBasisByIds(ids: string[]) {
    return simulate(() => database.legalBasis.filter((item) => ids.includes(item.id)));
  },
};
