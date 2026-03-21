import type { QuestionRecord } from '../../types/question';
import { formatDateTime } from '../../utils/formatDate';
import { StatusBadge } from '../common/StatusBadge';

interface QuestionBoxProps {
  question: QuestionRecord;
  documentTitle?: string;
  onRespond?: () => void;
}

export function QuestionBox({ question, documentTitle, onRespond }: QuestionBoxProps) {
  return (
    <article className="rounded-3xl border border-amber-200 bg-amber-50/70 p-5 shadow-soft">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">LLM 추가 질문</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">{question.title}</h3>
          {documentTitle ? <p className="mt-1 text-sm text-slate-500">관련 문서: {documentTitle}</p> : null}
        </div>
        <StatusBadge type="question" value={question.status} />
      </div>
      <div className="mt-4 space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">질문 내용</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">{question.prompt}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">필요한 이유</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">{question.reason}</p>
        </div>
        <div className="rounded-2xl bg-white/80 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">작성 가이드</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">{question.guidance}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500">생성 시각: {formatDateTime(question.createdAt)}</p>
          {question.status === 'open' && onRespond ? (
            <button
              type="button"
              onClick={onRespond}
              className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-900"
            >
              답변 입력
            </button>
          ) : question.answer ? (
            <p className="text-sm text-emerald-700">답변 완료: {question.answer}</p>
          ) : null}
        </div>
      </div>
    </article>
  );
}
