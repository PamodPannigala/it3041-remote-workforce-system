import React, { useState, useEffect, useCallback } from "react";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../../components/ui/Card";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import Badge from "../../../components/ui/Badge";
import EmptyState from "../../../components/ui/EmptyState";
import { SkeletonCard } from "../../../components/ui/Skeleton";
import { getTeamPulseSummary } from "../pulseSurveysApi";

function parseUtcDate(dateStr) {
  if (!dateStr) return null;
  try {
    let s = String(dateStr).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      s = `${s}T00:00:00Z`;
    } else if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(s)) {
      s = s.replace(" ", "T") + "Z";
    }
    const d = new Date(s);
    return isNaN(d.getTime()) ? new Date(dateStr) : d;
  } catch {
    return new Date(dateStr);
  }
}

function formatWeekDisplay(dateStr) {
  if (!dateStr) return "Current Week";
  try {
    const d = parseUtcDate(dateStr);
    return `Week of ${d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    })}`;
  } catch {
    return dateStr;
  }
}

function MetricScoreBar({ label, value, max = 5 }) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
          {label}
        </span>
        <div className="flex items-baseline gap-1">
          <span className="text-xl font-extrabold font-heading text-slate-900">
            {value.toFixed(2)}
          </span>
          <span className="text-xs text-slate-400 font-medium">/ 5.00</span>
        </div>
      </div>

      <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-amber-500 rounded-full transition-all duration-300"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-[10px] text-slate-400 font-medium pt-0.5">
        <span>1.0 (Low)</span>
        <span>3.0 (Moderate)</span>
        <span>5.0 (High)</span>
      </div>
    </div>
  );
}

export default function ManagerPulseInsights({
  user,
  token,
  onSessionExpired,
  managedTeams = [],
}) {
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [weekFilter, setWeekFilter] = useState("");
  const [summaryData, setSummaryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Initialize selectedTeamId
  useEffect(() => {
    if (managedTeams && managedTeams.length > 0) {
      if (!selectedTeamId || !managedTeams.some((t) => t.id === selectedTeamId)) {
        setSelectedTeamId(managedTeams[0].id);
      }
    }
  }, [managedTeams, selectedTeamId]);

  const loadSummary = useCallback(
    async (teamIdToLoad = selectedTeamId, weekToLoad = weekFilter) => {
      if (!token || !teamIdToLoad) return;

      setLoading(true);
      setError("");

      try {
        const data = await getTeamPulseSummary(token, {
          teamId: teamIdToLoad,
          weekStart: weekToLoad ? weekToLoad.trim() : undefined,
        });
        setSummaryData(data);
      } catch (err) {
        if (err.status === 401 && onSessionExpired) {
          onSessionExpired();
        } else {
          setError(err.message || "Failed to load team pulse summary.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, selectedTeamId, weekFilter, onSessionExpired]
  );

  useEffect(() => {
    if (selectedTeamId) {
      loadSummary(selectedTeamId, weekFilter);
    }
  }, [selectedTeamId, weekFilter, loadSummary]);

  if (managedTeams.length === 0) {
    return (
      <Card variant="manager">
        <CardHeader>
          <CardTitle>Team Pulse Insights</CardTitle>
          <CardDescription>
            Anonymized, privacy-thresholded team trends and capacity indicators.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No Managed Teams"
            description="You are not currently assigned as manager to any team. Contact an administrator to delegate team management."
          />
        </CardContent>
      </Card>
    );
  }

  const selectedTeam = managedTeams.find((t) => t.id === selectedTeamId);
  const teamName = summaryData?.team_name || selectedTeam?.name || "Managed Team";

  return (
    <div className="space-y-6">
      {/* Responsible AI & Privacy Guarantee Card */}
      <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200/80 flex items-start gap-3.5">
        <div className="w-8 h-8 rounded-lg bg-amber-100/80 border border-amber-200 flex items-center justify-center text-amber-800 shrink-0 mt-0.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
        <div className="min-w-0 text-xs text-slate-700 leading-relaxed space-y-1">
          <p className="font-bold text-slate-900 font-heading">
            Manager Privacy Threshold & Responsible Use Notice
          </p>
          <p>
            To strictly preserve respondent confidentiality, aggregate metrics are computed and displayed only when at least 3 team members submit responses for a given week. Individual ratings, comments, and member identities are never exposed.
          </p>
          <p className="text-slate-600">
            Insights are intended for team workload balance, support planning, and resource allocation. Do not use pulse metrics for punitive performance evaluations.
          </p>
        </div>
      </div>

      {/* Main Insights Header & Controls */}
      <Card variant="manager">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <CardTitle>Team Pulse Insights</CardTitle>
              <Badge variant="manager" size="sm">
                {teamName}
              </Badge>
            </div>
            <CardDescription>
              Review weekly aggregate indicators for team workload, balance, and collaboration support.
            </CardDescription>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Managed Team Selector */}
            {managedTeams.length > 1 && (
              <div className="flex items-center gap-2">
                <label
                  htmlFor="manager-pulse-team-select"
                  className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
                >
                  Team:
                </label>
                <select
                  id="manager-pulse-team-select"
                  value={selectedTeamId}
                  onChange={(e) => setSelectedTeamId(e.target.value)}
                  className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500/40"
                  aria-label="Select managed team for pulse insights"
                >
                  {managedTeams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.members?.length || 0} members)
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Optional Week Filter (Monday) */}
            <div className="flex items-center gap-2">
              <label
                htmlFor="manager-pulse-week-filter"
                className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
              >
                Week (Mon):
              </label>
              <input
                id="manager-pulse-week-filter"
                type="date"
                value={weekFilter}
                onChange={(e) => setWeekFilter(e.target.value)}
                placeholder="YYYY-MM-DD"
                className="px-2.5 py-1 bg-white border border-slate-300 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500/40"
                aria-label="Filter by Monday week date"
              />
              {weekFilter && (
                <button
                  type="button"
                  onClick={() => setWeekFilter("")}
                  className="text-xs text-slate-500 hover:text-slate-800 underline"
                >
                  Clear
                </button>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => loadSummary(selectedTeamId, weekFilter)}
              disabled={loading}
              icon={
                <svg
                  className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              }
            >
              {loading ? "Refreshing..." : "Refresh Insights"}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {error && (
            <Alert variant="error" onDismiss={() => setError("")}>
              {error}
            </Alert>
          )}

          {loading && !summaryData ? (
            <div className="space-y-4">
              <SkeletonCard />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <SkeletonCard />
                <SkeletonCard />
              </div>
            </div>
          ) : summaryData ? (
            <div className="space-y-6">
              {/* Summary Overview Banner */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-base font-bold text-slate-900 font-heading">
                      {teamName}
                    </h4>
                    <Badge variant={summaryData.available ? "active" : "neutral"} size="sm">
                      {summaryData.available ? "Metrics Available" : "Privacy Threshold Enforced"}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {formatWeekDisplay(summaryData.week_start)}
                  </p>
                </div>

                <div className="flex items-center gap-6">
                  <div className="text-right sm:text-left">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                      Weekly Responses
                    </span>
                    <span className="text-lg font-extrabold text-slate-900">
                      {summaryData.response_count}
                    </span>
                  </div>

                  <div className="text-right sm:text-left">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                      Privacy Minimum
                    </span>
                    <span className="text-lg font-extrabold text-slate-600">
                      {summaryData.minimum_required} required
                    </span>
                  </div>
                </div>
              </div>

              {/* Aggregates or Privacy Explanatory Empty State */}
              {summaryData.available && summaryData.averages ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                      Team Aggregate Averages (1.00 - 5.00 Scale)
                    </h5>
                    <span className="text-xs text-slate-400">
                      Computed from {summaryData.response_count} verified team submissions
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <MetricScoreBar
                      label="1. Workload Manageability"
                      value={summaryData.averages.workload_manageability}
                    />
                    <MetricScoreBar
                      label="2. Work-Life Balance"
                      value={summaryData.averages.work_life_balance}
                    />
                    <MetricScoreBar
                      label="3. Team Support"
                      value={summaryData.averages.team_support}
                    />
                    <MetricScoreBar
                      label="4. Engagement"
                      value={summaryData.averages.engagement}
                    />
                  </div>
                </div>
              ) : (
                <div className="p-6 rounded-2xl bg-amber-50/40 border border-amber-200/60 text-center space-y-3">
                  <div className="w-12 h-12 rounded-full bg-amber-100 border border-amber-200 text-amber-700 flex items-center justify-center mx-auto">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                      />
                    </svg>
                  </div>
                  <h4 className="text-base font-bold text-slate-900 font-heading">
                    Insufficient Responses to Display Aggregate Metrics
                  </h4>
                  <p className="text-xs text-slate-600 max-w-lg mx-auto leading-relaxed">
                    {summaryData.message ||
                      `Currently received ${summaryData.response_count} of ${summaryData.minimum_required} minimum responses required to protect individual respondent privacy.`}
                  </p>
                  <p className="text-[11px] text-slate-500 italic">
                    Aggregated metric indicators will automatically become visible once at least 3 team members submit their pulse for this week.
                  </p>
                </div>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
