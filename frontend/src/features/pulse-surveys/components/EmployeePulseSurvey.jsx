import React, { useState } from "react";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../../components/ui/Card";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import Badge from "../../../components/ui/Badge";
import EmptyState from "../../../components/ui/EmptyState";
import PulseRatingField from "./PulseRatingField";
import PulseResponseHistory from "./PulseResponseHistory";
import { submitPulseSurveyResponse } from "../pulseSurveysApi";

const MAX_COMMENT_LENGTH = 1000;

export default function EmployeePulseSurvey({
  user,
  token,
  onSessionExpired,
  assignedTeam = null,
}) {
  const hasTeamAccess = Boolean(assignedTeam?.has_team || user?.team_id);
  const teamName = assignedTeam?.team_name || "Assigned Team";

  // Form State
  const [ratings, setRatings] = useState({
    workload_manageability: null,
    work_life_balance: null,
    team_support: null,
    engagement: null,
  });
  const [optionalComment, setOptionalComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitSuccess, setSubmitSuccess] = useState("");
  const [refreshHistoryTrigger, setRefreshHistoryTrigger] = useState(0);

  // Check completion
  const isFormComplete =
    ratings.workload_manageability !== null &&
    ratings.work_life_balance !== null &&
    ratings.team_support !== null &&
    ratings.engagement !== null;

  const handleRatingChange = (field, val) => {
    setRatings((prev) => ({ ...prev, [field]: val }));
    setSubmitError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isFormComplete || submitting) return;

    setSubmitting(true);
    setSubmitError("");
    setSubmitSuccess("");

    try {
      await submitPulseSurveyResponse(token, {
        workload_manageability: ratings.workload_manageability,
        work_life_balance: ratings.work_life_balance,
        team_support: ratings.team_support,
        engagement: ratings.engagement,
        optional_comment: optionalComment.trim() || null,
      });

      setSubmitSuccess("Thank you! Your weekly pulse survey has been securely submitted.");
      // Reset form
      setRatings({
        workload_manageability: null,
        work_life_balance: null,
        team_support: null,
        engagement: null,
      });
      setOptionalComment("");
      // Trigger history reload
      setRefreshHistoryTrigger((prev) => prev + 1);
    } catch (err) {
      if (err.status === 401 && onSessionExpired) {
        onSessionExpired();
      } else if (err.status === 409) {
        setSubmitError("You have already submitted this week's pulse survey.");
      } else {
        setSubmitError(err.message || "Failed to submit pulse survey response.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!hasTeamAccess) {
    return (
      <Card variant="employee">
        <CardHeader>
          <CardTitle>Weekly Pulse Survey</CardTitle>
          <CardDescription>
            Confidential weekly reflection to help team leaders understand workload dynamics.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No Team Assigned"
            description="You are not currently assigned to a workforce team. Weekly pulse surveys become available once an administrator assigns you to a team."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Responsible AI & Privacy Notice Card */}
      <div className="p-4 rounded-xl bg-blue-50/70 border border-blue-200/80 flex items-start gap-3.5">
        <div className="w-8 h-8 rounded-lg bg-blue-100/80 border border-blue-200 flex items-center justify-center text-blue-700 shrink-0 mt-0.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
        </div>
        <div className="min-w-0 text-xs text-slate-700 leading-relaxed space-y-1">
          <p className="font-bold text-slate-900 font-heading">
            Privacy & Responsible Use Guarantee
          </p>
          <p>
            Weekly pulse surveys are intended solely for team-level support, workload planning, and resource balancing. Responses are not used for medical or psychological diagnosis, nor for punitive performance decisions.
          </p>
          <p className="text-slate-600">
            Managers and administrators only view privacy-thresholded team aggregates (minimum 3 team responses required). Your individual ratings and optional notes remain private.
          </p>
        </div>
      </div>

      {/* Main Pulse Survey Card */}
      <Card variant="employee">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <CardTitle>Weekly Pulse Check-In</CardTitle>
              <Badge variant="employee" size="sm">
                {teamName}
              </Badge>
            </div>
            <CardDescription>
              Share how your work week is progressing. All 4 ratings are required (1 = Low/Challenging, 5 = High/Thriving).
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent>
          {submitSuccess && (
            <Alert variant="success" className="mb-6" onDismiss={() => setSubmitSuccess("")}>
              {submitSuccess}
            </Alert>
          )}

          {submitError && (
            <Alert variant="error" className="mb-6" onDismiss={() => setSubmitError("")}>
              {submitError}
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Metric 1: Workload Manageability */}
            <PulseRatingField
              id="pulse-workload-manageability"
              label="1. Workload Manageability"
              description="How manageable was your assigned workload and task volume this week?"
              lowLabel="Overwhelming / Unmanageable"
              highLabel="Balanced / Fully Manageable"
              value={ratings.workload_manageability}
              onChange={(val) => handleRatingChange("workload_manageability", val)}
              disabled={submitting}
            />

            {/* Metric 2: Work-Life Balance */}
            <PulseRatingField
              id="pulse-work-life-balance"
              label="2. Work-Life Balance"
              description="How well were you able to maintain healthy boundaries between work and personal time?"
              lowLabel="Poor / Strained"
              highLabel="Healthy / Excellent"
              value={ratings.work_life_balance}
              onChange={(val) => handleRatingChange("work_life_balance", val)}
              disabled={submitting}
            />

            {/* Metric 3: Team Support */}
            <PulseRatingField
              id="pulse-team-support"
              label="3. Team Support"
              description="Did you feel supported by team members and have the collaboration needed to make progress?"
              lowLabel="Isolated / Minimal Support"
              highLabel="Strong Collaboration / Highly Supported"
              value={ratings.team_support}
              onChange={(val) => handleRatingChange("team_support", val)}
              disabled={submitting}
            />

            {/* Metric 4: Engagement */}
            <PulseRatingField
              id="pulse-engagement"
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
                  htmlFor="pulse-optional-comment"
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
              <p className="text-xs text-slate-500">
                Any private thoughts or context for your personal reflection log. This note is never exposed to managers or administrators.
              </p>
              <textarea
                id="pulse-optional-comment"
                rows={3}
                maxLength={MAX_COMMENT_LENGTH}
                value={optionalComment}
                onChange={(e) => setOptionalComment(e.target.value)}
                disabled={submitting}
                placeholder="Add any optional personal reflections on your week..."
                className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors"
              />
            </div>

            {/* Form Actions */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
              <p className="text-xs text-slate-500">
                {isFormComplete
                  ? "All required metrics selected. Ready to submit."
                  : "Please select a 1-5 rating for all 4 metrics above."}
              </p>
              <Button
                id="submit-pulse-btn"
                type="submit"
                variant="primary"
                disabled={!isFormComplete || submitting}
                loading={submitting}
                className="shrink-0"
              >
                {submitting ? "Submitting Pulse..." : "Submit Weekly Pulse"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Response History Card */}
      <Card variant="employee">
        <CardContent className="pt-6">
          <PulseResponseHistory
            token={token}
            onSessionExpired={onSessionExpired}
            refreshTrigger={refreshHistoryTrigger}
          />
        </CardContent>
      </Card>
    </div>
  );
}
