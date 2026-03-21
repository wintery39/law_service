import type { WorkflowStep } from '../../utils/progress';

interface WorkflowStepperProps {
  steps: WorkflowStep[];
  selectedStepId: string;
  onSelect: (stepId: string) => void;
}

export function WorkflowStepper({ steps, selectedStepId, onSelect }: WorkflowStepperProps) {
  return (
    <div className="grid gap-4 xl:grid-cols-6">
      {steps.map((step, index) => {
        const isSelected = selectedStepId === step.id;

        return (
          <button
            key={step.id}
            type="button"
            onClick={() => onSelect(step.id)}
            className={`relative rounded-3xl border px-4 py-5 text-left shadow-soft transition ${
              isSelected
                ? 'border-navy-900 bg-navy-900 text-white'
                : step.completed
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-950'
                  : step.active
                    ? 'border-amber-200 bg-amber-50 text-amber-950'
                    : 'border-white/60 bg-white/90 text-slate-900'
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">{step.caption}</span>
              <span
                className={`inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${
                  isSelected
                    ? 'bg-white/20'
                    : step.completed
                      ? 'bg-emerald-200/70 text-emerald-900'
                      : step.active
                        ? 'bg-amber-200/70 text-amber-900'
                        : 'bg-slate-100 text-slate-700'
                }`}
              >
                {index + 1}
              </span>
            </div>
            <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
            <p className="mt-2 text-sm leading-6 opacity-85">{step.description}</p>
          </button>
        );
      })}
    </div>
  );
}
