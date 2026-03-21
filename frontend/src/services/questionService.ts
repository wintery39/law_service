import { mockApi } from './mockApi';

export const questionService = {
  getQuestionsByCaseId: (caseId: string) => mockApi.getQuestionsByCaseId(caseId),
  getOpenQuestions: (caseId: string) => mockApi.getOpenQuestions(caseId),
  submitQuestionAnswer: (questionId: string, answer: string) =>
    mockApi.submitQuestionAnswer(questionId, answer),
};
