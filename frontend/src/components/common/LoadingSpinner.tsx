export function LoadingSpinner({ message = '데이터를 불러오는 중입니다.' }: { message?: string }) {
  return (
    <div className="flex min-h-[240px] flex-col items-center justify-center gap-4 rounded-3xl border border-white/60 bg-white/80 p-8 text-center shadow-panel">
      <div className="h-11 w-11 animate-spin rounded-full border-4 border-slate-200 border-t-navy-700" />
      <div>
        <p className="text-sm font-semibold text-slate-900">MILO 처리 중</p>
        <p className="mt-1 text-sm text-slate-600">{message}</p>
      </div>
    </div>
  );
}
