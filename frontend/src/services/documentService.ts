import { mockApi } from './mockApi';

export const documentService = {
  getDocumentsByCaseId: (caseId: string) => mockApi.getDocumentsByCaseId(caseId),
  getDocumentById: (caseId: string, documentId: string) => mockApi.getDocumentById(caseId, documentId),
};
