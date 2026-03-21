import type { ReactNode } from 'react';

interface SummaryCardProps {
  title: string;
  value: string | number;
  description: string;
  accent?: 'navy' | 'slate' | 'emerald' | 'amber';
  extra?: ReactNode;
}

const accentMap = {
  navy: 'from-navy-900 via-navy-800 to-blue-700 text-white',
  slate: 'from-slate-100 via-white to-slate-50 text-slate-950',
  emerald: 'from-emerald-600 via-emerald-500 to-teal-500 text-white',
  amber: 'from-amber-500 via-orange-500 to-amber-400 text-white',
};

export function SummaryCard({
  title,
  value,
  description,
  accent = 'slate',
  extra,
}: SummaryCardProps) {
  return (
    <article
      className={`rounded-3xl border border-white/60 bg-gradient-to-br px-5 py-5 shadow-soft ${accentMap[accent]}`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.22em] opacity-80">{title}</p>
      <div className="mt-4 flex items-end justify-between gap-4">
        <p className="font-serif text-4xl font-semibold leading-none">{value}</p>
        {extra}
      </div>
      <p className="mt-4 text-sm leading-6 opacity-85">{description}</p>
    </article>
  );
}
