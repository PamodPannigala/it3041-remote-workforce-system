import React, { useState, useEffect } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";

export default function ResolveBlockerModal({
  isOpen,
  onClose,
  onSubmit,
  task,
  blocker,
  isSubmitting = false,
  error = "",
}) {
  const [resolutionNote, setResolutionNote] = useState("");
  const [clientError, setClientError] = useState("");

  useEffect(() => {
    if (isOpen) {
      setResolutionNote("");
      setClientError("");
    }
  }, [isOpen, blocker]);

  if (!isOpen || !task || !blocker) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setClientError("");

    const trimmed = resolutionNote.trim();
    if (!trimmed) {
      setClientError("Resolution note is required to resolve this blocker.");
      return;
    }
    if (trimmed.length > 1000) {
      setClientError("Resolution note cannot exceed 1000 characters.");
      return;
    }

    onSubmit(task.id, blocker.id, trimmed);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="resolve-blocker-modal-title"
    >
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={isSubmitting ? undefined : onClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200/80 z-10 overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-slate-200/80 flex items-center justify-between bg-emerald-50/60">
          <div>
            <h3
              id="resolve-blocker-modal-title"
              className="text-base font-bold text-emerald-950 font-heading flex items-center gap-2"
            >
              <span>✓</span> Resolve Task Blocker
            </h3>
            <p className="text-xs text-emerald-700/80 mt-0.5 truncate max-w-sm">
              {task.title}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors disabled:opacity-50"
            aria-label="Close resolve blocker modal"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {(error || clientError) && (
            <Alert variant="error" onDismiss={() => setClientError("")}>
              {clientError || error}
            </Alert>
          )}

          {/* Original Blocker Description */}
          <div className="p-3.5 rounded-xl bg-rose-50/70 border border-rose-200/80 space-y-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-rose-800">
              Original Blocker Description:
            </span>
            <p className="text-xs text-rose-950 leading-relaxed break-words">
              {blocker.description}
            </p>
          </div>

          {/* Resolution Note Input */}
          <div className="space-y-1.5">
            <label
              htmlFor="resolution-note-input"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            >
              Resolution Note <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="resolution-note-input"
              required
              rows={4}
              maxLength={1000}
              placeholder="Explain how the obstacle was addressed, dependencies unblocked, or next steps..."
              value={resolutionNote}
              onChange={(e) => setResolutionNote(e.target.value)}
              disabled={isSubmitting}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 resize-y"
            />
            <p className="text-[11px] text-slate-500">
              Resolving this blocker will return the task to In Progress when no active blockers remain.
            </p>
          </div>

          {/* Actions */}
          <div className="pt-2 flex items-center justify-end gap-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              id="confirm-resolve-blocker-btn"
              type="submit"
              variant="primary"
              size="sm"
              disabled={isSubmitting || !resolutionNote.trim()}
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {isSubmitting ? "Resolving Blocker..." : "Confirm Blocker Resolution"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
