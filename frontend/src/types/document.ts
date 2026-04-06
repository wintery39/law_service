import type { DocumentStatus } from './common';
import type { LegalBasisEntry } from './legalBasis';
import type { QuestionRecord } from './question';

export interface DocumentVersion {
  version: string;
  updatedAt: string;
  note: string;
}

export interface DocumentParagraph {
  id: string;
  text: string;
}

export interface DocumentSection {
  id: string;
  title: string;
  paragraphs: DocumentParagraph[];
}

export interface DocumentBody {
  sections: DocumentSection[];
  compiledText: string;
}

export type ChangeSetSource = 'initial_generation' | 'question_answer' | 'review_feedback';
export type ChangeSetStatus = 'pending' | 'applied' | 'rejected' | 'superseded';
export type PatchDecision = 'pending' | 'approved' | 'rejected';
export type PatchChangeType = 'add' | 'modify' | 'remove';

export interface DocumentPatch {
  id: string;
  sectionId: string;
  sectionTitle: string;
  originalSectionTitle?: string | null;
  sectionOrder?: number;
  paragraphId: string;
  changeType: PatchChangeType;
  originalText: string;
  proposedText: string;
  decision: PatchDecision;
}

export interface DocumentChangeSet {
  id: string;
  source: ChangeSetSource;
  title: string;
  description: string;
  createdAt: string;
  baseVersion: string;
  status: ChangeSetStatus;
  patches: DocumentPatch[];
  relatedReviewId?: string | null;
  relatedQuestionId?: string | null;
  appliedAt?: string | null;
}

export interface DocumentReviewHistory {
  id: string;
  title: string;
  description: string;
  createdAt: string;
  status: 'open' | 'resolved';
}

export interface DocumentRecord {
  id: string;
  caseId: string;
  title: string;
  type: string;
  order: number;
  status: DocumentStatus;
  description: string;
  content: string;
  approvedBody?: DocumentBody | null;
  activeChangeSet?: DocumentChangeSet | null;
  changeSetHistory?: DocumentChangeSet[];
  legalBasisIds: string[];
  versionHistory: DocumentVersion[];
  reviewHistory: DocumentReviewHistory[];
  updatedAt: string;
}

export interface DocumentDetail extends DocumentRecord {
  legalBasis: LegalBasisEntry[];
  questions: QuestionRecord[];
  changeSetHistorySummary?: DocumentChangeSet[];
  previousDocumentId?: string;
  nextDocumentId?: string;
}
