import { apiClient } from './apiClient';
import type { CaseCreatePayload, CaseDetail, CaseSummary } from '../types/case';
import type { DashboardMetrics } from '../types/common';

export const caseService = {
  getCases: () => apiClient.get<CaseSummary[]>('/cases'),
  getCaseMetrics: () => apiClient.get<DashboardMetrics>('/cases/metrics'),
  getCaseById: (caseId: string) => apiClient.get<CaseDetail>(`/cases/${caseId}`),
  createCase: (payload: CaseCreatePayload) => apiClient.post<CaseDetail>('/cases', payload),
};
