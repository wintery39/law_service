import type { ReactNode } from 'react';

interface SummaryCardProps {
  title: string;
  value: string | number;
  description: string;
  accent?: 'navy' | 'slate' | 'emerald' | 'amber';
  extra?: ReactNode;
}

const accentMap = {
  navy: {
    container: 'border-navy-100 from-blue-50 via-white to-slate-50 text-slate-950',
    eyebrow: 'text-navy-800',
    description: 'text-slate-700',
  },
  slate: {
    container: 'from-slate-100 via-white to-slate-50 text-slate-950',
    eyebrow: 'text-slate-700',
    description: 'text-slate-700',
  },
  emerald: {
    container: 'from-emerald-100 via-teal-50 to-white text-emerald-950',
    eyebrow: 'text-emerald-900',
    description: 'text-emerald-900',
  },
  amber: {
    container: 'from-amber-100 via-orange-50 to-white text-amber-950',
    eyebrow: 'text-amber-900',
    description: 'text-amber-950',
  },
};

export function SummaryCard({
  title,
  value,
  description,
  accent = 'slate',
  extra,
}: SummaryCardProps) {
  const accentStyles = accentMap[accent];

  return (
    <article
      className={`rounded-3xl border bg-gradient-to-br px-5 py-5 shadow-soft ${accentStyles.container}`}
    >
      <p className={`text-xs font-semibold uppercase tracking-[0.22em] ${accentStyles.eyebrow}`}>{title}</p>
      <div className="mt-4 flex items-end justify-between gap-4">
        <p className="font-serif text-4xl font-semibold leading-none">{value}</p>
        {extra}
      </div>
      <p className={`mt-4 text-sm leading-6 ${accentStyles.description}`}>{description}</p>
    </article>
  );
}
