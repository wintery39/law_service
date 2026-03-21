import type { CaseStatus, CaseType } from '../../types/common';
import { caseStatusOptions, caseTypeOptions } from '../../utils/status';

interface SearchFilterBarProps {
  search: string;
  caseType: CaseType | 'all';
  status: CaseStatus | 'all';
  resultCount: number;
  onSearchChange: (value: string) => void;
  onCaseTypeChange: (value: CaseType | 'all') => void;
  onStatusChange: (value: CaseStatus | 'all') => void;
}

export function SearchFilterBar({
  search,
  caseType,
  status,
  resultCount,
  onSearchChange,
  onCaseTypeChange,
  onStatusChange,
}: SearchFilterBarProps) {
  return (
    <div className="rounded-3xl border border-white/60 bg-white/90 p-4 shadow-soft">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <label className="flex-1">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            사건명 검색
          </span>
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="사건명 또는 요약으로 검색"
            className="h-12 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-navy-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
          />
        </label>
        <label className="w-full lg:max-w-[180px]">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            사건 유형
          </span>
          <select
            value={caseType}
            onChange={(event) => onCaseTypeChange(event.target.value as CaseType | 'all')}
            className="h-12 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-900 outline-none transition focus:border-navy-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
          >
            {caseTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="w-full lg:max-w-[180px]">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            상태 필터
          </span>
          <select
            value={status}
            onChange={(event) => onStatusChange(event.target.value as CaseStatus | 'all')}
            className="h-12 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-900 outline-none transition focus:border-navy-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
          >
            {caseStatusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="mt-4 text-sm text-slate-500">현재 조건에 맞는 사건 {resultCount}건</p>
    </div>
  );
}
