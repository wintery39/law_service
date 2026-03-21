import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { PageSection } from '../components/common/PageSection';
import { SearchFilterBar } from '../components/common/SearchFilterBar';
import { SummaryCard } from '../components/common/SummaryCard';
import { CaseTable } from '../components/dashboard/CaseTable';
import { caseService } from '../services/caseService';
import type { CaseSummary } from '../types/case';
import type { AsyncStatus, CaseStatus, CaseType, DashboardMetrics } from '../types/common';

const initialMetrics: DashboardMetrics = {
  totalCases: 0,
  inProgressCases: 0,
  completedCases: 0,
  waitingCases: 0,
};

export default function DashboardPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics>(initialMetrics);
  const [status, setStatus] = useState<AsyncStatus>('loading');
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [caseType, setCaseType] = useState<CaseType | 'all'>('all');
  const [caseStatus, setCaseStatus] = useState<CaseStatus | 'all'>('all');

  useEffect(() => {
    let active = true;

    async function load() {
      setStatus('loading');
      setError('');

      try {
        const [caseList, caseMetrics] = await Promise.all([
          caseService.getCases(),
          caseService.getCaseMetrics(),
        ]);

        if (!active) {
          return;
        }

        setCases(caseList);
        setMetrics(caseMetrics);
        setStatus('success');
      } catch (loadError) {
        if (!active) {
          return;
        }

        setError(
          loadError instanceof Error ? loadError.message : '대시보드 데이터를 불러오는 중 오류가 발생했습니다.',
        );
        setStatus('error');
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, []);

  const filteredCases = cases.filter((item) => {
    const matchesSearch =
      search.trim().length === 0 ||
      item.title.toLowerCase().includes(search.toLowerCase()) ||
      item.summary.toLowerCase().includes(search.toLowerCase());
    const matchesCaseType = caseType === 'all' || item.caseType === caseType;
    const matchesStatus = caseStatus === 'all' || item.status === caseStatus;

    return matchesSearch && matchesCaseType && matchesStatus;
  });

  if (status === 'loading') {
    return <LoadingSpinner message="사건 목록과 요약 지표를 불러오는 중입니다." />;
  }

  if (status === 'error') {
    return <ErrorState description={error} onRetry={() => window.location.reload()} />;
  }

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-white/50 bg-gradient-to-br from-navy-950 via-navy-900 to-blue-800 p-6 text-white shadow-panel lg:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/70">
              군 내 법률 문서 생성 지원 서비스
            </p>
            <h2 className="mt-3 font-serif text-4xl font-semibold leading-tight lg:text-5xl">
              복잡한 사건 처리 흐름을 문서 중심으로 정리합니다.
            </h2>
            <p className="mt-4 text-sm leading-7 text-white/80 lg:text-base">
              사건 등록부터 문서 생성, 추가 질문, 최종 제출 직전 상태까지 한 화면에서 확인할 수 있도록 구성했습니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/cases/new"
              className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-navy-900 transition hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              새 사건 생성
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="전체 사건"
          value={metrics.totalCases}
          description="현재 데모 환경에 적재된 전체 사건 수"
          accent="navy"
        />
        <SummaryCard
          title="진행 중"
          value={metrics.inProgressCases}
          description="문서 생성과 검토가 계속 진행 중인 사건"
          accent="slate"
        />
        <SummaryCard
          title="문서 완료"
          value={metrics.completedCases}
          description="제출 직전 수준까지 정리된 사건"
          accent="emerald"
        />
        <SummaryCard
          title="추가 질문 대기"
          value={metrics.waitingCases}
          description="LLM이 추가 입력을 요청하고 있는 사건"
          accent="amber"
        />
      </div>

      <PageSection
        title="사건 목록"
        description="사건명, 유형, 상태, 진행률을 기준으로 전체 현황을 빠르게 파악할 수 있습니다."
      >
        <SearchFilterBar
          search={search}
          caseType={caseType}
          status={caseStatus}
          resultCount={filteredCases.length}
          onSearchChange={setSearch}
          onCaseTypeChange={setCaseType}
          onStatusChange={setCaseStatus}
        />

        {cases.length === 0 ? (
          <EmptyState
            title="등록된 사건이 없습니다."
            description="첫 사건을 등록하면 문서 생성 흐름과 질문 응답 화면을 바로 확인할 수 있습니다."
            action={
              <Link
                to="/cases/new"
                className="rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-white"
              >
                사건 등록하러 가기
              </Link>
            }
          />
        ) : filteredCases.length === 0 ? (
          <EmptyState
            title="조건에 맞는 사건이 없습니다."
            description="검색어나 필터를 조정하면 다른 사건을 확인할 수 있습니다."
          />
        ) : (
          <CaseTable cases={filteredCases} />
        )}
      </PageSection>
    </div>
  );
}
