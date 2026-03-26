import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import legalBasisData from '../mocks/legal-basis.json';
import { DocumentStepCard } from '../components/case/DocumentStepCard';
import { QuestionBox } from '../components/case/QuestionBox';
import { QuestionResponseModal } from '../components/case/QuestionResponseModal';
import { Timeline } from '../components/case/Timeline';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { KeyValueInfoList } from '../components/common/KeyValueInfoList';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { PageSection } from '../components/common/PageSection';
import { ProgressBar } from '../components/common/ProgressBar';
import { StatusBadge } from '../components/common/StatusBadge';
import { useToast } from '../context/ToastContext';
import { caseService } from '../services/caseService';
import { questionService } from '../services/questionService';
import type { CaseDetail } from '../types/case';
import type { AsyncStatus } from '../types/common';
import type { QuestionRecord } from '../types/question';
import { formatDateTime } from '../utils/formatDate';
import { getCaseTypeLabel } from '../utils/status';

const legalBasisMap = new Map(
  legalBasisData.map((item) => [item.id, `${item.lawName} ${item.article}`]),
);

export default function CaseDetailPage() {
  const { caseId = '' } = useParams();
  const { showToast } = useToast();
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [status, setStatus] = useState<AsyncStatus>('loading');
  const [error, setError] = useState('');
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function loadCase() {
    setStatus('loading');
    setError('');

    try {
      const detail = await caseService.getCaseById(caseId);
      setCaseDetail(detail);
      setStatus('success');
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '사건 상세 조회에 실패했습니다.');
      setStatus('error');
    }
  }

  useEffect(() => {
    void loadCase();
  }, [caseId]);

  async function handleAnswerSubmit(answer: string) {
    if (!selectedQuestion) {
      return;
    }

    setSubmitting(true);

    try {
      const nextDetail = await questionService.submitQuestionAnswer(selectedQuestion.id, answer);
      setCaseDetail(nextDetail);
      setSelectedQuestion(null);
      showToast({
        tone: 'success',
        title: '질문 답변이 반영되었습니다.',
        description: '관련 문서 상태와 사건 진행률이 갱신되었습니다.',
      });
    } catch (submitError) {
      showToast({
        tone: 'error',
        title: '답변 반영에 실패했습니다.',
        description: submitError instanceof Error ? submitError.message : '잠시 후 다시 시도해 주세요.',
      });
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return <LoadingSpinner message="사건 상세, 문서 흐름, 질문 현황을 불러오는 중입니다." />;
  }

  if (status === 'error' || !caseDetail) {
    return <ErrorState description={error} onRetry={() => void loadCase()} />;
  }

  const openQuestions = caseDetail.questions.filter((question) => question.status === 'open');
  const currentStage =
    caseDetail.workflowStages.find((stage) => stage.status === 'active') ??
    [...caseDetail.workflowStages].reverse().find((stage) => stage.status === 'completed') ??
    caseDetail.workflowStages[0];

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-panel">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap gap-2">
              <StatusBadge type="case" value={caseDetail.status} />
              <StatusBadge type="priority" value={caseDetail.priority} />
            </div>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              {getCaseTypeLabel(caseDetail.caseType)} 사건
            </p>
            <h2 className="mt-2 font-serif text-4xl font-semibold leading-tight text-slate-950">
              {caseDetail.title}
            </h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">{caseDetail.summary}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to={`/workflow/${caseDetail.id}`}
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
            >
              전체 흐름 보기
            </Link>
            <Link
              to="/cases/new"
              className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-800"
            >
              새 사건 생성
            </Link>
          </div>
        </div>
        <div className="mt-6 rounded-3xl bg-slate-50 p-5">
          <ProgressBar value={caseDetail.progressPercent} label="사건 전체 진행률" />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <PageSection title="사건 기본 정보" description="발생 시점, 관련자, 작성자, 우선순위를 한 번에 확인합니다.">
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <KeyValueInfoList
              items={[
                { label: '발생 일시', value: formatDateTime(caseDetail.occurredAt) },
                { label: '발생 장소', value: caseDetail.location },
                { label: '작성자', value: caseDetail.author },
                { label: '관련자', value: caseDetail.relatedPersons.join(', ') },
                {
                  label: '첨부자료',
                  value: caseDetail.attachmentProvided ? '제출됨' : '없음',
                },
                {
                  label: '첨부자료 요약',
                  value: caseDetail.attachmentProvided ? caseDetail.attachmentSummary : '생략됨',
                },
                { label: '긴급 메모', value: caseDetail.urgencyNote },
              ]}
            />
            <div className="mt-5 rounded-3xl bg-blue-50/70 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">현재 단계</p>
              <p className="mt-3 text-lg font-semibold text-slate-900">
                {currentStage.caption} {currentStage.title}
              </p>
              <p className="mt-2 text-sm leading-7 text-slate-700">{currentStage.detail}</p>
            </div>
            <div className="mt-5 rounded-3xl bg-blue-50/70 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">법률 검토 요약</p>
              <p className="mt-3 text-sm leading-7 text-slate-700">{caseDetail.legalReviewSummary}</p>
            </div>
          </div>
        </PageSection>

        <PageSection title="최근 활동 타임라인" description="같은 5단계 키 기준으로 사건 등록부터 검토 이력까지 최근 활동을 보여줍니다.">
          <div className="rounded-[32px] border border-white/60 bg-slate-50/80 p-6 shadow-soft">
            <Timeline items={caseDetail.timeline} />
          </div>
        </PageSection>
      </div>

      <PageSection
        title="문서 생성 단계"
        description="필요 문서 목록과 상태, 법률 근거 요약, 문서 상세 진입 링크를 제공합니다."
      >
        <div className="grid gap-4">
          {caseDetail.documents.map((document) => (
            <DocumentStepCard
              key={document.id}
              caseId={caseDetail.id}
              document={document}
              legalSummary={document.legalBasisIds.map((basisId) => legalBasisMap.get(basisId) ?? basisId)}
            />
          ))}
        </div>
      </PageSection>

      <PageSection
        title="LLM 추가 질문"
        description="문서 생성 과정에서 부족한 정보를 보완하기 위한 질문입니다."
      >
        {openQuestions.length === 0 ? (
          <EmptyState
            title="현재 응답이 필요한 질문이 없습니다."
            description="모든 문서가 필요한 정보를 확보한 상태이거나, 다음 생성 단계로 넘어간 상태입니다."
          />
        ) : (
          <div className="grid gap-4">
            {openQuestions.map((question) => {
              const relatedDocument = caseDetail.documents.find((item) => item.id === question.documentId);

              return (
                <QuestionBox
                  key={question.id}
                  question={question}
                  documentTitle={relatedDocument?.title}
                  onRespond={() => setSelectedQuestion(question)}
                />
              );
            })}
          </div>
        )}
      </PageSection>

      <QuestionResponseModal
        open={Boolean(selectedQuestion)}
        question={selectedQuestion}
        documentTitle={
          selectedQuestion
            ? caseDetail.documents.find((item) => item.id === selectedQuestion.documentId)?.title
            : undefined
        }
        isSubmitting={submitting}
        onClose={() => setSelectedQuestion(null)}
        onSubmit={(answer) => void handleAnswerSubmit(answer)}
      />
    </div>
  );
}
