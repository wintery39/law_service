import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { PageSection } from '../components/common/PageSection';
import { ProgressBar } from '../components/common/ProgressBar';
import { StatusBadge } from '../components/common/StatusBadge';
import { WorkflowStepper } from '../components/workflow/WorkflowStepper';
import { caseService } from '../services/caseService';
import type { CaseDetail, WorkflowStage } from '../types/case';
import type { AsyncStatus } from '../types/common';

export default function WorkflowPage() {
  const { caseId = '' } = useParams();
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [status, setStatus] = useState<AsyncStatus>('loading');
  const [error, setError] = useState('');
  const [selectedStepId, setSelectedStepId] = useState('');

  useEffect(() => {
    let active = true;

    async function loadWorkflow() {
      setStatus('loading');
      setError('');

      try {
        const detail = await caseService.getCaseById(caseId);
        if (!active) {
          return;
        }

        setCaseDetail(detail);
        const activeStep =
          detail.workflowStages.find((step) => step.id === 'review_feedback' && step.status === 'active') ??
          detail.workflowStages.find((step) => step.status === 'active') ??
          [...detail.workflowStages].reverse().find((step) => step.status === 'completed') ??
          detail.workflowStages[0];
        setSelectedStepId(activeStep.id);
        setStatus('success');
      } catch (loadError) {
        if (!active) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : '워크플로우를 불러오지 못했습니다.');
        setStatus('error');
      }
    }

    void loadWorkflow();

    return () => {
      active = false;
    };
  }, [caseId]);

  if (status === 'loading') {
    return <LoadingSpinner message="전체 문서 흐름과 현재 단계를 정리하는 중입니다." />;
  }

  if (status === 'error' || !caseDetail) {
    return <ErrorState description={error} onRetry={() => window.location.reload()} />;
  }

  const detail = caseDetail;
  const steps = detail.workflowStages;
  const selectedStep = steps.find((step) => step.id === selectedStepId) ?? steps[0];

  function renderSelectedStepPanel(step: WorkflowStage) {
    switch (step.id) {
      case 'attachment_registration':
        return (
          <div className="rounded-3xl bg-slate-50 p-5">
            <p className="text-sm leading-7 text-slate-700">
              {detail.attachmentProvided
                ? detail.attachmentSummary
                : '첨부 자료 없이 진행 중이며, 이후 필요한 경우 문서 생성 단계에서 추가 자료 요청이 연결됩니다.'}
            </p>
          </div>
        );
      case 'information_request':
        return detail.questions.length > 0 ? (
          <div className="grid gap-3">
            {detail.questions.map((question) => (
              <div key={question.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold text-slate-950">{question.title}</p>
                  <StatusBadge type="question" value={question.status} />
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{question.reason}</p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="추가 정보 요청이 없습니다."
            description="현재 사건은 별도 보완 질문 없이 문서 생성 단계로 진행 중입니다."
          />
        );
      case 'document_generation':
        return (
          <div className="grid gap-3">
            {detail.documents.map((document) => (
              <div key={document.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold text-slate-950">{document.title}</p>
                  <StatusBadge type="document" value={document.status} />
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{document.description}</p>
                {document.activeChangeSet ? (
                  <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
                    승인 대기 섹션 {document.activeChangeSet.patches.length}건
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        );
      case 'review_feedback': {
        const reviewItems = detail.documents.flatMap((document) =>
          document.reviewHistory.map((item) => ({
            ...item,
            documentId: document.id,
            documentTitle: document.title,
          })),
        );

        return reviewItems.length > 0 ? (
          <div className="grid gap-3">
            {reviewItems.map((item) => (
              <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold text-slate-950">{item.title}</p>
                  <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600">
                    {item.status === 'open' ? '피드백 대기' : '반영 완료'}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                <p className="mt-3 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                  {item.documentTitle}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="검토 또는 피드백 이력이 없습니다."
            description="문서 생성이 끝나면 검토 요청과 반영 이력이 이곳에 정리됩니다."
          />
        );
      }
      default:
        return (
          <div className="rounded-3xl bg-slate-50 p-5">
            <p className="text-sm leading-7 text-slate-700">{step.detail}</p>
          </div>
        );
    }
  }

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-panel">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">사건 진행 현황</p>
            <h2 className="mt-2 font-serif text-4xl font-semibold text-slate-950">{detail.title}</h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">
              사건 처리 단계와 관련 문서, 검토 이력을 한눈에 확인할 수 있는 화면입니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to={`/cases/${detail.id}`}
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
            >
              사건 상세 보기
            </Link>
          </div>
        </div>
        <div className="mt-6 rounded-3xl bg-slate-50 p-5">
          <ProgressBar value={detail.progressPercent} label="현재 워크플로우 완성도" />
        </div>
      </section>

      <PageSection
        title="전체 문서 흐름"
        description="사건 등록부터 문서 생성, 검토와 피드백 반영까지의 진행 단계를 정리했습니다."
      >
        <WorkflowStepper
          steps={steps}
          selectedStepId={selectedStepId}
          onSelect={setSelectedStepId}
        />
      </PageSection>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <PageSection
          title={selectedStep.title}
          description="선택한 단계의 설명과 관련 데이터를 확인할 수 있습니다."
        >
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{selectedStep.caption}</p>
            <p className="mt-3 text-lg font-semibold text-slate-950">{selectedStep.description}</p>
            <p className="mt-3 text-sm leading-7 text-slate-600">{selectedStep.detail}</p>
            <div className="mt-6">{renderSelectedStepPanel(selectedStep)}</div>
          </div>
        </PageSection>

        <PageSection title="요약 정보" description="사건 처리 현황을 빠르게 확인할 수 있도록 핵심 상태를 정리했습니다.">
          <div className="space-y-4 rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <div className="rounded-2xl bg-slate-50 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">현재 사건 상태</p>
              <div className="mt-3">
                <StatusBadge type="case" value={detail.status} />
              </div>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">문서 수</p>
              <p className="mt-3 text-2xl font-semibold text-slate-950">{detail.documents.length}건</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">추가 질문 수</p>
              <p className="mt-3 text-2xl font-semibold text-slate-950">{detail.questions.length}건</p>
            </div>
          </div>
        </PageSection>
      </div>
    </div>
  );
}
