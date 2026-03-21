import { createContext, useContext, useState, type ReactNode } from 'react';

type ToastTone = 'success' | 'error' | 'info';

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastContextValue {
  showToast: (toast: Omit<ToastItem, 'id'>) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const toneClassNames: Record<ToastTone, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
  info: 'border-blue-200 bg-blue-50 text-blue-900',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const value = {
    showToast(toast: Omit<ToastItem, 'id'>) {
      const id = Math.random().toString(36).slice(2, 10);
      const nextToast = { ...toast, id };

      setToasts((current) => [nextToast, ...current].slice(0, 4));

      window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.id !== id));
      }, 3200);
    },
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-full max-w-sm flex-col gap-3">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto rounded-2xl border px-4 py-3 shadow-soft backdrop-blur ${toneClassNames[toast.tone]}`}
          >
            <p className="text-sm font-semibold">{toast.title}</p>
            {toast.description ? <p className="mt-1 text-sm opacity-80">{toast.description}</p> : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);

  if (!context) {
    throw new Error('useToast는 ToastProvider 내부에서 사용해야 합니다.');
  }

  return context;
}
