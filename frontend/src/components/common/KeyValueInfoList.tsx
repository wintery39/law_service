import type { ReactNode } from 'react';

interface KeyValueInfoListProps {
  items: Array<{
    label: string;
    value: ReactNode;
  }>;
  columns?: 1 | 2;
}

export function KeyValueInfoList({ items, columns = 2 }: KeyValueInfoListProps) {
  return (
    <dl className={`grid gap-4 ${columns === 2 ? 'sm:grid-cols-2' : 'grid-cols-1'}`}>
      {items.map((item) => (
        <div key={item.label} className="rounded-2xl bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{item.label}</dt>
          <dd className="mt-2 text-sm leading-6 text-slate-900">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
