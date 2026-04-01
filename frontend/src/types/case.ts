import type { CaseStatus, CaseType, PriorityLevel } from './common';
import type { DocumentRecord } from './document';
import type { QuestionRecord } from './question';

export type WorkflowStageId =
  | 'case_registration'
  | 'attachment_registration'
  | 'information_request'
  | 'document_generation'
  | 'review_feedback';

export type WorkflowStageStatus = 'pending' | 'active' | 'completed' | 'skipped';

export type TimelineEventType =
  | 'case_registered'
  | 'attachment_registered'
  | 'attachment_skipped'
  | 'information_requested'
  | 'information_received'
  | 'document_generated'
  | 'document_completed'
  | 'review_requested'
  | 'review_completed';

export interface WorkflowStage {
  id: WorkflowStageId;
  title: string;
  caption: string;
  description: string;
  detail: string;
  status: WorkflowStageStatus;
}

export interface TimelineEvent {
  id: string;
  stageId: WorkflowStageId;
  type: TimelineEventType;
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
  openReviewCount: number;
  documentCount: number;
}

export interface CaseDetail extends CaseSummary {
  attachmentProvided: boolean;
  attachmentSummary: string;
  legalReviewSummary: string;
  urgencyNote: string;
  workflowStages: WorkflowStage[];
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
  attachmentSummary: string;
  priority: PriorityLevel;
}
