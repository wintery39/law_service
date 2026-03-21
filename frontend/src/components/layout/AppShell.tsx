import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { SidebarNav } from './SidebarNav';

export function AppShell() {
  return (
    <div className="min-h-screen bg-[#eff4fb] bg-grid-soft bg-[size:24px_24px]">
      <div className="absolute inset-x-0 top-0 -z-10 h-[420px] bg-[radial-gradient(circle_at_top_left,rgba(29,78,216,0.16),transparent_35%),radial-gradient(circle_at_top_right,rgba(14,165,233,0.12),transparent_32%),linear-gradient(180deg,#0f172a_0%,#eaf1fb_55%,#eff4fb_100%)]" />
      <Header />
      <div className="mx-auto flex max-w-[1600px] gap-8 px-4 py-6 lg:px-8">
        <SidebarNav />
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
