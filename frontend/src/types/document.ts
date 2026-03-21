import type { DocumentStatus } from './common';
import type { LegalBasisEntry } from './legalBasis';
import type { QuestionRecord } from './question';

export interface DocumentVersion {
  version: string;
  updatedAt: string;
  note: string;
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
  legalBasisIds: string[];
  versionHistory: DocumentVersion[];
  reviewHistory: DocumentReviewHistory[];
  updatedAt: string;
}

export interface DocumentDetail extends DocumentRecord {
  legalBasis: LegalBasisEntry[];
  questions: QuestionRecord[];
  previousDocumentId?: string;
  nextDocumentId?: string;
}
