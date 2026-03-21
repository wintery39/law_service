import type { CaseStatus, DocumentStatus, PriorityLevel, QuestionStatus } from '../../types/common';
import {
  CASE_STATUS_META,
  DOCUMENT_STATUS_META,
  PRIORITY_META,
  QUESTION_STATUS_META,
} from '../../utils/status';

type StatusBadgeProps =
  | { type: 'case'; value: CaseStatus }
  | { type: 'document'; value: DocumentStatus }
  | { type: 'question'; value: QuestionStatus }
  | { type: 'priority'; value: PriorityLevel };

export function StatusBadge(props: StatusBadgeProps) {
  const meta =
    props.type === 'case'
      ? CASE_STATUS_META[props.value]
      : props.type === 'document'
        ? DOCUMENT_STATUS_META[props.value]
        : props.type === 'question'
          ? QUESTION_STATUS_META[props.value]
          : PRIORITY_META[props.value];

  const dotClassName = 'dotClassName' in meta ? meta.dotClassName : 'bg-slate-500';

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${meta.className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotClassName}`} />
      {meta.label}
    </span>
  );
}
