import React, { useState, useEffect, useCallback } from "react";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../../components/ui/Card";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import Badge from "../../../components/ui/Badge";
import EmptyState from "../../../components/ui/EmptyState";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { getAdminCollaborationMessages } from "../collaborationApi";

function formatTimestamp(isoString) {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function AdminMessageAudit({
  adminTeams = [],
  token,
  onSessionExpired,
}) {
  const [messages, setMessages] = useState([]);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    total_pages: 1,
  });
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inspectingMessage, setInspectingMessage] = useState(null);

  const loadAuditMessages = useCallback(
    async (page = 1) => {
      if (!token) return;

      setLoading(true);
      setError("");

      try {
        const queryOptions = {
          teamId: selectedTeamId || undefined,
          includeDeleted,
          page,
          limit: 20,
        };

        const data = await getAdminCollaborationMessages(token, queryOptions);
        setMessages(data.items || []);
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
          setError(err.message || "Failed to load collaboration audit records.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, selectedTeamId, includeDeleted, onSessionExpired]
  );

  useEffect(() => {
    loadAuditMessages(1);
  }, [loadAuditMessages]);

  return (
    <div className="space-y-6">
      <Card variant="admin">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <CardTitle>Collaboration Message Audit</CardTitle>
              <Badge variant="admin" size="sm">
                Read-only Audit
              </Badge>
            </div>
            <CardDescription>
              Organization-wide compliance audit log for all collaboration messages, including retained soft-deleted message history.
            </CardDescription>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => loadAuditMessages(pagination.page)}
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
            {loading ? "Refreshing..." : "Refresh Audit"}
          </Button>
        </CardHeader>

        {/* Filter Controls Bar */}
        <div className="p-4 sm:p-5 bg-slate-50/80 border-b border-slate-200/80 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {/* Team Filter */}
            <div className="flex items-center gap-2">
              <label
                htmlFor="audit-team-filter"
                className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
              >
                Team:
              </label>
              <select
                id="audit-team-filter"
                value={selectedTeamId}
                onChange={(e) => setSelectedTeamId(e.target.value)}
                className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                aria-label="Filter audit by team"
              >
                <option value="">All Teams ({adminTeams.length})</option>
                {adminTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Visibility Status Filter */}
            <div className="flex items-center gap-2">
              <label
                htmlFor="audit-status-filter"
                className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
              >
                Visibility:
              </label>
              <select
                id="audit-status-filter"
                value={includeDeleted ? "all" : "active"}
                onChange={(e) => setIncludeDeleted(e.target.value === "all")}
                className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                aria-label="Filter audit by visibility status"
              >
                <option value="all">All Records (Active & Deleted)</option>
                <option value="active">Active Only</option>
              </select>
            </div>
          </div>

          <div className="text-xs text-slate-500 font-medium self-end sm:self-center">
            Total Audit Records: <span className="font-bold text-slate-800">{pagination.total}</span>
          </div>
        </div>

        <CardContent className="p-0">
          {error && (
            <div className="p-4 border-b border-slate-200">
              <Alert variant="error" onDismiss={() => setError("")}>
                {error}
              </Alert>
            </div>
          )}

          {loading ? (
            <div className="p-4">
              <SkeletonTable rows={5} cols={6} />
            </div>
          ) : messages.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="No Collaboration Messages Found"
                description="No organization message records match the selected filter criteria."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-700">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                  <tr>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Timestamp</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Team</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Sender</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Message Content</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Status</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6 text-right">Audit Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {messages.map((msg) => {
                    const senderDisplay = msg.sender_name || "Unknown User";
                    const teamDisplay = msg.team_name || "Unknown Team";
                    const isDeleted = Boolean(msg.is_deleted);

                    return (
                      <tr key={msg.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3.5 px-4 sm:px-6 text-xs text-slate-500 whitespace-nowrap">
                          {formatTimestamp(msg.created_at)}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 text-xs font-semibold text-slate-800 whitespace-nowrap">
                          {teamDisplay}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6">
                          <div className="text-xs font-medium text-slate-900">{senderDisplay}</div>
                          {msg.sender_email && (
                            <div className="text-[11px] text-slate-400 truncate max-w-[160px]">
                              {msg.sender_email}
                            </div>
                          )}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 max-w-xs">
                          <div className="text-xs text-slate-700 truncate line-clamp-2">
                            {msg.content ? (
                              <span>{msg.content}</span>
                            ) : (
                              <span className="italic text-slate-400">No content</span>
                            )}
                          </div>
                          {msg.edited_at && (
                            <span className="text-[10px] text-amber-700 bg-amber-50 px-1 py-0.5 rounded mt-0.5 inline-block">
                              Edited
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 whitespace-nowrap">
                          <Badge variant={isDeleted ? "inactive" : "active"} size="sm" dot>
                            {isDeleted ? "Deleted" : "Active"}
                          </Badge>
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 text-right whitespace-nowrap">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setInspectingMessage(msg)}
                            aria-label={`Inspect audit record for message from ${senderDisplay}`}
                          >
                            Inspect
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {pagination.total_pages > 1 && (
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
              <span>
                Page {pagination.page} of {pagination.total_pages} (Total: {pagination.total} records)
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadAuditMessages(pagination.page - 1)}
                  disabled={pagination.page <= 1 || loading}
                >
                  Previous
                </Button>
                <span className="px-2 font-medium">Page {pagination.page}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadAuditMessages(pagination.page + 1)}
                  disabled={pagination.page >= pagination.total_pages || loading}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Audit Inspection Modal */}
      {inspectingMessage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="audit-inspect-modal-title"
        >
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
            onClick={() => setInspectingMessage(null)}
            aria-hidden="true"
          />

          {/* Modal Container */}
          <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-10 flex flex-col max-h-[90vh]">
            {/* Header */}
            <div className="p-5 sm:p-6 border-b border-slate-100 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-600 shrink-0">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                </div>
                <div>
                  <h3
                    id="audit-inspect-modal-title"
                    className="text-lg font-bold font-heading text-slate-900"
                  >
                    Audit Record Inspection
                  </h3>
                  <span className="text-xs text-slate-500">
                    Read-only compliance verification
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setInspectingMessage(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                aria-label="Close inspection modal"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Scrollable Modal Body */}
            <div className="p-5 sm:p-6 space-y-5 overflow-y-auto">
              {/* Metadata Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-xs">
                <div>
                  <span className="font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    Team
                  </span>
                  <p className="font-bold text-slate-900 text-sm">
                    {inspectingMessage.team_name || "Unknown Team"}
                  </p>
                </div>

                <div>
                  <span className="font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    Sender Identity
                  </span>
                  <p className="font-bold text-slate-900 text-sm">
                    {inspectingMessage.sender_name || "Unknown User"}
                  </p>
                  {inspectingMessage.sender_email && (
                    <p className="text-slate-500">{inspectingMessage.sender_email}</p>
                  )}
                </div>

                <div>
                  <span className="font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    Audit Status
                  </span>
                  <Badge
                    variant={inspectingMessage.is_deleted ? "inactive" : "active"}
                    size="sm"
                    dot
                  >
                    {inspectingMessage.is_deleted ? "Soft-Deleted" : "Active"}
                  </Badge>
                </div>

                <div>
                  <span className="font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    Created Timestamp
                  </span>
                  <p className="text-slate-800 font-medium">
                    {formatTimestamp(inspectingMessage.created_at)}
                  </p>
                </div>

                {inspectingMessage.edited_at && (
                  <div>
                    <span className="font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                      Last Edited
                    </span>
                    <p className="text-slate-800 font-medium">
                      {formatTimestamp(inspectingMessage.edited_at)}
                    </p>
                  </div>
                )}

                {inspectingMessage.is_deleted && inspectingMessage.deleted_at && (
                  <div>
                    <span className="font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                      Deleted Timestamp
                    </span>
                    <p className="text-rose-700 font-medium">
                      {formatTimestamp(inspectingMessage.deleted_at)}
                    </p>
                  </div>
                )}
              </div>

              {/* Message Content (Retained for audit review) */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-600 block">
                  {inspectingMessage.is_deleted
                    ? "Retained Soft-Deleted Message Content (Audit View Only)"
                    : "Message Content"}
                </span>
                <div className="p-4 rounded-xl bg-slate-900 text-slate-100 text-sm font-sans whitespace-pre-wrap break-words leading-relaxed border border-slate-800">
                  {inspectingMessage.content || "(Empty message content)"}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 sm:p-5 border-t border-slate-100 bg-slate-50/70 flex items-center justify-between shrink-0">
              <span className="text-xs text-slate-500 italic">
                No modifications permitted in audit view
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setInspectingMessage(null)}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
