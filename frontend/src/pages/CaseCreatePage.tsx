import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageSection } from '../components/common/PageSection';
import { useToast } from '../context/ToastContext';
import { caseService } from '../services/caseService';
import type { CaseCreatePayload } from '../types/case';
import type { CaseType, PriorityLevel } from '../types/common';

interface FormErrors {
  title?: string;
  caseType?: string;
  occurredAt?: string;
  location?: string;
  author?: string;
  relatedPersons?: string;
  summary?: string;
  details?: string;
  attachmentSummary?: string;
}

const priorityOptions: Array<{ value: PriorityLevel; label: string }> = [
  { value: 'critical', label: '긴급' },
  { value: 'high', label: '높음' },
  { value: 'medium', label: '보통' },
  { value: 'low', label: '낮음' },
];

export default function CaseCreatePage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [form, setForm] = useState({
    title: '',
    caseType: 'criminal' as CaseType,
    occurredAt: '2026-03-19T09:00',
    location: '',
    author: '',
    relatedPersons: '',
    summary: '',
    details: '',
    attachmentProvided: true,
    attachmentSummary: '',
    priority: 'high' as PriorityLevel,
  });

  function validate() {
    const nextErrors: FormErrors = {};

    if (!form.title.trim()) nextErrors.title = '사건 제목을 입력하세요.';
    if (!form.caseType) nextErrors.caseType = '사건 유형을 선택하세요.';
    if (!form.occurredAt) nextErrors.occurredAt = '발생 일시를 입력하세요.';
    if (!form.location.trim()) nextErrors.location = '발생 장소를 입력하세요.';
    if (!form.author.trim()) nextErrors.author = '작성자를 입력하세요.';
    if (!form.relatedPersons.trim()) nextErrors.relatedPersons = '관련자를 한 명 이상 입력하세요.';
    if (form.summary.trim().length < 10) nextErrors.summary = '사건 개요는 10자 이상 입력하세요.';
    if (form.details.trim().length < 30) nextErrors.details = '상세 사실관계는 30자 이상 입력하세요.';
    if (form.attachmentProvided && form.attachmentSummary.trim().length < 5) {
      nextErrors.attachmentSummary = '첨부 자료가 있다면 5자 이상으로 요약해 주세요.';
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!validate()) {
      return;
    }

    setIsSubmitting(true);
    setSubmitError('');

    const payload: CaseCreatePayload = {
      title: form.title.trim(),
      caseType: form.caseType,
      occurredAt: new Date(form.occurredAt).toISOString(),
      location: form.location.trim(),
      author: form.author.trim(),
      relatedPersons: form.relatedPersons
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      summary: form.summary.trim(),
      details: form.details.trim(),
      attachmentProvided: form.attachmentProvided,
      attachmentSummary: form.attachmentProvided ? form.attachmentSummary.trim() : '',
      priority: form.priority,
    };

    try {
      const createdCase = await caseService.createCase(payload);
      showToast({
        tone: 'success',
        title: '사건이 등록되었습니다.',
        description: '기본 문서 패키지가 생성되어 상세 화면으로 이동합니다.',
      });
      navigate(`/cases/${createdCase.id}`);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '사건 생성 중 오류가 발생했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  }

  function fieldError(name: keyof FormErrors) {
    return errors[name] ? <p className="mt-2 text-sm text-rose-600">{errors[name]}</p> : null;
  }

  return (
    <div className="space-y-8">
      <PageSection
        title="새 사건 등록"
        description="기본 사실관계를 입력하면 LawFlow가 사건 유형에 맞는 문서 흐름을 생성합니다."
      >
        <div className="grid gap-6 xl:grid-cols-[1.45fr_0.8fr]">
          <form
            onSubmit={handleSubmit}
            className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-panel"
          >
            <div className="grid gap-5 md:grid-cols-2">
              <label className="md:col-span-2">
                <span className="form-label">사건 제목</span>
                <input
                  value={form.title}
                  onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                  className="form-input"
                  placeholder="예: 창고 자산 반출 의혹 조사"
                />
                {fieldError('title')}
              </label>

              <label>
                <span className="form-label">사건 유형</span>
                <select
                  value={form.caseType}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, caseType: event.target.value as CaseType }))
                  }
                  className="form-input"
                >
                  <option value="criminal">형사</option>
                  <option value="disciplinary">징계</option>
                  <option value="other">기타</option>
                </select>
                {fieldError('caseType')}
              </label>

              <label>
                <span className="form-label">긴급도</span>
                <select
                  value={form.priority}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, priority: event.target.value as PriorityLevel }))
                  }
                  className="form-input"
                >
                  {priorityOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span className="form-label">발생 일시</span>
                <input
                  type="datetime-local"
                  value={form.occurredAt}
                  onChange={(event) => setForm((current) => ({ ...current, occurredAt: event.target.value }))}
                  className="form-input"
                />
                {fieldError('occurredAt')}
              </label>

              <label>
                <span className="form-label">발생 장소</span>
                <input
                  value={form.location}
                  onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
                  className="form-input"
                  placeholder="예: 제3보급대대 창고동"
                />
                {fieldError('location')}
              </label>

              <label>
                <span className="form-label">작성자</span>
                <input
                  value={form.author}
                  onChange={(event) => setForm((current) => ({ ...current, author: event.target.value }))}
                  className="form-input"
                  placeholder="예: 대위 홍길동"
                />
                {fieldError('author')}
              </label>

              <label>
                <span className="form-label">관련자</span>
                <input
                  value={form.relatedPersons}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, relatedPersons: event.target.value }))
                  }
                  className="form-input"
                  placeholder="쉼표로 구분해 입력"
                />
                {fieldError('relatedPersons')}
              </label>

              <label className="md:col-span-2">
                <span className="form-label">사건 개요</span>
                <textarea
                  value={form.summary}
                  onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))}
                  rows={4}
                  className="form-textarea"
                  placeholder="핵심 쟁점과 현재 확인된 사실을 간단히 요약하세요."
                />
                {fieldError('summary')}
              </label>

              <label className="md:col-span-2">
                <span className="form-label">상세 사실관계</span>
                <textarea
                  value={form.details}
                  onChange={(event) => setForm((current) => ({ ...current, details: event.target.value }))}
                  rows={8}
                  className="form-textarea"
                  placeholder="시간 순서, 관련자 행동, 확보된 자료, 확인이 필요한 점을 포함해 입력하세요."
                />
                {fieldError('details')}
              </label>

              <label className="md:col-span-2 flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                <input
                  type="checkbox"
                  checked={form.attachmentProvided}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      attachmentProvided: event.target.checked,
                      attachmentSummary: event.target.checked ? current.attachmentSummary : '',
                    }))
                  }
                  className="h-4 w-4 rounded border-slate-300 text-navy-900 focus:ring-navy-700"
                />
                <span className="text-sm font-medium text-slate-700">첨부자료 있음</span>
              </label>

              {form.attachmentProvided ? (
                <label className="md:col-span-2">
                  <span className="form-label">첨부 자료 요약</span>
                  <textarea
                    value={form.attachmentSummary}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, attachmentSummary: event.target.value }))
                    }
                    rows={3}
                    className="form-textarea"
                    placeholder="예: CCTV 캡처 4장, 출입기록 CSV, 창고 책임관 메모 1부"
                  />
                  {fieldError('attachmentSummary')}
                </label>
              ) : null}
            </div>

            {submitError ? (
              <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {submitError}
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="rounded-full border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
              >
                취소
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="rounded-full bg-navy-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-navy-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {isSubmitting ? '등록 중...' : '사건 등록 후 상세 보기'}
              </button>
            </div>
          </form>

          <aside className="space-y-5">
            <div className="rounded-[32px] border border-white/60 bg-white/90 p-6 shadow-soft">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">자동 생성 흐름</p>
              <h3 className="mt-3 font-serif text-2xl font-semibold text-slate-950">등록 후 이어지는 5단계</h3>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
                <li>1단계: 새 사건 등록과 기본 사실관계 입력</li>
                <li>2단계: 첨부 자료 등록 또는 생략 처리</li>
                <li>3단계: LLM 추가 정보 요청 여부 확인</li>
                <li>4단계: 사건 유형에 맞는 문서 패키지 생성</li>
                <li>5단계: 문서 검토와 사용자 피드백 반영</li>
              </ul>
            </div>

            <div className="rounded-[32px] border border-navy-100 bg-gradient-to-br from-blue-50 via-white to-slate-50 p-6 shadow-soft">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">작성 팁</p>
              <div className="mt-4 space-y-3 text-sm leading-6 text-slate-700">
                <p>사건 개요는 발표자가 한 문장으로 설명할 수 있게 핵심만 정리하는 편이 좋습니다.</p>
                <p>상세 사실관계에는 시간 순서와 확인된 자료를 포함하면 문서 초안 품질이 안정적으로 올라갑니다.</p>
                <p>관련자는 쉼표 기준으로 입력하면 상세 화면의 정보 카드에 그대로 표시됩니다.</p>
              </div>
            </div>
          </aside>
        </div>
      </PageSection>
    </div>
  );
}
