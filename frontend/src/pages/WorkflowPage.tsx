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
import type { CaseDetail } from '../types/case';
import type { AsyncStatus } from '../types/common';
import { buildWorkflowSteps, type WorkflowStep } from '../utils/progress';

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
        const steps = buildWorkflowSteps(detail);
        const activeStep = steps.find((step) => step.active) ?? steps[0];
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
  const steps = buildWorkflowSteps(detail);
  const selectedStep = steps.find((step) => step.id === selectedStepId) ?? steps[0];

  function renderSelectedStepPanel(step: WorkflowStep) {
    switch (step.id) {
      case 'documents':
        return (
          <div className="grid gap-3">
            {detail.documents.map((document) => (
              <div key={document.id} className="rounded-2xl bg-slate-50 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold text-slate-950">{document.title}</p>
                  <StatusBadge type="document" value={document.status} />
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{document.description}</p>
              </div>
            ))}
          </div>
        );
      case 'question':
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
            title="추가 질문 기록이 없습니다."
            description="현재 사건은 별도 보완 질문 없이 문서 흐름이 진행되고 있습니다."
          />
        );
      case 'completed':
        return (
          <div className="rounded-3xl bg-slate-50 p-5">
            <p className="text-sm leading-7 text-slate-700">
              완료 문서 {detail.documents.filter((document) => document.status === 'completed').length}건,
              생성 중 또는 입력 대기 문서 {detail.documents.filter((document) => document.status !== 'completed').length}
              건입니다. 모든 문서가 완료되면 사건 상태가 자동으로 완료로 전환됩니다.
            </p>
          </div>
        );
      case 'submitted':
        return (
          <div className="rounded-3xl bg-slate-50 p-5">
            <p className="text-sm leading-7 text-slate-700">{detail.legalReviewSummary}</p>
          </div>
        );
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
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Workflow Visualizer</p>
            <h2 className="mt-2 font-serif text-4xl font-semibold text-slate-950">{detail.title}</h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">
              사건 등록부터 법무관 제출 직전까지의 흐름을 한눈에 보여주는 발표용 시각화 화면입니다.
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
        description="사건 입력, 문서 생성, 추가 질문, 문서 완성, 제출 단계가 순서대로 연결됩니다."
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
          description="선택한 단계의 핵심 설명과 관련 데이터를 확인할 수 있습니다."
        >
          <div className="rounded-[32px] border border-white/60 bg-white/95 p-6 shadow-soft">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{selectedStep.caption}</p>
            <p className="mt-3 text-lg font-semibold text-slate-950">{selectedStep.description}</p>
            <p className="mt-3 text-sm leading-7 text-slate-600">{selectedStep.detail}</p>
            <div className="mt-6">{renderSelectedStepPanel(selectedStep)}</div>
          </div>
        </PageSection>

        <PageSection title="요약 지점" description="발표 시 설명 포인트를 빠르게 꺼낼 수 있도록 핵심 상태를 정리했습니다.">
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
            <div className="rounded-2xl bg-blue-50/70 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">발표 포인트</p>
              <p className="mt-3 text-sm leading-7 text-slate-700">
                이 화면은 단순 문서 편집기가 아니라 사건 전체 처리 절차를 안내하는 시스템이라는 점을 보여주기 위한 데모 장면입니다.
              </p>
            </div>
          </div>
        </PageSection>
      </div>
    </div>
  );
}
