import { apiClient } from './apiClient';
import type { DocumentDetail, DocumentRecord } from '../types/document';

export const documentService = {
  getDocumentsByCaseId: (caseId: string) => apiClient.get<DocumentRecord[]>(`/cases/${caseId}/documents`),
  getDocumentById: (caseId: string, documentId: string) =>
    apiClient.get<DocumentDetail>(`/cases/${caseId}/documents/${documentId}`),
};
