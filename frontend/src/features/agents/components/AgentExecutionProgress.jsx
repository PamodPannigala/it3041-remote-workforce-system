import React from "react";
import Button from "../../../components/ui/Button";

export default function AgentExecutionProgress({
  onCancel,
  message = "Analyzing authorized workforce data...",
  subMessage = "Synthesizing domain telemetry and generating advisory insights. This may take a few moments.",
  className = "",
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`p-6 sm:p-8 rounded-xl border border-blue-200/80 bg-blue-50/40 text-slate-800 space-y-6 ${className}`}
      data-testid="agent-execution-progress"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-blue-600 text-white shrink-0 shadow-sm shadow-blue-500/20">
            <svg
              className="w-5 h-5 animate-spin motion-reduce:animate-none"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>

          <div>
            <h4 className="text-base font-bold text-slate-900 tracking-tight">
              {message}
            </h4>
            <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
              {subMessage}
            </p>
          </div>
        </div>

        {onCancel && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onCancel}
            className="self-start sm:self-center text-xs"
            aria-label="Cancel analysis request"
          >
            Cancel Analysis
          </Button>
        )}
      </div>

      {/* Structural Skeletons for layout stability */}
      <div className="space-y-3 pt-2">
        <div className="h-4 bg-slate-200/70 rounded-md w-3/4 animate-pulse motion-reduce:animate-none" />
        <div className="h-4 bg-slate-200/70 rounded-md w-5/6 animate-pulse motion-reduce:animate-none" />
        <div className="h-4 bg-slate-200/70 rounded-md w-1/2 animate-pulse motion-reduce:animate-none" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
        <div className="p-4 rounded-lg bg-white/70 border border-slate-200/70 space-y-2">
          <div className="h-3.5 bg-slate-200 rounded w-1/3 animate-pulse motion-reduce:animate-none" />
          <div className="h-3 bg-slate-200 rounded w-full animate-pulse motion-reduce:animate-none" />
          <div className="h-3 bg-slate-200 rounded w-4/5 animate-pulse motion-reduce:animate-none" />
        </div>
        <div className="p-4 rounded-lg bg-white/70 border border-slate-200/70 space-y-2">
          <div className="h-3.5 bg-slate-200 rounded w-1/3 animate-pulse motion-reduce:animate-none" />
          <div className="h-3 bg-slate-200 rounded w-full animate-pulse motion-reduce:animate-none" />
          <div className="h-3 bg-slate-200 rounded w-4/5 animate-pulse motion-reduce:animate-none" />
        </div>
      </div>
    </div>
  );
}
