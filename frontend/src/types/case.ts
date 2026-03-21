import type { CaseStatus, CaseType, PriorityLevel } from './common';
import type { DocumentRecord } from './document';
import type { QuestionRecord } from './question';

export interface TimelineEvent {
  id: string;
  type:
    | 'case_created'
    | 'document_generated'
    | 'question_requested'
    | 'question_answered'
    | 'document_completed'
    | 'status_updated';
  title: string;
  description: string;
  occurredAt: string;
  actor: string;
  relatedDocumentId?: string;
  relatedQuestionId?: string;
}

export interface CaseSummary {
  id: string;
  title: string;
  caseType: CaseType;
  status: CaseStatus;
  occurredAt: string;
  location: string;
  author: string;
  relatedPersons: string[];
  summary: string;
  details: string;
  priority: PriorityLevel;
  createdAt: string;
  updatedAt: string;
  progressPercent: number;
  activeQuestionCount: number;
  documentCount: number;
}

export interface CaseDetail extends CaseSummary {
  attachmentProvided: boolean;
  legalReviewSummary: string;
  urgencyNote: string;
  timeline: TimelineEvent[];
  documents: DocumentRecord[];
  questions: QuestionRecord[];
}

export interface CaseCreatePayload {
  title: string;
  caseType: CaseType;
  occurredAt: string;
  location: string;
  author: string;
  relatedPersons: string[];
  summary: string;
  details: string;
  attachmentProvided: boolean;
  priority: PriorityLevel;
}
