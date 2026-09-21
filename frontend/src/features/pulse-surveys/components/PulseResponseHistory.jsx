import React, { useState, useEffect, useCallback } from "react";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import Badge from "../../../components/ui/Badge";
import EmptyState from "../../../components/ui/EmptyState";
import { SkeletonCard } from "../../../components/ui/Skeleton";
import { getMyPulseSurveyResponses } from "../pulseSurveysApi";
import EditPulseModal from "./EditPulseModal";

function getUtcWeekStart(date = new Date()) {
  const d = new Date(date);
  const utcDay = d.getUTCDay(); // 0 is Sun, 1 is Mon, ..., 6 is Sat
  const diff = (utcDay === 0 ? -6 : 1) - utcDay;
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + diff, 0, 0, 0, 0));
}

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

function isCurrentUtcWeek(weekStartStr) {
  if (!weekStartStr) return false;
  try {
    const itemDate = parseUtcDate(weekStartStr);
    const currentMonday = getUtcWeekStart();
    return itemDate.toISOString().slice(0, 10) === currentMonday.toISOString().slice(0, 10);
  } catch {
    return false;
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

export default function PulseResponseHistory({ token, onSessionExpired, refreshTrigger = 0 }) {
  const [history, setHistory] = useState([]);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 10,
    total: 0,
    total_pages: 1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [editingItem, setEditingItem] = useState(null);

  const loadHistory = useCallback(
    async (page = 1) => {
      if (!token) return;
      setLoading(true);
      setError("");

      try {
        const data = await getMyPulseSurveyResponses(token, { page, limit: 10 });
        setHistory(data.items || []);
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
          setError(err.message || "Failed to load pulse survey history.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, onSessionExpired]
  );

  useEffect(() => {
    loadHistory(1);
  }, [loadHistory, refreshTrigger]);

  const handleResponseUpdated = (updatedResponse) => {
    setHistory((prev) =>
      prev.map((item) => (item.id === updatedResponse.id ? { ...item, ...updatedResponse } : item))
    );
    setSuccessMessage("Your weekly pulse response has been updated successfully.");
    loadHistory(pagination.page);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div>
          <h4 className="text-sm font-bold text-slate-900 font-heading">
            Your Pulse Response History ({pagination.total})
          </h4>
          <p className="text-xs text-slate-500">
            Confidential record of your past weekly submissions. You can edit your response until the current UTC week ends.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadHistory(pagination.page)}
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
          {loading ? "Refreshing..." : "Refresh History"}
        </Button>
      </div>

      {successMessage && (
        <Alert variant="success" onDismiss={() => setSuccessMessage("")}>
          {successMessage}
        </Alert>
      )}

      {error && (
        <Alert variant="error" onDismiss={() => setError("")}>
          {error}
        </Alert>
      )}

      {loading && history.length === 0 ? (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : history.length === 0 ? (
        <EmptyState
          title="No Submission History Yet"
          description="Your submitted weekly pulse surveys will appear here for your personal reference."
        />
      ) : (
        <div className="space-y-3">
          {history.map((item) => {
            const isCurrentWeek = isCurrentUtcWeek(item.week_start);
            const isEdited = Boolean(item.is_edited || item.updated_at);

            return (
              <div
                key={item.id}
                className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs hover:border-slate-300 transition-colors space-y-3"
              >
                {/* Card Header: Week, Badges, Timestamps & Actions */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="employee" size="sm">
                      Week of {formatWeekDate(item.week_start)}
                    </Badge>
                    {isCurrentWeek && (
                      <Badge variant="info" size="sm">
                        Current Week
                      </Badge>
                    )}
                    {isEdited && (
                      <Badge variant="warning" size="sm">
                        Edited
                      </Badge>
                    )}
                    {item.team_name && (
                      <span className="text-xs font-semibold text-slate-700">
                        Team: {item.team_name}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="flex flex-col sm:items-end text-[11px] text-slate-400">
                      <span>Submitted: {formatTimestamp(item.submitted_at)}</span>
                      {item.updated_at && (
                        <span className="text-amber-600 font-medium">
                          Edited: {formatTimestamp(item.updated_at)}
                        </span>
                      )}
                    </div>
                    {isCurrentWeek && (
                      <Button
                        id={`edit-pulse-btn-${item.id}`}
                        variant="outline"
                        size="xs"
                        onClick={() => setEditingItem(item)}
                        className="text-xs font-semibold text-blue-700 border-blue-200 hover:bg-blue-50"
                      >
                        Edit Response
                      </Button>
                    )}
                  </div>
                </div>

                {/* 4 Metrics Badges */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Workload
                    </span>
                    <span className="text-sm font-extrabold text-slate-800">
                      {item.workload_manageability}{" "}
                      <span className="text-xs font-normal text-slate-400">/ 5</span>
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Work-Life
                    </span>
                    <span className="text-sm font-extrabold text-slate-800">
                      {item.work_life_balance}{" "}
                      <span className="text-xs font-normal text-slate-400">/ 5</span>
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Team Support
                    </span>
                    <span className="text-sm font-extrabold text-slate-800">
                      {item.team_support}{" "}
                      <span className="text-xs font-normal text-slate-400">/ 5</span>
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Engagement
                    </span>
                    <span className="text-sm font-extrabold text-slate-800">
                      {item.engagement}{" "}
                      <span className="text-xs font-normal text-slate-400">/ 5</span>
                    </span>
                  </div>
                </div>

                {/* Optional Comment if provided */}
                {item.optional_comment && (
                  <div className="pt-2 text-xs text-slate-700 bg-slate-50/70 p-3 rounded-lg border border-slate-200/60">
                    <span className="font-semibold text-slate-600 block mb-1">
                      Your Confidential Note:
                    </span>
                    <p className="whitespace-pre-wrap leading-relaxed">
                      {item.optional_comment}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Controls */}
      {pagination.total_pages > 1 && (
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
          <span>
            Page {pagination.page} of {pagination.total_pages} ({pagination.total} total submissions)
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadHistory(pagination.page - 1)}
              disabled={pagination.page <= 1 || loading}
            >
              Previous
            </Button>
            <span className="px-2 font-medium">Page {pagination.page}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadHistory(pagination.page + 1)}
              disabled={pagination.page >= pagination.total_pages || loading}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Edit Pulse Modal */}
      {editingItem && (
        <EditPulseModal
          isOpen={Boolean(editingItem)}
          onClose={() => setEditingItem(null)}
          response={editingItem}
          token={token}
          onResponseUpdated={handleResponseUpdated}
          onSessionExpired={onSessionExpired}
        />
      )}
    </div>
  );
}
