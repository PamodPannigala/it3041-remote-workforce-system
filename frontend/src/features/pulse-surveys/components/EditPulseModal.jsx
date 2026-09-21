import React, { useState, useEffect } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import PulseRatingField from "./PulseRatingField";
import { updatePulseSurveyResponse } from "../pulseSurveysApi";

const MAX_COMMENT_LENGTH = 1000;

export default function EditPulseModal({
  isOpen,
  onClose,
  response,
  token,
  onResponseUpdated,
  onSessionExpired,
}) {
  if (!isOpen || !response) return null;

  const [ratings, setRatings] = useState({
    workload_manageability: response.workload_manageability ?? null,
    work_life_balance: response.work_life_balance ?? null,
    team_support: response.team_support ?? null,
    engagement: response.engagement ?? null,
  });
  const [optionalComment, setOptionalComment] = useState(response.optional_comment || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (response) {
      setRatings({
        workload_manageability: response.workload_manageability ?? null,
        work_life_balance: response.work_life_balance ?? null,
        team_support: response.team_support ?? null,
        engagement: response.engagement ?? null,
      });
      setOptionalComment(response.optional_comment || "");
      setError("");
    }
  }, [response]);

  const isFormComplete =
    ratings.workload_manageability !== null &&
    ratings.work_life_balance !== null &&
    ratings.team_support !== null &&
    ratings.engagement !== null;

  const handleRatingChange = (field, val) => {
    setRatings((prev) => ({ ...prev, [field]: val }));
    setError("");
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!isFormComplete || submitting) return;

    setSubmitting(true);
    setError("");

    try {
      const updated = await updatePulseSurveyResponse(token, response.id, {
        workload_manageability: ratings.workload_manageability,
        work_life_balance: ratings.work_life_balance,
        team_support: ratings.team_support,
        engagement: ratings.engagement,
        optional_comment: optionalComment.trim() || null,
        expected_revision: response.revision ?? 1,
      });

      if (onResponseUpdated) {
        onResponseUpdated(updated);
      }
      onClose();
    } catch (err) {
      if (err.status === 401 && onSessionExpired) {
        onSessionExpired();
      } else if (err.status === 400 && err.message?.includes("Previous-week")) {
        setError("The current UTC week has ended. Previous-week responses are read-only.");
      } else if (err.status === 409) {
        setError(err.message || "Conflict: This pulse survey response was modified concurrently. Please refresh the page to view the latest response before retrying.");
      } else {
        setError(err.message || "Failed to update pulse survey response.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-pulse-dialog-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={!submitting ? onClose : undefined}
        aria-hidden="true"
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-10 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-5 sm:p-6 border-b border-slate-200 flex items-center justify-between shrink-0 bg-slate-50">
          <div>
            <h3
              id="edit-pulse-dialog-title"
              className="text-lg font-bold font-heading text-slate-900"
            >
              Edit Weekly Pulse Check-In
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Update your ratings and personal reflections for the current week.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
            aria-label="Close edit pulse dialog"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable Form Body */}
        <form onSubmit={handleSave} className="p-5 sm:p-6 space-y-4 overflow-y-auto flex-1">
          <div className="p-3.5 rounded-xl bg-blue-50/70 border border-blue-200/80 text-xs text-slate-700 leading-relaxed">
            <p className="font-semibold text-blue-950 mb-0.5">Current Week Edit Policy</p>
            <p>
              You can edit your response until the current UTC week ends. Previous weeks are read-only.
            </p>
          </div>

          {error && (
            <Alert variant="error" onDismiss={() => setError("")}>
              {error}
            </Alert>
          )}

          {/* Metric 1 */}
          <PulseRatingField
            id="edit-pulse-workload"
            label="1. Workload Manageability"
            description="How manageable was your assigned workload and task volume this week?"
            lowLabel="Overwhelming / Unmanageable"
            highLabel="Balanced / Fully Manageable"
            value={ratings.workload_manageability}
            onChange={(val) => handleRatingChange("workload_manageability", val)}
            disabled={submitting}
          />

          {/* Metric 2 */}
          <PulseRatingField
            id="edit-pulse-balance"
            label="2. Work-Life Balance"
            description="How well were you able to maintain healthy boundaries between work and personal time?"
            lowLabel="Poor / Strained"
            highLabel="Healthy / Excellent"
            value={ratings.work_life_balance}
            onChange={(val) => handleRatingChange("work_life_balance", val)}
            disabled={submitting}
          />

          {/* Metric 3 */}
          <PulseRatingField
            id="edit-pulse-support"
            label="3. Team Support"
            description="Did you feel supported by team members and have the collaboration needed to make progress?"
            lowLabel="Isolated / Minimal Support"
            highLabel="Strong Collaboration / Highly Supported"
            value={ratings.team_support}
            onChange={(val) => handleRatingChange("team_support", val)}
            disabled={submitting}
          />

          {/* Metric 4 */}
          <PulseRatingField
            id="edit-pulse-engagement"
            label="4. Engagement"
            description="How energized and engaged did you feel regarding your work and accomplishments?"
            lowLabel="Disengaged / Low Energy"
            highLabel="Energized / Highly Engaged"
            value={ratings.engagement}
            onChange={(val) => handleRatingChange("engagement", val)}
            disabled={submitting}
          />

          {/* Optional Comment */}
          <div className="space-y-1.5 p-4 rounded-xl bg-slate-50/80 border border-slate-200/80">
            <div className="flex items-center justify-between">
              <label
                htmlFor="edit-pulse-optional-comment"
                className="text-sm font-bold text-slate-900 font-heading"
              >
                Confidential Personal Note <span className="text-xs font-normal text-slate-500">(Optional)</span>
              </label>
              <span
                className={`text-xs ${
                  optionalComment.length > MAX_COMMENT_LENGTH * 0.9
                    ? "text-rose-600 font-bold"
                    : "text-slate-400"
                }`}
              >
                {optionalComment.length} / {MAX_COMMENT_LENGTH} chars
              </span>
            </div>
            <textarea
              id="edit-pulse-optional-comment"
              rows={3}
              maxLength={MAX_COMMENT_LENGTH}
              value={optionalComment}
              onChange={(e) => setOptionalComment(e.target.value)}
              disabled={submitting}
              placeholder="Add any optional personal reflections on your week..."
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors"
            />
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              id="save-edit-pulse-btn"
              type="submit"
              variant="primary"
              size="sm"
              loading={submitting}
              disabled={!isFormComplete || submitting}
            >
              Save Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
