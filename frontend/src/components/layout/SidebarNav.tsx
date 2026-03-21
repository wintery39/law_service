import { NavLink } from 'react-router-dom';

const sidebarLinkClassName = ({ isActive }: { isActive: boolean }) =>
  `flex items-center justify-between rounded-2xl px-4 py-3 text-sm font-semibold transition ${
    isActive
      ? 'bg-navy-900 text-white shadow-soft'
      : 'text-slate-600 hover:bg-white hover:text-slate-950 hover:shadow-soft'
  }`;

export function SidebarNav() {
  return (
    <aside className="hidden w-72 shrink-0 lg:block">
      <div className="sticky top-24 space-y-6">
        <div className="rounded-3xl border border-white/60 bg-white/90 p-4 shadow-soft">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Navigation</p>
          <nav className="mt-4 space-y-2">
            <NavLink to="/" className={sidebarLinkClassName} end>
              <span>사건 현황</span>
              <span>01</span>
            </NavLink>
            <NavLink to="/cases/new" className={sidebarLinkClassName}>
              <span>사건 등록</span>
              <span>02</span>
            </NavLink>
          </nav>
        </div>
        <div className="rounded-3xl border border-navy-800 bg-gradient-to-br from-navy-950 via-navy-900 to-blue-800 p-5 text-white shadow-panel">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/70">Demo Focus</p>
          <h2 className="mt-3 font-serif text-2xl font-semibold">복잡한 절차를 단계별로 정리합니다.</h2>
          <p className="mt-3 text-sm leading-6 text-white/80">
            사건 등록, 문서 생성, 추가 질문, 제출 직전 상태까지 한 흐름으로 설명할 수 있게 구성했습니다.
          </p>
        </div>
      </div>
    </aside>
  );
}
