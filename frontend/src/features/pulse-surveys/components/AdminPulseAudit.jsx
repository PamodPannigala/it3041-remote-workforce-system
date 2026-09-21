import React, { useState, useEffect, useCallback } from "react";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../../components/ui/Card";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import Badge from "../../../components/ui/Badge";
import EmptyState from "../../../components/ui/EmptyState";
import { SkeletonCard, SkeletonTable } from "../../../components/ui/Skeleton";
import { getAdminPulseSummary, getAdminPulseAuditRecords } from "../pulseSurveysApi";

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

function formatWeekDate(dateStr) {
  if (!dateStr) return "N/A";
  try {
    const d = parseUtcDate(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  } catch {
    return dateStr;
  }
}

function formatTimestamp(dateStr) {
  if (!dateStr) return "N/A";
  try {
    const d = parseUtcDate(dateStr);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export default function AdminPulseAudit({
  adminTeams = [],
  token,
  onSessionExpired,
}) {
  const [activeSubView, setActiveSubView] = useState("summaries"); // 'summaries' | 'records'
  const [weekFilter, setWeekFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");

  // Summaries State
  const [summaryData, setSummaryData] = useState(null);
  const [summariesLoading, setSummariesLoading] = useState(false);
  const [summariesError, setSummariesError] = useState("");

  // Audit Records State
  const [recordsData, setRecordsData] = useState([]);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    total_pages: 1,
  });
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState("");

  // Load Summaries
  const loadSummaries = useCallback(
    async (weekToLoad = weekFilter) => {
      if (!token) return;
      setSummariesLoading(true);
      setSummariesError("");

      try {
        const data = await getAdminPulseSummary(token, {
          weekStart: weekToLoad ? weekToLoad.trim() : undefined,
        });
        setSummaryData(data);
      } catch (err) {
        if (err.status === 401 && onSessionExpired) {
          onSessionExpired();
        } else {
          setSummariesError(err.message || "Failed to load organization pulse summaries.");
        }
      } finally {
        setSummariesLoading(false);
      }
    },
    [token, weekFilter, onSessionExpired]
  );

  // Load Audit Records
  const loadAuditRecords = useCallback(
    async (page = 1, teamToFilter = teamFilter, weekToFilter = weekFilter) => {
      if (!token) return;
      setRecordsLoading(true);
      setRecordsError("");

      try {
        const data = await getAdminPulseAuditRecords(token, {
          page,
          limit: 20,
          teamId: teamToFilter ? teamToFilter.trim() : undefined,
          weekStart: weekToFilter ? weekToFilter.trim() : undefined,
        });
        setRecordsData(data.items || []);
        setPagination({
          page: data.page,
          limit: data.limit,
          total: data.total,
          total_pages: data.total_pages,
        });
      } catch (err) {
        if (err.status === 401 && onSessionExpired) {
          onSessionExpired();
        } else {
          setRecordsError(err.message || "Failed to load pulse audit records.");
        }
      } finally {
        setRecordsLoading(false);
      }
    },
    [token, teamFilter, weekFilter, onSessionExpired]
  );

  useEffect(() => {
    if (activeSubView === "summaries") {
      loadSummaries(weekFilter);
    } else {
      loadAuditRecords(1, teamFilter, weekFilter);
    }
  }, [activeSubView, weekFilter, teamFilter, loadSummaries, loadAuditRecords]);

  return (
    <div className="space-y-6">
      {/* Responsible AI & Privacy Audit Banner */}
      <div className="p-4 rounded-xl bg-violet-50/70 border border-violet-200/80 flex items-start gap-3.5">
        <div className="w-8 h-8 rounded-lg bg-violet-100/80 border border-violet-200 flex items-center justify-center text-violet-700 shrink-0 mt-0.5">
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
          <div className="flex items-center gap-2">
            <p className="font-bold text-slate-900 font-heading">
              Governance & Privacy Guarantee
            </p>
            <Badge variant="admin" size="sm">
              Read-only Privacy-Safe Audit
            </Badge>
          </div>
          <p>
            This administrative audit console strictly enforces respondent privacy protection. No individual user identities, respondent emails, individual scores, or confidential employee comments are accessible to administrators.
          </p>
          <p className="text-slate-600">
            Team-level metrics are only aggregated when at least 3 responses exist for a team. Pulse survey data must never be used for disciplinary actions or medical diagnostic conclusions.
          </p>
        </div>
      </div>

      {/* Main Card */}
      <Card variant="admin">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <CardTitle>Pulse Survey Governance Audit</CardTitle>
              <Badge variant="admin" size="sm">
                Admin Audit
              </Badge>
            </div>
            <CardDescription>
              Review organization-wide team pulse aggregations and submission metadata logs.
            </CardDescription>
          </div>

          {/* Sub-view switcher */}
          <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200">
            <button
              type="button"
              id="admin-pulse-tab-summaries"
              onClick={() => setActiveSubView("summaries")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeSubView === "summaries"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Team Summaries
            </button>
            <button
              type="button"
              id="admin-pulse-tab-records"
              onClick={() => setActiveSubView("records")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeSubView === "records"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Submission Audit Logs
            </button>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Controls & Filters */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-4 rounded-xl bg-slate-50 border border-slate-200/80">
            <div className="flex items-center gap-3 flex-wrap">
              {/* Optional Week Filter */}
              <div className="flex items-center gap-2">
                <label
                  htmlFor="admin-pulse-week-filter"
                  className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
                >
                  Week (Mon):
                </label>
                <input
                  id="admin-pulse-week-filter"
                  type="date"
                  value={weekFilter}
                  onChange={(e) => setWeekFilter(e.target.value)}
                  className="px-2.5 py-1 bg-white border border-slate-300 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                  aria-label="Filter pulse audit by Monday week date"
                />
              </div>

              {/* Optional Team Filter (For Records View) */}
              {activeSubView === "records" && (
                <div className="flex items-center gap-2">
                  <label
                    htmlFor="admin-pulse-team-filter"
                    className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
                  >
                    Team:
                  </label>
                  <select
                    id="admin-pulse-team-filter"
                    value={teamFilter}
                    onChange={(e) => setTeamFilter(e.target.value)}
                    className="px-2.5 py-1 bg-white border border-slate-300 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                    aria-label="Filter audit logs by team"
                  >
                    <option value="">All Organization Teams</option>
                    {adminTeams.map((team) => (
                      <option key={team.id} value={team.id}>
                        {team.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {(weekFilter || teamFilter) && (
                <button
                  type="button"
                  onClick={() => {
                    setWeekFilter("");
                    setTeamFilter("");
                  }}
                  className="text-xs text-slate-500 hover:text-slate-800 underline"
                >
                  Reset Filters
                </button>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (activeSubView === "summaries") {
                  loadSummaries(weekFilter);
                } else {
                  loadAuditRecords(pagination.page, teamFilter, weekFilter);
                }
              }}
              disabled={summariesLoading || recordsLoading}
            >
              {summariesLoading || recordsLoading ? "Refreshing..." : "Refresh Audit"}
            </Button>
          </div>

          {/* Sub-view 1: Organization Team Summaries */}
          {activeSubView === "summaries" && (
            <div className="space-y-4">
              {summariesError && (
                <Alert variant="error" onDismiss={() => setSummariesError("")}>
                  {summariesError}
                </Alert>
              )}

              {summariesLoading && !summaryData ? (
                <div className="space-y-3">
                  <SkeletonCard />
                  <SkeletonCard />
                </div>
              ) : !summaryData || summaryData.items?.length === 0 ? (
                <EmptyState
                  title="No Team Summaries Available"
                  description="No teams or pulse summaries were found for the selected week."
                />
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-1 text-xs text-slate-500">
                    <span>Week of {formatWeekDate(summaryData.week_start)}</span>
                    <span>{summaryData.items.length} Teams Evaluated</span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {summaryData.items.map((teamSummary) => {
                      const teamName = teamSummary.team_name || "Unknown Team";
                      return (
                        <div
                          key={teamSummary.team_id}
                          className="p-4 rounded-xl bg-slate-50/80 border border-slate-200/80 space-y-3 shadow-xs"
                        >
                          <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                            <div>
                              <h4 className="text-sm font-bold text-slate-900 font-heading">
                                {teamName}
                              </h4>
                              <span className="text-xs text-slate-500">
                                {teamSummary.response_count} {teamSummary.response_count === 1 ? "response" : "responses"}
                              </span>
                            </div>
                            <Badge
                              variant={teamSummary.available ? "active" : "neutral"}
                              size="sm"
                            >
                              {teamSummary.available ? "Aggregated" : "< 3 Responses"}
                            </Badge>
                          </div>

                          {teamSummary.available && teamSummary.averages ? (
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div className="p-2 rounded-lg bg-white border border-slate-200/60">
                                <span className="text-[10px] uppercase font-bold text-slate-500 block">Workload</span>
                                <span className="font-extrabold text-slate-900 text-sm">
                                  {teamSummary.averages.workload_manageability.toFixed(2)} / 5.00
                                </span>
                              </div>
                              <div className="p-2 rounded-lg bg-white border border-slate-200/60">
                                <span className="text-[10px] uppercase font-bold text-slate-500 block">Work-Life</span>
                                <span className="font-extrabold text-slate-900 text-sm">
                                  {teamSummary.averages.work_life_balance.toFixed(2)} / 5.00
                                </span>
                              </div>
                              <div className="p-2 rounded-lg bg-white border border-slate-200/60">
                                <span className="text-[10px] uppercase font-bold text-slate-500 block">Support</span>
                                <span className="font-extrabold text-slate-900 text-sm">
                                  {teamSummary.averages.team_support.toFixed(2)} / 5.00
                                </span>
                              </div>
                              <div className="p-2 rounded-lg bg-white border border-slate-200/60">
                                <span className="text-[10px] uppercase font-bold text-slate-500 block">Engagement</span>
                                <span className="font-extrabold text-slate-900 text-sm">
                                  {teamSummary.averages.engagement.toFixed(2)} / 5.00
                                </span>
                              </div>
                            </div>
                          ) : (
                            <div className="p-3 rounded-lg bg-amber-50/50 border border-amber-200/60 text-xs text-slate-600">
                              <p className="font-medium text-amber-900 mb-0.5">Privacy Threshold Enforced</p>
                              <p className="text-[11px] text-slate-500">
                                {teamSummary.message || "Fewer than 3 responses received; individual responses masked."}
                              </p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Sub-view 2: Submission Audit Log Table */}
          {activeSubView === "records" && (
            <div className="space-y-4">
              {recordsError && (
                <Alert variant="error" onDismiss={() => setRecordsError("")}>
                  {recordsError}
                </Alert>
              )}

              {recordsLoading && recordsData.length === 0 ? (
                <SkeletonTable rows={5} cols={4} />
              ) : recordsData.length === 0 ? (
                <EmptyState
                  title="No Audit Records Found"
                  description="No pulse survey submissions matched the selected filters."
                />
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-left text-sm text-slate-700">
                    <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                      <tr>
                        <th scope="col" className="py-3 px-4">Team</th>
                        <th scope="col" className="py-3 px-4">Pulse Week</th>
                        <th scope="col" className="py-3 px-4">Submitted At</th>
                        <th scope="col" className="py-3 px-4">Privacy Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {recordsData.map((record) => (
                        <tr key={record.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3 px-4 font-semibold text-slate-900">
                            {record.team_name || "Unknown Team"}
                          </td>
                          <td className="py-3 px-4 text-slate-600">
                            Week of {formatWeekDate(record.week_start)}
                          </td>
                          <td className="py-3 px-4 text-slate-500 text-xs">
                            {formatTimestamp(record.submitted_at)}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant="neutral" size="sm">
                              Masked & Confidential
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Pagination */}
              {pagination.total_pages > 1 && (
                <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
                  <span>
                    Total Audit Entries: {pagination.total} (Page {pagination.page} of {pagination.total_pages})
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => loadAuditRecords(pagination.page - 1, teamFilter, weekFilter)}
                      disabled={pagination.page <= 1 || recordsLoading}
                    >
                      Previous
                    </Button>
                    <span className="px-2 font-medium">Page {pagination.page}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => loadAuditRecords(pagination.page + 1, teamFilter, weekFilter)}
                      disabled={pagination.page >= pagination.total_pages || recordsLoading}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
