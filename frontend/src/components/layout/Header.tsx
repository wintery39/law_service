import { NavLink } from 'react-router-dom';

const navLinkClassName = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-4 py-2 text-sm font-semibold transition ${
    isActive ? 'bg-navy-900 text-white shadow-soft' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
  }`;

export function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/60 bg-white/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-4 lg:px-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Military Legal Workflow
            </p>
            <h1 className="font-serif text-2xl font-semibold text-slate-950">LawFlow</h1>
          </div>
          <div className="rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-semibold text-blue-700">
            문서 흐름 데모 환경
          </div>
        </div>
        <nav className="flex flex-wrap items-center gap-2">
          <NavLink to="/" className={navLinkClassName} end>
            대시보드
          </NavLink>
          <NavLink to="/cases/new" className={navLinkClassName}>
            새 사건 등록
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
