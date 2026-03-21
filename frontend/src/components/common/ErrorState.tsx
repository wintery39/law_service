interface ErrorStateProps {
  title?: string;
  description: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = '데이터를 불러오지 못했습니다.',
  description,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="rounded-3xl border border-rose-200 bg-rose-50/80 px-6 py-10 text-center shadow-soft">
      <p className="text-lg font-semibold text-rose-900">{title}</p>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-rose-800/80">{description}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 rounded-full bg-rose-700 px-5 py-2 text-sm font-semibold text-white transition hover:bg-rose-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-700"
        >
          다시 시도
        </button>
      ) : null}
    </div>
  );
}
