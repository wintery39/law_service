import { Link } from 'react-router-dom';
import type { CaseSummary } from '../../types/case';
import { formatDate } from '../../utils/formatDate';
import { getCaseTypeLabel } from '../../utils/status';
import { ProgressBar } from '../common/ProgressBar';
import { StatusBadge } from '../common/StatusBadge';
import { CaseCard } from './CaseCard';

export function CaseTable({ cases }: { cases: CaseSummary[] }) {
  return (
    <>
      <div className="grid gap-4 xl:hidden">
        {cases.map((item) => (
          <CaseCard key={item.id} item={item} />
        ))}
      </div>
      <div className="hidden overflow-hidden rounded-3xl border border-white/60 bg-white/90 shadow-soft xl:block">
        <table className="min-w-full divide-y divide-slate-100">
          <thead className="bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <tr>
              <th className="px-6 py-4">사건명</th>
              <th className="px-6 py-4">유형</th>
              <th className="px-6 py-4">상태</th>
              <th className="px-6 py-4">생성일</th>
              <th className="px-6 py-4">마지막 수정</th>
              <th className="px-6 py-4">진행률</th>
              <th className="px-6 py-4">이동</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {cases.map((item) => (
              <tr key={item.id} className="align-top text-sm text-slate-700">
                <td className="px-6 py-5">
                  <p className="font-semibold text-slate-950">{item.title}</p>
                  <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">{item.summary}</p>
                </td>
                <td className="px-6 py-5">{getCaseTypeLabel(item.caseType)}</td>
                <td className="px-6 py-5">
                  <div className="flex flex-col gap-2">
                    <StatusBadge type="case" value={item.status} />
                    {item.activeQuestionCount > 0 ? (
                      <span className="text-xs text-amber-700">질문 {item.activeQuestionCount}건 대기</span>
                    ) : null}
                    {item.openReviewCount > 0 ? (
                      <span className="text-xs text-blue-700">피드백 {item.openReviewCount}건 대기</span>
                    ) : null}
                  </div>
                </td>
                <td className="px-6 py-5">{formatDate(item.createdAt)}</td>
                <td className="px-6 py-5">{formatDate(item.updatedAt)}</td>
                <td className="px-6 py-5">
                  <div className="w-40">
                    <ProgressBar value={item.progressPercent} />
                  </div>
                </td>
                <td className="px-6 py-5">
                  <div className="flex flex-col gap-2">
                    <Link to={`/cases/${item.id}`} className="font-semibold text-navy-700 hover:text-navy-900">
                      사건 상세
                    </Link>
                    <Link to={`/workflow/${item.id}`} className="text-slate-600 hover:text-slate-900">
                      흐름 보기
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
