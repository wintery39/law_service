export type CaseType = 'criminal' | 'disciplinary' | 'other';
export type CaseStatus = 'draft' | 'in_progress' | 'waiting_for_input' | 'completed';
export type DocumentStatus = 'pending' | 'generating' | 'needs_input' | 'completed';
export type QuestionStatus = 'open' | 'answered';
export type PriorityLevel = 'critical' | 'high' | 'medium' | 'low';
export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';

export interface SelectOption<T extends string = string> {
  label: string;
  value: T | 'all';
}

export interface DashboardMetrics {
  totalCases: number;
  inProgressCases: number;
  completedCases: number;
  waitingCases: number;
}
