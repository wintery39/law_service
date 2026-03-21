import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { QuestionBox } from '../components/case/QuestionBox';
import { QuestionResponseModal } from '../components/case/QuestionResponseModal';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { PageSection } from '../components/common/PageSection';
import { StatusBadge } from '../components/common/StatusBadge';
import { LegalBasisCard } from '../components/document/LegalBasisCard';
import { useToast } from '../context/ToastContext';
import { caseService } from '../services/caseService';
import { documentService } from '../services/documentService';
import { questionService } from '../services/questionService';
import type { CaseDetail } from '../types/case';
import type { AsyncStatus } from '../types/common';
import type { DocumentDetail } from '../types/document';
import type { QuestionRecord } from '../types/question';
import { formatDateTime } from '../utils/formatDate';

export default function DocumentDetailPage() {
  const { caseId = '', documentId = '' } = useParams();
  const { showToast } = useToast();
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [status, setStatus] = useState<AsyncStatus>('loading');
  const [error, setError] = useState('');
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function loadDocument() {
    setStatus('loading');
    setError('');

    try {
      const [nextCaseDetail, nextDocumentDetail] = await Promise.all([
        caseService.getCaseById(caseId),
        documentService.getDocumentById(caseId, documentId),
      ]);

      setCaseDetail(nextCaseDetail);
      setDocumentDetail(nextDocumentDetail);
      setStatus('success');
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '문서 상세 조회에 실패했습니다.');
      setStatus('error');
    }
  }

  useEffect(() => {
    void loadDocument();
  }, [caseId, documentId]);

  async function handleSubmitAnswer(answer: string) {
    if (!selectedQuestion) {
      return;
    }

    setSubmitting(true);

    try {
      await questionService.submitQuestionAnswer(selectedQuestion.id, answer);
      await loadDocument();
      setSelectedQuestion(null);
      showToast({
        tone: 'success',
        title: '질문 답변을 반영했습니다.',
        description: '문서 이력과 상태가 새로 고쳐졌습니다.',
      });
    } catch (submitError) {
      showToast({
        tone: 'error',
        title: '질문 답변 반영 실패',
        description: submitError instanceof Error ? submitError.message : '잠시 후 다시 시도해 주세요.',
      });
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return <LoadingSpinner message="문서 본문, 법률 근거, 버전 이력을 불러오는 중입니다." />;
  }

  if (status === 'error' || !caseDetail || !documentDetail) {
    return <ErrorState description={error} onRetry={() => void loadDocument()} />;
  }

  const openQuestions = documentDetail.questions.filter((item) => item.status === 'open');

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-panel">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              {caseDetail.title}
            </p>
            <h2 className="mt-2 font-serif text-4xl font-semibold text-slate-950">{documentDetail.title}</h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">{documentDetail.description}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge type="document" value={documentDetail.status} />
            <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600">
              생성 순서 {documentDetail.order}단계
            </span>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to={`/cases/${caseId}`}
            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            사건 상세로 돌아가기
          </Link>
          <Link
            to={`/workflow/${caseId}`}
            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            전체 흐름 보기
          </Link>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.85fr]">
        <PageSection title="문서 본문 미리보기" description="실제 공문 초안처럼 문단을 나눠 가독성 있게 표현합니다.">
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <div className="rounded-3xl border border-slate-200 bg-slate-50 px-6 py-6">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-slate-800">
                {documentDetail.content}
              </pre>
            </div>
          </div>
        </PageSection>

        <PageSection title="법률적 근거" description="관련 법 조항과 적용 이유를 별도 패널로 강조합니다.">
          <div className="grid gap-4">
            {documentDetail.legalBasis.map((item) => (
              <LegalBasisCard key={item.id} item={item} />
            ))}
          </div>
        </PageSection>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <PageSection title="버전 이력" description="문서가 어떻게 보완되어 왔는지 버전 단위로 확인합니다.">
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <div className="space-y-4">
              {documentDetail.versionHistory.map((version) => (
                <div key={`${version.version}-${version.updatedAt}`} className="rounded-2xl bg-slate-50 px-4 py-4">
                  <div className="flex items-center justify-between gap-4">
                    <p className="font-semibold text-slate-950">{version.version}</p>
                    <p className="text-xs text-slate-500">{formatDateTime(version.updatedAt)}</p>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{version.note}</p>
                </div>
              ))}
            </div>
          </div>
        </PageSection>

        <PageSection title="수정 요청 및 질문 이력" description="문서 보완 과정에서 발생한 요청과 질문 상태를 함께 보여줍니다.">
          <div className="space-y-4 rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            {documentDetail.reviewHistory.length === 0 && documentDetail.questions.length === 0 ? (
              <EmptyState
                title="기록된 보완 이력이 없습니다."
                description="이 문서는 별도 수정 요청이나 추가 질문 없이 생성되었습니다."
              />
            ) : (
              <>
                {documentDetail.reviewHistory.map((item) => (
                  <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold text-slate-950">{item.title}</p>
                      <span className="text-xs text-slate-500">{formatDateTime(item.createdAt)}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                  </div>
                ))}
                {documentDetail.questions.map((question) => (
                  <QuestionBox
                    key={question.id}
                    question={question}
                    documentTitle={documentDetail.title}
                    onRespond={question.status === 'open' ? () => setSelectedQuestion(question) : undefined}
                  />
                ))}
              </>
            )}
          </div>
        </PageSection>
      </div>

      <PageSection title="문서 이동" description="이전 또는 다음 문서로 이어서 검토할 수 있습니다.">
        <div className="flex flex-wrap gap-3">
          {documentDetail.previousDocumentId ? (
            <Link
              to={`/cases/${caseId}/documents/${documentDetail.previousDocumentId}`}
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
            >
              이전 문서
            </Link>
          ) : null}
          {documentDetail.nextDocumentId ? (
            <Link
              to={`/cases/${caseId}/documents/${documentDetail.nextDocumentId}`}
              className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-800"
            >
              다음 문서
            </Link>
          ) : null}
        </div>
      </PageSection>

      <QuestionResponseModal
        open={Boolean(selectedQuestion)}
        question={selectedQuestion}
        documentTitle={documentDetail.title}
        isSubmitting={submitting}
        onClose={() => setSelectedQuestion(null)}
        onSubmit={(answer) => void handleSubmitAnswer(answer)}
      />
    </div>
  );
}
