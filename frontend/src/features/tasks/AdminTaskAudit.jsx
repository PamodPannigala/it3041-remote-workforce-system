import React, { useState, useEffect, useCallback } from "react";
import { getAdminTasks } from "../../api/tasks";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import EmptyState from "../../components/ui/EmptyState";
import { SkeletonTable } from "../../components/ui/Skeleton";
import TaskStatusBadge from "./TaskStatusBadge";
import TaskPriorityBadge from "./TaskPriorityBadge";
import TaskDetailsModal from "./TaskDetailsModal";

function formatDate(isoStr) {
  if (!isoStr) return "None";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return isoStr;
  }
}

export default function AdminTaskAudit({
  adminTeams = [],
  token,
  onSessionExpired,
}) {
  const [tasks, setTasks] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total: 0, total_pages: 0, limit: 10 });
  const [statusFilter, setStatusFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedTask, setSelectedTask] = useState(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  const teamMap = React.useMemo(() => {
    const map = {};
    adminTeams.forEach((t) => {
      map[t.id] = t;
    });
    return map;
  }, [adminTeams]);

  const loadTasks = useCallback(
    async (page = 1) => {
      setLoading(true);
      setError("");
      try {
        const res = await getAdminTasks(token, {
          teamId: teamFilter || undefined,
          status: statusFilter || undefined,
          page,
          limit: 10,
        });
        setTasks(res.items || []);
        setPagination({
          page: res.page,
          total: res.total,
          total_pages: res.total_pages,
          limit: res.limit,
        });
      } catch (err) {
        if (err.status === 401) {
          onSessionExpired();
        } else {
          setError(err.message || "Failed to load audit task records.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, teamFilter, statusFilter, onSessionExpired]
  );

  useEffect(() => {
    loadTasks(1);
  }, [loadTasks]);

  return (
    <div className="space-y-6">
      <Card id="admin-task-audit-section">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <CardTitle>Organization Task Audit</CardTitle>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200">
                Read-Only Audit Visibility
              </span>
            </div>
            <CardDescription>
              Organization-wide task deliverable logs, execution status, blocker history, and audit metadata.
            </CardDescription>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => loadTasks(pagination.page)}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Refresh Audit Logs"}
          </Button>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <Alert variant="error" onDismiss={() => setError("")}>
              {error}
            </Alert>
          )}

          {/* Filters */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              {/* Team Filter */}
              {adminTeams.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <label htmlFor="admin-audit-team" className="text-xs font-semibold text-slate-500">
                    Team:
                  </label>
                  <select
                    id="admin-audit-team"
                    value={teamFilter}
                    onChange={(e) => setTeamFilter(e.target.value)}
                    disabled={loading}
                    className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                  >
                    <option value="">All Teams</option>
                    {adminTeams.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Status Filter */}
              <div className="flex items-center gap-1.5">
                <label htmlFor="admin-audit-status" className="text-xs font-semibold text-slate-500">
                  Status:
                </label>
                <select
                  id="admin-audit-status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  disabled={loading}
                  className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                >
                  <option value="">All Statuses</option>
                  <option value="todo">To Do</option>
                  <option value="in_progress">In Progress</option>
                  <option value="blocked">Blocked</option>
                  <option value="completed">Completed</option>
                </select>
              </div>
            </div>

            {(statusFilter || teamFilter) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setStatusFilter("");
                  setTeamFilter("");
                }}
                disabled={loading}
                className="text-xs text-slate-600"
              >
                Reset Filters
              </Button>
            )}
          </div>

          {/* Table */}
          {loading ? (
            <SkeletonTable rows={5} cols={6} />
          ) : tasks.length === 0 ? (
            <EmptyState
              title="No Audit Task Records"
              description="No organization task records found matching the active criteria."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-700">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                  <tr>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Title</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Team</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Status</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Priority</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Due Date</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Blockers</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Audit Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {tasks.map((task) => {
                    const team = teamMap[task.team_id];
                    const openBlockers = task.blockers
                      ? task.blockers.filter((b) => !b.is_resolved).length
                      : 0;
                    const resolvedBlockers = task.blockers
                      ? task.blockers.filter((b) => b.is_resolved).length
                      : 0;
                    const blockerSummary = `${openBlockers} open / ${resolvedBlockers} resolved`;

                    return (
                      <tr key={task.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3.5 px-4 sm:px-6 font-semibold text-slate-900 max-w-xs truncate">
                          {task.title}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 text-slate-600 text-xs">
                          {team ? team.name : (task.team_name || "Unknown Team")}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6">
                          <TaskStatusBadge status={task.status} size="sm" />
                        </td>
                        <td className="py-3.5 px-4 sm:px-6">
                          <TaskPriorityBadge priority={task.priority} size="sm" />
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 text-slate-500 text-xs">
                          {formatDate(task.due_date)}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6 text-xs">
                          {openBlockers > 0 ? (
                            <span className="font-bold text-rose-600">
                              ⛔ {blockerSummary}
                            </span>
                          ) : resolvedBlockers > 0 ? (
                            <span className="font-semibold text-emerald-700">
                              ✓ {blockerSummary}
                            </span>
                          ) : (
                            <span className="text-slate-400">
                              {blockerSummary}
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 sm:px-6">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setSelectedTask(task);
                              setIsDetailsOpen(true);
                            }}
                            className="text-xs"
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
            <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl flex items-center justify-between text-xs text-slate-600">
              <span>Total Workspace Tasks: {pagination.total}</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadTasks(pagination.page - 1)}
                  disabled={pagination.page <= 1 || loading}
                >
                  Previous
                </Button>
                <span className="px-2">
                  Page {pagination.page} of {pagination.total_pages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadTasks(pagination.page + 1)}
                  disabled={pagination.page >= pagination.total_pages || loading}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Details Modal */}
      <TaskDetailsModal
        task={selectedTask}
        isOpen={isDetailsOpen}
        onClose={() => {
          setIsDetailsOpen(false);
          setSelectedTask(null);
        }}
        isManager={false}
        teamName={selectedTask ? (teamMap[selectedTask.team_id]?.name || selectedTask.team_name || null) : null}
      />
    </div>
  );
}
