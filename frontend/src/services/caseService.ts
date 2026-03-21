import { mockApi } from './mockApi';
import type { CaseCreatePayload } from '../types/case';

export const caseService = {
  getCases: () => mockApi.getCases(),
  getCaseMetrics: () => mockApi.getCaseMetrics(),
  getCaseById: (caseId: string) => mockApi.getCaseById(caseId),
  createCase: (payload: CaseCreatePayload) => mockApi.createCase(payload),
};
