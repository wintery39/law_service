import { Link } from 'react-router-dom';
import type { DocumentRecord } from '../../types/document';
import { getDocumentTypeLabel } from '../../utils/documentCatalog';
import { StatusBadge } from '../common/StatusBadge';

interface DocumentStepCardProps {
  caseId: string;
  document: DocumentRecord;
  legalSummary: string[];
}

export function DocumentStepCard({ caseId, document, legalSummary }: DocumentStepCardProps) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-navy-900 text-sm font-semibold text-white">
              {document.order}
            </span>
            <div>
              <h3 className="text-lg font-semibold text-slate-950">{document.title}</h3>
              <p className="mt-1 text-sm text-slate-500">{getDocumentTypeLabel(document.type)}</p>
            </div>
          </div>
          <p className="text-sm leading-6 text-slate-600">{document.description}</p>
        </div>
        <StatusBadge type="document" value={document.status} />
      </div>
      <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">법률 근거 요약</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {legalSummary.map((basis) => (
            <span key={basis} className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
              {basis}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <Link
          to={`/cases/${caseId}/documents/${document.id}`}
          className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-navy-200 hover:bg-navy-50 hover:text-navy-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-700"
        >
          상세 보기
        </Link>
      </div>
    </article>
  );
}
