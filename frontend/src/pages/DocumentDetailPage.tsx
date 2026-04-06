import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { QuestionBox } from '../components/case/QuestionBox';
import { QuestionResponseModal } from '../components/case/QuestionResponseModal';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { PageSection } from '../components/common/PageSection';
import { StatusBadge } from '../components/common/StatusBadge';
import { HighlightedDiffText } from '../components/document/HighlightedDiffText';
import { LegalBasisCard } from '../components/document/LegalBasisCard';
import { useToast } from '../context/ToastContext';
import { caseService } from '../services/caseService';
import { documentService } from '../services/documentService';
import { questionService } from '../services/questionService';
import type { CaseDetail } from '../types/case';
import type { AsyncStatus } from '../types/common';
import type {
  DocumentChangeSet,
  DocumentDetail,
  DocumentPatch,
  PatchDecision,
} from '../types/document';
import type { QuestionRecord } from '../types/question';
import { formatDateTime } from '../utils/formatDate';

const CHANGE_TYPE_META: Record<DocumentPatch['changeType'], { label: string; className: string }> = {
  add: {
    label: '추가',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  },
  modify: {
    label: '수정',
    className: 'bg-blue-50 text-blue-700 ring-blue-200',
  },
  remove: {
    label: '삭제',
    className: 'bg-rose-50 text-rose-700 ring-rose-200',
  },
};

const CHANGE_SET_SOURCE_LABEL: Record<DocumentChangeSet['source'], string> = {
  initial_generation: '초기 생성',
  question_answer: '질문 답변 반영',
  review_feedback: '피드백 반영',
};

function buildDecisionButtonClass(selected: boolean, tone: 'approve' | 'reject') {
  if (selected && tone === 'approve') {
    return 'border-emerald-700 bg-emerald-600 text-white';
  }
  if (selected && tone === 'reject') {
    return 'border-rose-700 bg-rose-600 text-white';
  }
  return tone === 'approve'
    ? 'border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50'
    : 'border-rose-200 bg-white text-rose-700 hover:bg-rose-50';
}

export default function DocumentDetailPage() {
  const { caseId = '', documentId = '' } = useParams();
  const { showToast } = useToast();
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [status, setStatus] = useState<AsyncStatus>('loading');
  const [error, setError] = useState('');
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedbackTitle, setFeedbackTitle] = useState('');
  const [feedbackDescription, setFeedbackDescription] = useState('');
  const [feedbackError, setFeedbackError] = useState('');
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [patchDecisions, setPatchDecisions] = useState<Record<string, Exclude<PatchDecision, 'pending'>>>({});
  const [submittingChangeSet, setSubmittingChangeSet] = useState(false);

  async function loadDocument(showLoader = true) {
    if (showLoader) {
      setStatus('loading');
    }
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

  useEffect(() => {
    if (!documentDetail?.activeChangeSet) {
      setPatchDecisions({});
      return;
    }

    setPatchDecisions(
      Object.fromEntries(
        documentDetail.activeChangeSet.patches.map((patch) => [
          patch.id,
          patch.decision === 'pending'
            ? 'rejected'
            : (patch.decision as Exclude<PatchDecision, 'pending'>),
        ]),
      ),
    );
  }, [documentDetail?.activeChangeSet?.id]);

  async function handleSubmitAnswer(answer: string) {
    if (!selectedQuestion) {
      return;
    }

    setSubmitting(true);

    try {
      await questionService.submitQuestionAnswer(selectedQuestion.id, answer);
      await loadDocument(false);
      setSelectedQuestion(null);
      showToast({
        tone: 'success',
        title: '질문 답변을 저장했습니다.',
        description: '문서 상태와 승인 대기 수정안을 다시 확인했습니다.',
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

  async function handleFeedbackSubmit() {
    const trimmedTitle = feedbackTitle.trim();
    const trimmedDescription = feedbackDescription.trim();

    if (trimmedTitle.length < 2) {
      setFeedbackError('피드백 제목을 2자 이상 입력해 주세요.');
      return;
    }

    if (trimmedDescription.length < 10) {
      setFeedbackError('피드백 내용은 10자 이상 입력해 주세요.');
      return;
    }

    setFeedbackError('');
    setSubmittingFeedback(true);

    try {
      await documentService.submitDocumentReview(caseId, documentId, trimmedTitle, trimmedDescription);
      await loadDocument(false);
      setFeedbackTitle('');
      setFeedbackDescription('');
      showToast({
        tone: 'success',
        title: '문서 피드백을 저장했습니다.',
        description: '검토 이력과 문서 상태를 다시 확인했습니다.',
      });
    } catch (submitError) {
      setFeedbackError(
        submitError instanceof Error ? submitError.message : '피드백 등록 중 오류가 발생했습니다.',
      );
    } finally {
      setSubmittingFeedback(false);
    }
  }

  function handlePatchDecisionChange(patchId: string, decision: Exclude<PatchDecision, 'pending'>) {
    setPatchDecisions((current) => ({
      ...current,
      [patchId]: decision,
    }));
  }

  async function handleApplyChangeSet() {
    const changeSet = documentDetail?.activeChangeSet;
    if (!changeSet) {
      return;
    }

    const approvedPatchIds = changeSet.patches
      .filter((patch) => (patchDecisions[patch.id] ?? 'rejected') === 'approved')
      .map((patch) => patch.id);
    const rejectedPatchIds = changeSet.patches
      .filter((patch) => (patchDecisions[patch.id] ?? 'rejected') === 'rejected')
      .map((patch) => patch.id);

    setSubmittingChangeSet(true);

    try {
      await documentService.applyDocumentChangeSet(
        caseId,
        documentId,
        changeSet.id,
        approvedPatchIds,
        rejectedPatchIds,
      );
      await loadDocument(false);
      showToast({
        tone: 'success',
        title: '선택한 변경안을 적용했습니다.',
        description:
          approvedPatchIds.length > 0
            ? `${approvedPatchIds.length}개 섹션이 공식 본문에 반영되었습니다.`
            : '모든 변경 섹션을 거절 처리했습니다.',
      });
    } catch (applyError) {
      showToast({
        tone: 'error',
        title: '변경안 적용 실패',
        description: applyError instanceof Error ? applyError.message : '잠시 후 다시 시도해 주세요.',
      });
    } finally {
      setSubmittingChangeSet(false);
    }
  }

  if (status === 'loading') {
    return <LoadingSpinner message="문서 본문, 변경 제안, 법률 근거를 불러오는 중입니다." />;
  }

  if (status === 'error' || !caseDetail || !documentDetail) {
    return <ErrorState description={error} onRetry={() => void loadDocument()} />;
  }

  const approvedContent = documentDetail.approvedBody?.compiledText || documentDetail.content;
  const activeChangeSet = documentDetail.activeChangeSet;
  const changeSetHistoryItems = documentDetail.changeSetHistorySummary ?? documentDetail.changeSetHistory ?? [];

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

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <PageSection
          title="공식 본문"
          description="현재 승인되어 실제 문서 본문으로 간주되는 내용입니다."
        >
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <div className="rounded-3xl border border-slate-200 bg-slate-50 px-6 py-6">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-slate-800">
                {approvedContent}
              </pre>
            </div>
          </div>
        </PageSection>

        <PageSection
          title="승인 대기 수정안"
          description="원본 대비 변경된 섹션만 확인하고 선택 승인할 수 있습니다."
        >
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            {!activeChangeSet ? (
              <EmptyState
                title="현재 승인 대기 중인 수정안이 없습니다."
                description="새 질문 답변이나 피드백이 반영되면 이 영역에 변경된 섹션 제안이 표시됩니다."
              />
            ) : (
              <div className="space-y-5">
                <div className="rounded-3xl border border-amber-200 bg-amber-50/80 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
                        {CHANGE_SET_SOURCE_LABEL[activeChangeSet.source]}
                      </p>
                      <p className="mt-2 text-lg font-semibold text-slate-950">{activeChangeSet.title}</p>
                    </div>
                    <span className="rounded-full border border-amber-200 bg-white px-3 py-1 text-xs font-semibold text-amber-900">
                      기준 버전 {activeChangeSet.baseVersion}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-700">{activeChangeSet.description}</p>
                  <p className="mt-3 text-xs text-slate-500">{formatDateTime(activeChangeSet.createdAt)}</p>
                </div>

                {activeChangeSet.patches.map((patch) => {
                  const selectedDecision = patchDecisions[patch.id];
                  const meta = CHANGE_TYPE_META[patch.changeType];
                  const originalSectionTitle = patch.originalSectionTitle ?? '';

                  return (
                    <article key={patch.id} className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            변경 섹션
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <p className="text-lg font-semibold text-slate-950">{patch.sectionTitle}</p>
                            <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${meta.className}`}>
                              {meta.label}
                            </span>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => handlePatchDecisionChange(patch.id, 'approved')}
                            className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${buildDecisionButtonClass(selectedDecision === 'approved', 'approve')}`}
                          >
                            승인
                          </button>
                          <button
                            type="button"
                            onClick={() => handlePatchDecisionChange(patch.id, 'rejected')}
                            className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${buildDecisionButtonClass(selectedDecision === 'rejected', 'reject')}`}
                          >
                            거절
                          </button>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-4 xl:grid-cols-2">
                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            변경 전
                          </p>
                          <p className="mt-3 text-sm font-semibold text-slate-900">
                            <HighlightedDiffText
                              originalText={originalSectionTitle}
                              proposedText={patch.sectionTitle}
                              variant="original"
                              emptyText="제목 없음"
                            />
                          </p>
                          <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-6 text-slate-700">
                            <HighlightedDiffText
                              originalText={patch.originalText}
                              proposedText={patch.proposedText}
                              variant="original"
                            />
                          </pre>
                        </div>
                        <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">
                            변경 후
                          </p>
                          <p className="mt-3 text-sm font-semibold text-slate-950">
                            <HighlightedDiffText
                              originalText={originalSectionTitle}
                              proposedText={patch.sectionTitle}
                              variant="proposed"
                              emptyText="삭제 섹션"
                            />
                          </p>
                          <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-6 text-slate-800">
                            <HighlightedDiffText
                              originalText={patch.originalText}
                              proposedText={patch.proposedText}
                              variant="proposed"
                            />
                          </pre>
                        </div>
                      </div>
                    </article>
                  );
                })}

                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => void handleApplyChangeSet()}
                    disabled={!activeChangeSet || submittingChangeSet}
                    className="rounded-full bg-navy-900 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-navy-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-600"
                  >
                    {submittingChangeSet ? '적용 중...' : '선택한 변경 적용'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </PageSection>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <PageSection title="법률적 근거" description="관련 법 조항과 적용 이유를 별도 패널로 강조합니다.">
          <div className="grid gap-4">
            {documentDetail.legalBasis.map((item) => (
              <LegalBasisCard key={item.id} item={item} />
            ))}
          </div>
        </PageSection>

        <PageSection title="버전 이력" description="공식 본문이 승인되어 반영된 이력만 버전으로 남깁니다.">
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
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <PageSection
          title="유저 피드백 및 질문 이력"
          description="문서 검토 피드백을 남기고, 반영 상태와 추가 질문 이력을 함께 관리합니다."
        >
          <div className="space-y-4 rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <div className="rounded-3xl border border-blue-100 bg-blue-50/60 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">유저 검토 피드백 등록</p>
              <p className="mt-3 text-sm leading-6 text-slate-700">
                문서 표현, 사실관계 보완, 위원회 제출용 문구 수정 요청을 남기면 승인 대기 수정안으로 제안됩니다.
              </p>
              <div className="mt-4 space-y-4">
                <label className="block">
                  <span className="form-label">피드백 제목</span>
                  <input
                    value={feedbackTitle}
                    onChange={(event) => setFeedbackTitle(event.target.value)}
                    className="form-input"
                    placeholder="예: 재발 방지 계획 문구 보완"
                  />
                </label>
                <label className="block">
                  <span className="form-label">피드백 내용</span>
                  <textarea
                    value={feedbackDescription}
                    onChange={(event) => setFeedbackDescription(event.target.value)}
                    rows={4}
                    className="form-textarea"
                    placeholder="예: 위원회 참고 자료에 교육 일정, 책임 부서, 지휘관 확인 의견을 더 구체적으로 반영해 주세요."
                  />
                </label>
                {feedbackError ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    {feedbackError}
                  </div>
                ) : null}
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => void handleFeedbackSubmit()}
                    disabled={submittingFeedback}
                    className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-600"
                  >
                    {submittingFeedback ? '등록 중...' : '피드백 등록'}
                  </button>
                </div>
              </div>
            </div>

            {documentDetail.reviewHistory.length === 0 && documentDetail.questions.length === 0 ? (
              <EmptyState
                title="기록된 보완 이력이 없습니다."
                description="이 문서는 아직 피드백이나 추가 질문 없이 유지되고 있습니다."
              />
            ) : (
              <>
                {documentDetail.reviewHistory.map((item) => (
                  <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="font-semibold text-slate-950">{item.title}</p>
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            item.status === 'open'
                              ? 'bg-amber-50 text-amber-800 ring-1 ring-amber-200'
                              : 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                          }`}
                        >
                          {item.status === 'open' ? '열림' : '종료'}
                        </span>
                        <span className="text-xs text-slate-500">{formatDateTime(item.createdAt)}</span>
                      </div>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                    {item.status === 'open' ? (
                      <p className="mt-4 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                        연결된 수정안은 상단 승인 패널에서 반영 여부를 결정합니다.
                      </p>
                    ) : null}
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

        <PageSection title="이전 수정안 기록" description="이미 적용되었거나 거절된 수정안 기록입니다.">
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            {changeSetHistoryItems.length === 0 ? (
              <EmptyState
                title="이전 수정안 기록이 없습니다."
                description="수정안이 적용되거나 거절되면 이 영역에 이력이 쌓입니다."
              />
            ) : (
              <div className="space-y-4">
                {changeSetHistoryItems.map((item) => (
                  <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                          {CHANGE_SET_SOURCE_LABEL[item.source]}
                        </p>
                        <p className="mt-2 font-semibold text-slate-950">{item.title}</p>
                      </div>
                      <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                        {item.status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                    <p className="mt-3 text-xs text-slate-500">
                      생성 {formatDateTime(item.createdAt)}
                      {item.appliedAt ? ` / 처리 ${formatDateTime(item.appliedAt)}` : ''}
                    </p>
                  </div>
                ))}
              </div>
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
        documentTitle={
          selectedQuestion
            ? caseDetail.documents.find((item) => item.id === selectedQuestion.documentId)?.title
            : undefined
        }
        isSubmitting={submitting}
        onClose={() => setSelectedQuestion(null)}
        onSubmit={(answer) => void handleSubmitAnswer(answer)}
      />
    </div>
  );
}
