import type {
  CaseStatus,
  CaseType,
  DocumentStatus,
  PriorityLevel,
  QuestionStatus,
  SelectOption,
} from '../types/common';

export const caseTypeOptions: SelectOption<CaseType>[] = [
  { label: '전체 유형', value: 'all' },
  { label: '징계', value: 'disciplinary' },
];

export const caseStatusOptions: SelectOption<CaseStatus>[] = [
  { label: '전체 상태', value: 'all' },
  { label: '초안', value: 'draft' },
  { label: '진행 중', value: 'in_progress' },
  { label: '추가 입력 대기', value: 'waiting_for_input' },
  { label: '완료', value: 'completed' },
];

export const CASE_TYPE_LABELS: Record<CaseType, string> = {
  criminal: '형사',
  disciplinary: '징계',
  other: '기타',
};

export const CASE_STATUS_META: Record<
  CaseStatus,
  { label: string; className: string; dotClassName: string }
> = {
  draft: {
    label: '초안',
    className: 'bg-slate-100 text-slate-700 ring-slate-200',
    dotClassName: 'bg-slate-400',
  },
  in_progress: {
    label: '진행 중',
    className: 'bg-blue-50 text-blue-700 ring-blue-200',
    dotClassName: 'bg-blue-500',
  },
  waiting_for_input: {
    label: '추가 입력 대기',
    className: 'bg-amber-50 text-amber-800 ring-amber-200',
    dotClassName: 'bg-amber-500',
  },
  completed: {
    label: '완료',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    dotClassName: 'bg-emerald-500',
  },
};

export const DOCUMENT_STATUS_META: Record<
  DocumentStatus,
  { label: string; className: string; dotClassName: string }
> = {
  pending: {
    label: '대기',
    className: 'bg-slate-100 text-slate-700 ring-slate-200',
    dotClassName: 'bg-slate-400',
  },
  generating: {
    label: '작성 중',
    className: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
    dotClassName: 'bg-indigo-500',
  },
  needs_input: {
    label: '추가 정보 필요',
    className: 'bg-orange-50 text-orange-700 ring-orange-200',
    dotClassName: 'bg-orange-500',
  },
  completed: {
    label: '완료',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    dotClassName: 'bg-emerald-500',
  },
};

export const QUESTION_STATUS_META: Record<
  QuestionStatus,
  { label: string; className: string; dotClassName: string }
> = {
  open: {
    label: '응답 필요',
    className: 'bg-amber-50 text-amber-800 ring-amber-200',
    dotClassName: 'bg-amber-500',
  },
  answered: {
    label: '답변 완료',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    dotClassName: 'bg-emerald-500',
  },
};

export const PRIORITY_META: Record<
  PriorityLevel,
  { label: string; className: string }
> = {
  critical: {
    label: '긴급',
    className: 'bg-rose-50 text-rose-700 ring-rose-200',
  },
  high: {
    label: '높음',
    className: 'bg-orange-50 text-orange-700 ring-orange-200',
  },
  medium: {
    label: '보통',
    className: 'bg-blue-50 text-blue-700 ring-blue-200',
  },
  low: {
    label: '낮음',
    className: 'bg-slate-100 text-slate-700 ring-slate-200',
  },
};

export function getCaseTypeLabel(caseType: CaseType) {
  return CASE_TYPE_LABELS[caseType];
}
