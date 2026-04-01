import { apiClient } from './apiClient';
import type { DocumentDetail, DocumentRecord } from '../types/document';

export const documentService = {
  getDocumentsByCaseId: (caseId: string) => apiClient.get<DocumentRecord[]>(`/cases/${caseId}/documents`),
  getDocumentById: (caseId: string, documentId: string) =>
    apiClient.get<DocumentDetail>(`/cases/${caseId}/documents/${documentId}`),
  submitDocumentReview: (caseId: string, documentId: string, title: string, description: string) =>
    apiClient.post<DocumentDetail>(`/cases/${caseId}/documents/${documentId}/reviews`, { title, description }),
  resolveDocumentReview: (caseId: string, documentId: string, reviewId: string) =>
    apiClient.post<DocumentDetail>(`/cases/${caseId}/documents/${documentId}/reviews/${reviewId}/resolve`),
};
