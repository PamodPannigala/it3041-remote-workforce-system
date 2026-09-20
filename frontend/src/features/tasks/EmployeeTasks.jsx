import React, { useState, useEffect, useCallback } from "react";
import { getMyTasks, updateTaskStatus, addTaskProgress, addTaskBlocker } from "../../api/tasks";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import EmptyState from "../../components/ui/EmptyState";
import { SkeletonCard } from "../../components/ui/Skeleton";
import TaskStatusBadge from "./TaskStatusBadge";
import TaskPriorityBadge from "./TaskPriorityBadge";
import TaskFilters from "./TaskFilters";
import TaskDetailsModal from "./TaskDetailsModal";
import ProgressUpdateModal from "./ProgressUpdateModal";
import BlockerModal from "./BlockerModal";

function formatDate(isoStr) {
  if (!isoStr) return null;
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

export default function EmployeeTasks({ token, onSessionExpired }) {
  const [tasks, setTasks] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total: 0, total_pages: 0, limit: 10 });
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Modals state
  const [selectedTask, setSelectedTask] = useState(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isProgressOpen, setIsProgressOpen] = useState(false);
  const [isBlockerOpen, setIsBlockerOpen] = useState(false);
  const [modalSubmitting, setModalSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");

  const loadTasks = useCallback(
    async (page = 1) => {
      setLoading(true);
      setError("");
      try {
        const res = await getMyTasks(token, {
          status: statusFilter || undefined,
          priority: priorityFilter || undefined,
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
          setError(err.message || "Failed to load assigned tasks.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, statusFilter, priorityFilter, onSessionExpired]
  );

  useEffect(() => {
    loadTasks(1);
  }, [loadTasks]);

  // Status transition handler
  const handleStatusChange = async (task, newStatus) => {
    setError("");
    setSuccess("");
    try {
      const updated = await updateTaskStatus(token, task.id, newStatus);
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
      setSuccess(`Task "${task.title}" status updated to ${newStatus.replace("_", " ")}.`);
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setError(err.message || "Failed to update task status.");
      }
    }
  };

  // Progress update submit
  const handleProgressSubmit = async (progressData) => {
    if (!selectedTask) return;
    setModalSubmitting(true);
    setModalError("");
    try {
      const updated = await addTaskProgress(token, selectedTask.id, progressData);
      setTasks((prev) => prev.map((t) => (t.id === selectedTask.id ? updated : t)));
      setSuccess(`Logged ${progressData.percentage}% progress on "${selectedTask.title}".`);
      setIsProgressOpen(false);
      setSelectedTask(null);
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setModalError(err.message || "Failed to submit progress update.");
      }
    } finally {
      setModalSubmitting(false);
    }
  };

  // Blocker submit
  const handleBlockerSubmit = async (blockerData) => {
    if (!selectedTask) return;
    setModalSubmitting(true);
    setModalError("");
    try {
      const updated = await addTaskBlocker(token, selectedTask.id, blockerData);
      setTasks((prev) => prev.map((t) => (t.id === selectedTask.id ? updated : t)));
      setSuccess(`Reported blocker on "${selectedTask.title}". Task marked as Blocked.`);
      setIsBlockerOpen(false);
      setSelectedTask(null);
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setModalError(err.message || "Failed to report blocker.");
      }
    } finally {
      setModalSubmitting(false);
    }
  };

  // Metrics count
  const metrics = {
    total: pagination.total,
    inProgress: tasks.filter((t) => t.status === "in_progress").length,
    blocked: tasks.filter((t) => t.status === "blocked").length,
    completed: tasks.filter((t) => t.status === "completed").length,
  };

  return (
    <div className="space-y-6">
      {/* Top Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm shrink-0">
            📋
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Total Assigned
            </span>
            <p className="text-base font-extrabold text-slate-900 truncate">
              {metrics.total}
            </p>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm shrink-0">
            ⚡
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              In Progress
            </span>
            <p className="text-base font-extrabold text-slate-900 truncate">
              {metrics.inProgress}
            </p>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 font-bold text-sm shrink-0">
            ⛔
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Blocked
            </span>
            <p className="text-base font-extrabold text-rose-600 truncate">
              {metrics.blocked}
            </p>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-sm shrink-0">
            ✓
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Completed
            </span>
            <p className="text-base font-extrabold text-emerald-600 truncate">
              {metrics.completed}
            </p>
          </div>
        </div>
      </div>

      {/* Main Task List Card */}
      <Card id="employee-tasks-section">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <CardTitle>Assigned Workload</CardTitle>
            <CardDescription>
              Track your assigned task deliverables, update execution status, and log progress milestones.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadTasks(pagination.page)}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Refresh Tasks"}
          </Button>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Alerts */}
          {success && (
            <Alert variant="success" onDismiss={() => setSuccess("")}>
              {success}
            </Alert>
          )}

          {error && (
            <Alert variant="error" onDismiss={() => setError("")}>
              {error}
            </Alert>
          )}

          {/* Filters */}
          <TaskFilters
            status={statusFilter}
            onStatusChange={setStatusFilter}
            priority={priorityFilter}
            onPriorityChange={setPriorityFilter}
            onReset={() => {
              setStatusFilter("");
              setPriorityFilter("");
            }}
            loading={loading}
          />

          {/* Task List Content */}
          {loading ? (
            <div className="space-y-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : tasks.length === 0 ? (
            <EmptyState
              title="No Assigned Tasks"
              description={
                statusFilter || priorityFilter
                  ? "No tasks match your filter criteria. Try resetting the filters."
                  : "You have no tasks assigned to you currently. New tasks from your manager will appear here."
              }
            />
          ) : (
            <div className="space-y-3">
              {tasks.map((task) => {
                const latestProgress =
                  task.progress_history && task.progress_history.length > 0
                    ? task.progress_history[task.progress_history.length - 1].percentage
                    : task.status === "completed"
                    ? 100
                    : 0;

                const formattedDue = formatDate(task.due_date);
                const hasActiveBlockers = task.blockers && task.blockers.some((b) => !b.is_resolved);

                return (
                  <div
                    key={task.id}
                    className={`p-4 sm:p-5 rounded-xl border transition-all duration-150 ${
                      task.status === "blocked"
                        ? "bg-rose-50/30 border-rose-200/80 shadow-xs"
                        : "bg-white border-slate-200/80 hover:border-slate-300 shadow-xs"
                    }`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      {/* Left: Info */}
                      <div className="space-y-2 min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <TaskStatusBadge status={task.status} />
                          <TaskPriorityBadge priority={task.priority} />
                          {formattedDue && (
                            <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200">
                              📅 Due: {formattedDue}
                            </span>
                          )}
                          {task.estimated_hours > 0 && (
                            <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200">
                              ⏱ {task.estimated_hours} hrs
                            </span>
                          )}
                        </div>

                        <h4 className="text-sm sm:text-base font-bold text-slate-900 font-heading leading-snug">
                          {task.title}
                        </h4>

                        {task.description && (
                          <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                            {task.description}
                          </p>
                        )}

                        {/* Progress Bar & Skills */}
                        <div className="flex items-center gap-4 pt-1 flex-wrap">
                          <div className="flex items-center gap-2 w-44">
                            <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-1.5 rounded-full transition-all ${
                                  task.status === "completed"
                                    ? "bg-emerald-500"
                                    : task.status === "blocked"
                                    ? "bg-rose-500"
                                    : "bg-blue-600"
                                }`}
                                style={{ width: `${latestProgress}%` }}
                              />
                            </div>
                            <span className="text-[11px] font-mono font-bold text-slate-600">
                              {latestProgress}%
                            </span>
                          </div>

                          {task.required_skills && task.required_skills.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap">
                              {task.required_skills.slice(0, 3).map((s, idx) => (
                                <span
                                  key={idx}
                                  className="text-[10px] font-medium px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-100"
                                >
                                  {s}
                                </span>
                              ))}
                              {task.required_skills.length > 3 && (
                                <span className="text-[10px] text-slate-400 font-medium">
                                  +{task.required_skills.length - 3} more
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right: Actions */}
                      <div className="flex items-center gap-2 flex-wrap shrink-0 border-t md:border-t-0 pt-3 md:pt-0 border-slate-100">
                        {/* Status Select */}
                        <select
                          value={task.status}
                          onChange={(e) => handleStatusChange(task, e.target.value)}
                          className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                          aria-label={`Update status for ${task.title}`}
                        >
                          <option value="todo">To Do</option>
                          <option value="in_progress">In Progress</option>
                          <option value="blocked">Blocked</option>
                          <option value="completed" disabled={hasActiveBlockers}>
                            Completed {hasActiveBlockers ? "(Blocker unresolved)" : ""}
                          </option>
                        </select>

                        {/* Log Progress */}
                        {task.status !== "completed" && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setSelectedTask(task);
                              setIsProgressOpen(true);
                            }}
                            className="text-xs"
                          >
                            Log Progress
                          </Button>
                        )}

                        {/* Report Blocker */}
                        {task.status !== "completed" && (
                          <Button
                            variant="dangerOutline"
                            size="sm"
                            onClick={() => {
                              setSelectedTask(task);
                              setIsBlockerOpen(true);
                            }}
                            className="text-xs"
                          >
                            Report Blocker
                          </Button>
                        )}

                        {/* Details */}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSelectedTask(task);
                            setIsDetailsOpen(true);
                          }}
                          className="text-xs text-slate-600 hover:text-slate-900"
                        >
                          Details
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {pagination.total_pages > 1 && (
            <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl flex items-center justify-between text-xs text-slate-600">
              <span>Total Tasks: {pagination.total}</span>
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

      {/* Modals */}
      <TaskDetailsModal
        task={selectedTask}
        isOpen={isDetailsOpen}
        onClose={() => {
          setIsDetailsOpen(false);
          setSelectedTask(null);
        }}
        isManager={false}
      />

      <ProgressUpdateModal
        task={selectedTask}
        isOpen={isProgressOpen}
        onClose={() => {
          setIsProgressOpen(false);
          setSelectedTask(null);
        }}
        onSubmit={handleProgressSubmit}
        isSubmitting={modalSubmitting}
        error={modalError}
      />

      <BlockerModal
        task={selectedTask}
        isOpen={isBlockerOpen}
        onClose={() => {
          setIsBlockerOpen(false);
          setSelectedTask(null);
        }}
        onSubmit={handleBlockerSubmit}
        isSubmitting={modalSubmitting}
        error={modalError}
      />
    </div>
  );
}
