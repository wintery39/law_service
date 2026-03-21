import type { TimelineEvent } from '../../types/case';
import { formatDateTime } from '../../utils/formatDate';

const toneByType: Record<TimelineEvent['type'], string> = {
  case_created: 'bg-blue-500',
  document_generated: 'bg-indigo-500',
  question_requested: 'bg-amber-500',
  question_answered: 'bg-emerald-500',
  document_completed: 'bg-teal-500',
  status_updated: 'bg-slate-500',
};

export function Timeline({ items }: { items: TimelineEvent[] }) {
  return (
    <ol className="space-y-4">
      {items.map((item) => (
        <li key={item.id} className="relative pl-8">
          <span className="absolute left-0 top-2 flex h-4 w-4 items-center justify-center rounded-full bg-white ring-4 ring-white">
            <span className={`h-3 w-3 rounded-full ${toneByType[item.type]}`} />
          </span>
          <div className="rounded-2xl bg-white px-4 py-4 shadow-soft">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="font-semibold text-slate-950">{item.title}</p>
              <p className="text-xs text-slate-500">{formatDateTime(item.occurredAt)}</p>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
            <p className="mt-3 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">{item.actor}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
