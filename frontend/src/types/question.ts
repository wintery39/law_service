import type { QuestionStatus } from './common';

export interface QuestionRecord {
  id: string;
  caseId: string;
  documentId: string;
  title: string;
  prompt: string;
  reason: string;
  status: QuestionStatus;
  answer: string | null;
  createdAt: string;
  answeredAt: string | null;
  guidance: string;
}
