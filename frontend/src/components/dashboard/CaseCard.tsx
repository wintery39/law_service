import { Link } from 'react-router-dom';
import type { CaseSummary } from '../../types/case';
import { formatDate } from '../../utils/formatDate';
import { getCaseTypeLabel } from '../../utils/status';
import { ProgressBar } from '../common/ProgressBar';
import { StatusBadge } from '../common/StatusBadge';

export function CaseCard({ item }: { item: CaseSummary }) {
  return (
    <article className="rounded-3xl border border-white/60 bg-white/90 p-5 shadow-soft">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            {getCaseTypeLabel(item.caseType)}
          </p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">{item.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{item.summary}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge type="case" value={item.status} />
          <StatusBadge type="priority" value={item.priority} />
        </div>
      </div>
      <div className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">발생일</p>
          <p className="mt-1">{formatDate(item.occurredAt)}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">마지막 수정</p>
          <p className="mt-1">{formatDate(item.updatedAt)}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">추가 질문</p>
          <p className="mt-1">{item.activeQuestionCount}건</p>
        </div>
      </div>
      <div className="mt-4">
        <ProgressBar value={item.progressPercent} />
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        <Link
          to={`/cases/${item.id}`}
          className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-900"
        >
          사건 상세 보기
        </Link>
        <Link
          to={`/workflow/${item.id}`}
          className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400"
        >
          전체 흐름 보기
        </Link>
      </div>
    </article>
  );
}
