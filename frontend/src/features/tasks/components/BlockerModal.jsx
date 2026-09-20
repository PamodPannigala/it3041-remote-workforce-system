import React, { useState, useEffect } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";

export default function BlockerModal({
  task,
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  error = "",
}) {
  const [description, setDescription] = useState("");
  const [clientError, setClientError] = useState("");

  useEffect(() => {
    if (isOpen) {
      setDescription("");
      setClientError("");
    }
  }, [isOpen]);

  if (!isOpen || !task) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setClientError("");

    const trimmed = description.trim();
    if (!trimmed) {
      setClientError("Blocker description is required.");
      return;
    }
    if (trimmed.length > 1000) {
      setClientError("Description cannot exceed 1000 characters.");
      return;
    }

    onSubmit({ description: trimmed });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="blocker-modal-title"
    >
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={isSubmitting ? undefined : onClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200/80 z-10 overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-slate-200/80 flex items-center justify-between bg-rose-50/60">
          <div>
            <h3 id="blocker-modal-title" className="text-base font-bold text-rose-950 font-heading flex items-center gap-2">
              <span>⛔</span> Report Task Blocker
            </h3>
            <p className="text-xs text-rose-700/80 mt-0.5 truncate max-w-sm">
              {task.title}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
            aria-label="Close blocker modal"
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

          <p className="text-xs text-slate-600 leading-relaxed">
            Reporting a blocker will notify your manager and automatically mark this task as{" "}
            <span className="font-semibold text-rose-700">Blocked</span> until the obstacle is resolved.
          </p>

          <div className="space-y-1.5">
            <label htmlFor="blocker-description-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
              Blocker Description <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="blocker-description-input"
              required
              rows={4}
              maxLength={1000}
              placeholder="Detail the technical blocker, external dependency, or missing requirements..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-rose-500/40 focus:border-rose-500 resize-y"
            />
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
              id="submit-blocker-btn"
              type="submit"
              variant="dangerOutline"
              size="sm"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Reporting Blocker..." : "Submit Blocker"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
