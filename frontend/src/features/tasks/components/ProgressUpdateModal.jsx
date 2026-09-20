import React, { useState, useEffect } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";

export default function ProgressUpdateModal({
  task,
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  error = "",
}) {
  const [percentage, setPercentage] = useState(50);
  const [notes, setNotes] = useState("");
  const [clientError, setClientError] = useState("");

  useEffect(() => {
    if (isOpen && task) {
      const latest =
        task.progress_history && task.progress_history.length > 0
          ? task.progress_history[task.progress_history.length - 1].percentage
          : 0;
      setPercentage(latest);
      setNotes("");
      setClientError("");
    }
  }, [isOpen, task]);

  if (!isOpen || !task) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setClientError("");

    const parsed = parseInt(percentage, 10);
    if (isNaN(parsed) || parsed < 0 || parsed > 100) {
      setClientError("Percentage must be an integer between 0 and 100.");
      return;
    }

    const trimmedNotes = notes.trim();
    if (!trimmedNotes) {
      setClientError("Progress notes are required.");
      return;
    }
    if (trimmedNotes.length > 1000) {
      setClientError("Notes cannot exceed 1000 characters.");
      return;
    }

    onSubmit({
      percentage: parsed,
      notes: trimmedNotes,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="progress-modal-title"
    >
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={isSubmitting ? undefined : onClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200/80 z-10 overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-slate-200/80 flex items-center justify-between bg-slate-50/50">
          <div>
            <h3 id="progress-modal-title" className="text-base font-bold text-slate-900 font-heading">
              Log Progress Update
            </h3>
            <p className="text-xs text-slate-500 mt-0.5 truncate max-w-sm">
              {task.title}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
            aria-label="Close progress modal"
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

          {/* Slider & Numeric input */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label htmlFor="progress-percentage-input" className="text-xs font-semibold uppercase tracking-wider text-slate-700">
                Completion Percentage <span className="text-rose-500">*</span>
              </label>
              <span className="text-sm font-bold text-blue-600 font-mono">
                {percentage}%
              </span>
            </div>

            <input
              id="progress-percentage-range"
              type="range"
              min="0"
              max="100"
              step="5"
              value={percentage}
              onChange={(e) => setPercentage(Number(e.target.value))}
              disabled={isSubmitting}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <label htmlFor="progress-notes-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
              Update Notes <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="progress-notes-input"
              required
              rows={4}
              maxLength={1000}
              placeholder="Describe what was accomplished, milestones met, or remaining steps..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              disabled={isSubmitting}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 resize-y"
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
              id="submit-progress-btn"
              type="submit"
              variant="primary"
              size="sm"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Logging Progress..." : "Submit Progress"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
