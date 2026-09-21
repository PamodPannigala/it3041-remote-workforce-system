import React, { useState, useEffect } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import { updateCollaborationMessage } from "../collaborationApi";

const MAX_CONTENT_LENGTH = 4000;

export default function EditMessageModal({
  isOpen,
  onClose,
  message,
  onMessageUpdated,
  token,
  onSessionExpired,
}) {
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isOpen && message) {
      setContent(message.content || "");
      setError("");
    }
  }, [isOpen, message]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen || !message) return null;

  const trimmedContent = content.trim();
  const charCount = content.length;
  const isOverLimit = charCount > MAX_CONTENT_LENGTH;
  const isModified = trimmedContent !== (message.content || "").trim();
  const isValid = trimmedContent.length > 0 && !isOverLimit && isModified;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isValid || isSubmitting) return;

    setIsSubmitting(true);
    setError("");

    try {
      const updatedMessage = await updateCollaborationMessage(
        token,
        message.id,
        trimmedContent
      );
      if (onMessageUpdated) {
        onMessageUpdated(updatedMessage);
      }
      onClose();
    } catch (err) {
      if (err.status === 401 && onSessionExpired) {
        onSessionExpired();
      } else {
        setError(err.message || "Failed to update message. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-message-modal-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={!isSubmitting ? onClose : undefined}
        aria-hidden="true"
      />

      {/* Modal Dialog */}
      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-10 flex flex-col">
        {/* Header */}
        <div className="p-5 sm:p-6 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
            </div>
            <h3
              id="edit-message-modal-title"
              className="text-lg font-bold font-heading text-slate-900"
            >
              Edit Message
            </h3>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors disabled:opacity-50"
            aria-label="Close modal"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4">
          {error && (
            <Alert variant="error" onDismiss={() => setError("")}>
              {error}
            </Alert>
          )}

          <div className="space-y-1.5">
            <label
              htmlFor="edit-message-textarea"
              className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
            >
              Message Content <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="edit-message-textarea"
              rows={5}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={isSubmitting}
              maxLength={MAX_CONTENT_LENGTH}
              required
              className="w-full px-3.5 py-2.5 text-sm text-slate-900 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all disabled:bg-slate-50 resize-y"
            />
          </div>

          <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
            <span
              className={`font-mono font-medium ${
                isOverLimit
                  ? "text-rose-600 font-bold"
                  : charCount >= MAX_CONTENT_LENGTH * 0.9
                  ? "text-amber-600 font-semibold"
                  : "text-slate-500"
              }`}
            >
              {charCount} / {MAX_CONTENT_LENGTH}
            </span>
            {!isModified && trimmedContent.length > 0 && (
              <span className="text-slate-400 italic text-[11px]">No changes made</span>
            )}
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!isValid || isSubmitting}
              loading={isSubmitting}
            >
              Save Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
