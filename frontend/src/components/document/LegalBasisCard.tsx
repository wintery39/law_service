import type { LegalBasisEntry } from '../../types/legalBasis';

export function LegalBasisCard({ item }: { item: LegalBasisEntry }) {
  return (
    <article className="rounded-3xl border border-blue-100 bg-blue-50/70 p-5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">{item.lawName}</p>
      <h3 className="mt-2 text-lg font-semibold text-slate-950">{item.article}</h3>
      <p className="mt-3 text-sm leading-6 text-slate-700">{item.summary}</p>
      <div className="mt-4 rounded-2xl bg-white/90 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">적용 이유</p>
        <p className="mt-2 text-sm leading-6 text-slate-700">{item.rationale}</p>
      </div>
    </article>
  );
}
