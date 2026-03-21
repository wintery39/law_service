import { useEffect, useState } from 'react';
import type { QuestionRecord } from '../../types/question';

interface QuestionResponseModalProps {
  open: boolean;
  question: QuestionRecord | null;
  documentTitle?: string;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (answer: string) => void;
}

export function QuestionResponseModal({
  open,
  question,
  documentTitle,
  isSubmitting,
  onClose,
  onSubmit,
}: QuestionResponseModalProps) {
  const [answer, setAnswer] = useState('');

  useEffect(() => {
    if (question) {
      setAnswer(question.answer ?? '');
    }
  }, [question]);

  if (!open || !question) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 py-8 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-[32px] border border-white/60 bg-white p-6 shadow-panel">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">추가 질문 응답</p>
            <h2 className="mt-2 font-serif text-3xl font-semibold text-slate-950">{question.title}</h2>
            {documentTitle ? <p className="mt-2 text-sm text-slate-500">관련 문서: {documentTitle}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
          >
            닫기
          </button>
        </div>
        <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_0.9fr]">
          <div className="space-y-4 rounded-3xl bg-slate-50 p-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">질문 설명</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{question.prompt}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">필요한 이유</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{question.reason}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">답변 가이드</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{question.guidance}</p>
            </div>
          </div>
          <div>
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                답변 입력
              </span>
              <textarea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                rows={10}
                placeholder="질문에 대한 사실관계와 확인 결과를 입력하세요."
                className="w-full rounded-3xl border border-slate-200 bg-white px-4 py-4 text-sm leading-6 text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-navy-400 focus:ring-4 focus:ring-blue-100"
              />
            </label>
            <p className="mt-3 text-xs text-slate-500">
              답변이 제출되면 관련 문서 상태가 갱신되고 사건 진행률이 다시 계산됩니다.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
              >
                취소
              </button>
              <button
                type="button"
                disabled={isSubmitting || !answer.trim()}
                onClick={() => onSubmit(answer.trim())}
                className="rounded-full bg-navy-900 px-5 py-2 text-sm font-semibold text-white transition hover:bg-navy-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isSubmitting ? '제출 중...' : '답변 제출'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
