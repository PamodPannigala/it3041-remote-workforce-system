import { sanitizePublicText } from "../publicProse";
import React from "react";
import Button from "../../../components/ui/Button";

export default function AgentErrorPanel({
  error,
  onRetry = null,
  onDismiss = null,
  onClearTaskContext = null,
  className = "",
}) {
  if (!error) return null;

  const rawErrorMessage =
    typeof error === "string"
      ? error
      : error?.message || "An unexpected error occurred during agent analysis.";

  const errorMessage = sanitizePublicText(rawErrorMessage);

  const isAbort =
    error?.name === "AbortError" ||
    (errorMessage && (errorMessage.toLowerCase().includes("abort") || errorMessage.toLowerCase().includes("cancel")));

  const isIrrelevantTaskContext =
    rawErrorMessage.includes("target_task_id is not permitted") ||
    error?.error_code === "IRRELEVANT_CONTEXT_REJECTED";

  const title = isAbort
    ? "Analysis Request Cancelled"
    : isIrrelevantTaskContext
    ? "Incompatible Task Context"
    : error?.status === 403
    ? "Permission Denied"
    : error?.status === 503
    ? "AI Specialist Service Unavailable"
    : error?.status === 504
    ? "Analysis Request Timed Out"
    : "Unable to Complete Workforce Analysis";

  const isWarningOnly = isAbort;

  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="agent-error-panel"
      className={`p-5 rounded-xl border ${
        isWarningOnly
          ? "bg-slate-50 border-slate-300 text-slate-800"
          : "bg-rose-50/90 border-rose-200 text-rose-950"
      } shadow-sm space-y-3 ${className}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`shrink-0 mt-0.5 ${
            isWarningOnly ? "text-slate-600" : "text-rose-600"
          }`}
        >
          {isWarningOnly ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm tracking-tight">{title}</h4>
          <p className="text-sm mt-1 leading-relaxed text-slate-700 break-words">
            {errorMessage}
          </p>

          {!isAbort && (
            <p className="text-xs text-slate-500 mt-2">
              Your inputs have been preserved. You can adjust your query or retry the request.
            </p>
          )}
        </div>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="shrink-0 p-1 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-black/5 transition-colors"
            aria-label="Dismiss message"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="pt-2 flex flex-wrap items-center gap-3">
        {onClearTaskContext && isIrrelevantTaskContext && (
          <Button
            variant="outline"
            size="sm"
            onClick={onClearTaskContext}
            data-testid="clear-incompatible-task-btn"
            className="text-rose-700 border-rose-300 hover:bg-rose-100"
          >
            Clear Incompatible Task Context
          </Button>
        )}

        {onRetry && !isAbort && (
          <Button
            variant="primary"
            size="sm"
            onClick={onRetry}
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            }
          >
            Retry Request
          </Button>
        )}
      </div>
    </div>
  );
}
