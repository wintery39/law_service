import { apiClient } from './apiClient';
import type { CaseDetail } from '../types/case';
import type { QuestionRecord } from '../types/question';

export const questionService = {
  getQuestionsByCaseId: (caseId: string) => apiClient.get<QuestionRecord[]>(`/cases/${caseId}/questions`),
  getOpenQuestions: (caseId: string) => apiClient.get<QuestionRecord[]>(`/cases/${caseId}/questions/open`),
  submitQuestionAnswer: (questionId: string, answer: string) =>
    apiClient.post<CaseDetail>(`/questions/${questionId}/answer`, { answer }),
};
