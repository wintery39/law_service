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
      <div className="sticky top-24">
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
      </div>
    </aside>
  );
}
