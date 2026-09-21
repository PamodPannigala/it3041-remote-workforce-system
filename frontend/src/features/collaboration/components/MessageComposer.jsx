import React, { useState } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import { createCollaborationMessage } from "../collaborationApi";

const MAX_CONTENT_LENGTH = 4000;

export default function MessageComposer({
  teamId,
  token,
  onMessageSent,
  onSessionExpired,
  disabled = false,
  placeholder = "Write a message or update to your team...",
}) {
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const trimmedContent = content.trim();
  const charCount = content.length;
  const isOverLimit = charCount > MAX_CONTENT_LENGTH;
  const isValid = trimmedContent.length > 0 && !isOverLimit;

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!isValid || isSubmitting || disabled) return;

    setIsSubmitting(true);
    setError("");

    try {
      const createdMessage = await createCollaborationMessage(token, {
        teamId,
        content: trimmedContent,
      });
      setContent("");
      if (onMessageSent) {
        onMessageSent(createdMessage);
      }
    } catch (err) {
      if (err.status === 401 && onSessionExpired) {
        onSessionExpired();
      } else {
        setError(err.message || "Failed to post message. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="p-4 sm:p-5 rounded-xl bg-white border border-slate-200/80 shadow-sm space-y-3">
      {error && (
        <Alert variant="error" onDismiss={() => setError("")}>
          {error}
        </Alert>
      )}

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="relative">
          <label htmlFor="team-message-composer" className="sr-only">
            Compose message to team
          </label>
          <textarea
            id="team-message-composer"
            rows={3}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled || isSubmitting}
            maxLength={MAX_CONTENT_LENGTH}
            placeholder={placeholder}
            aria-label="Compose team message"
            className="w-full px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 bg-slate-50/70 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 focus:bg-white transition-all disabled:opacity-60 disabled:cursor-not-allowed resize-y"
          />
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between gap-2.5 pt-1">
          <div className="flex items-center gap-2 text-xs text-slate-500">
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
            <span className="hidden sm:inline text-slate-400">•</span>
            <span className="hidden sm:inline text-[11px] text-slate-400">
              Press Ctrl + Enter to send
            </span>
          </div>

          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!isValid || isSubmitting || disabled}
            loading={isSubmitting}
            className="w-full sm:w-auto"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
            }
          >
            Send Message
          </Button>
        </div>
      </form>
    </div>
  );
}
