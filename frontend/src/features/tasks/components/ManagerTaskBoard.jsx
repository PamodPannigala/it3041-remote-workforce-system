import React, { useState, useEffect, useCallback } from "react";
import {
  getManagedTasks,
  createTask,
  updateTaskMetadata,
  updateTaskAssignment,
  resolveTaskBlocker,
} from "../tasksApi";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../../components/ui/Card";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import EmptyState from "../../../components/ui/EmptyState";
import { SkeletonCard } from "../../../components/ui/Skeleton";
import TaskStatusBadge from "./TaskStatusBadge";
import TaskPriorityBadge from "./TaskPriorityBadge";
import TaskFilters from "./TaskFilters";
import TaskDetailsModal from "./TaskDetailsModal";
import TaskFormModal from "./TaskFormModal";
import ResolveBlockerModal from "./ResolveBlockerModal";

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

export default function ManagerTaskBoard({
  managedTeams = [],
  token,
  onSessionExpired,
}) {
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [tasks, setTasks] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total: 0, total_pages: 0, limit: 10 });
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Create Modal state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState("");

  // Edit Modal state
  const [selectedEditTask, setSelectedEditTask] = useState(null);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState("");

  // Details Modal state
  const [selectedTask, setSelectedTask] = useState(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  // Resolve Blocker Modal state
  const [selectedBlockerTask, setSelectedBlockerTask] = useState(null);
  const [selectedBlocker, setSelectedBlocker] = useState(null);
  const [isResolveBlockerOpen, setIsResolveBlockerOpen] = useState(false);
  const [resolveBlockerSubmitting, setResolveBlockerSubmitting] = useState(false);
  const [resolveBlockerError, setResolveBlockerError] = useState("");

  // Map team IDs to team names and members
  const teamMap = React.useMemo(() => {
    const map = {};
    managedTeams.forEach((t) => {
      map[t.id] = t;
    });
    return map;
  }, [managedTeams]);

  // Load tasks
  const loadTasks = useCallback(
    async (page = 1) => {
      if (managedTeams.length === 0) {
        setLoading(false);
        setTasks([]);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const res = await getManagedTasks(token, {
          teamId: selectedTeamId || undefined,
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
          setError(err.message || "Failed to load team tasks.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, managedTeams, selectedTeamId, statusFilter, priorityFilter, onSessionExpired]
  );

  useEffect(() => {
    loadTasks(1);
  }, [loadTasks]);

  // Handle Create Task
  const handleCreateTask = async (taskPayload) => {
    setCreateSubmitting(true);
    setCreateError("");
    try {
      const created = await createTask(token, taskPayload);
      setSuccess(`Task "${created.title}" created successfully.`);
      setIsCreateOpen(false);
      loadTasks(1);
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setCreateError(err.message || "Failed to create task.");
      }
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Handle Edit Task
  const handleEditTask = async (taskPayload) => {
    if (!selectedEditTask) return;
    setEditSubmitting(true);
    setEditError("");
    try {
      const updated = await updateTaskMetadata(token, selectedEditTask.id, taskPayload);
      setTasks((prev) => prev.map((t) => (t.id === selectedEditTask.id ? updated : t)));
      if (selectedTask && selectedTask.id === selectedEditTask.id) {
        setSelectedTask(updated);
      }
      setSuccess(`Task "${updated.title}" updated successfully.`);
      setIsEditOpen(false);
      setSelectedEditTask(null);
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setEditError(err.message || "Failed to update task.");
      }
    } finally {
      setEditSubmitting(false);
    }
  };

  // Handle Assignee Change
  const handleAssigneeChange = async (taskId, newAssigneeId) => {
    setError("");
    setSuccess("");
    try {
      const updated = await updateTaskAssignment(
        token,
        taskId,
        newAssigneeId ? newAssigneeId : null
      );
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      if (selectedTask && selectedTask.id === taskId) {
        setSelectedTask(updated);
      }
      setSuccess("Task assignment updated successfully.");
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setError(err.message || "Failed to update task assignment.");
      }
    }
  };

  // Handle Opening Resolve Blocker Modal
  const handleOpenResolveModal = (task, blocker) => {
    setSelectedBlockerTask(task);
    setSelectedBlocker(blocker);
    setResolveBlockerError("");
    setIsResolveBlockerOpen(true);
  };

  // Handle Submit Resolve Blocker
  const handleResolveBlockerSubmit = async (taskId, blockerId, resolutionNote) => {
    setResolveBlockerSubmitting(true);
    setResolveBlockerError("");
    try {
      const updated = await resolveTaskBlocker(token, taskId, blockerId, resolutionNote);
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      if (selectedTask && selectedTask.id === taskId) {
        setSelectedTask(updated);
      }
      setSuccess("Blocker resolved. Task status updated.");
      setIsResolveBlockerOpen(false);
      setSelectedBlocker(null);
      setSelectedBlockerTask(null);
    } catch (err) {
      if (err.status === 401) {
        onSessionExpired();
      } else {
        setResolveBlockerError(err.message || "Failed to resolve blocker.");
      }
    } finally {
      setResolveBlockerSubmitting(false);
    }
  };

  // Summary Metrics
  const metrics = {
    total: pagination.total,
    inProgress: tasks.filter((t) => t.status === "in_progress").length,
    blocked: tasks.filter((t) => t.status === "blocked").length,
    completed: tasks.filter((t) => t.status === "completed").length,
  };

  if (managedTeams.length === 0) {
    return (
      <Card id="manager-task-board-section">
        <CardContent className="p-6">
          <EmptyState
            title="No Managed Teams Assigned"
            description="You must be assigned as manager to at least one active team to create and govern team tasks."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 font-bold text-sm shrink-0">
            📊
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Total Team Tasks
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
              Blocked Tasks
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

      {/* Main Task Governance Card */}
      <Card id="manager-tasks-section">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <CardTitle>Team Task Governance</CardTitle>
            <CardDescription>
              Create deliverables, allocate tasks to team members, monitor execution, and resolve blockers.
            </CardDescription>
          </div>

          <div className="flex items-center gap-2">
            <Button
              id="open-create-task-btn"
              variant="primary"
              size="sm"
              onClick={() => {
                setCreateError("");
                setIsCreateOpen(true);
              }}
            >
              + Create Task
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadTasks(pagination.page)}
              disabled={loading}
            >
              {loading ? "Refreshing..." : "Refresh Tasks"}
            </Button>
          </div>
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
            teamId={selectedTeamId}
            onTeamChange={setSelectedTeamId}
            teams={managedTeams}
            onReset={() => {
              setSelectedTeamId("");
              setStatusFilter("");
              setPriorityFilter("");
            }}
            loading={loading}
          />

          {/* Tasks Grid */}
          {loading ? (
            <div className="space-y-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : tasks.length === 0 ? (
            <EmptyState
              title="No Team Tasks Established"
              description={
                statusFilter || priorityFilter || selectedTeamId
                  ? "No tasks match the active filters. Try resetting the filters."
                  : "No tasks have been created for your managed teams yet. Click '+ Create Task' to establish a work item."
              }
              action={
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setIsCreateOpen(true)}
                >
                  Create First Task
                </Button>
              }
            />
          ) : (
            <div className="space-y-3">
              {tasks.map((task) => {
                const team = teamMap[task.team_id];
                const teamMembers = team?.members || [];
                const latestProgress =
                  task.progress_history && task.progress_history.length > 0
                    ? task.progress_history[task.progress_history.length - 1].percentage
                    : task.status === "completed"
                    ? 100
                    : 0;

                const formattedDue = formatDate(task.due_date);
                const unresolvedBlockers =
                  task.blockers ? task.blockers.filter((b) => !b.is_resolved) : [];

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
                          {team && (
                            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200">
                              {team.name}
                            </span>
                          )}
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

                      {/* Right: Assignment & Actions */}
                      <div className="flex items-center gap-2 flex-wrap shrink-0 border-t md:border-t-0 pt-3 md:pt-0 border-slate-100">
                        {/* Assignee Select */}
                        <div className="flex items-center gap-1.5">
                          <label
                            htmlFor={`assign-select-${task.id}`}
                            className="text-xs font-semibold text-slate-500"
                          >
                            Assignee:
                          </label>
                          <select
                            id={`assign-select-${task.id}`}
                            value={task.assigned_to || ""}
                            onChange={(e) => handleAssigneeChange(task.id, e.target.value)}
                            className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                          >
                            <option value="">Unassigned</option>
                            {teamMembers.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Resolve Blockers (if any) */}
                        {unresolvedBlockers.length > 0 && (
                          <Button
                            variant="dangerOutline"
                            size="sm"
                            onClick={() => handleOpenResolveModal(task, unresolvedBlockers[0])}
                            className="text-xs bg-rose-50 text-rose-700 hover:bg-rose-100 border-rose-300"
                          >
                            Resolve Blocker ({unresolvedBlockers.length})
                          </Button>
                        )}

                        {/* Edit Task Action */}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSelectedEditTask(task);
                            setEditError("");
                            setIsEditOpen(true);
                          }}
                          className="text-xs"
                          aria-label={`Edit task ${task.title}`}
                        >
                          Edit
                        </Button>

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
              <span>Total Managed Tasks: {pagination.total}</span>
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

      {/* Create Task Modal */}
      <TaskFormModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreateTask}
        managedTeams={managedTeams}
        isSubmitting={createSubmitting}
        error={createError}
      />

      {/* Edit Task Modal */}
      <TaskFormModal
        isOpen={isEditOpen}
        onClose={() => {
          setIsEditOpen(false);
          setSelectedEditTask(null);
        }}
        onSubmit={handleEditTask}
        managedTeams={managedTeams}
        task={selectedEditTask}
        isSubmitting={editSubmitting}
        error={editError}
      />

      {/* Task Details Modal */}
      <TaskDetailsModal
        task={selectedTask}
        isOpen={isDetailsOpen}
        onClose={() => {
          setIsDetailsOpen(false);
          setSelectedTask(null);
        }}
        isManager={true}
        onResolveBlocker={(blocker) => handleOpenResolveModal(selectedTask, blocker)}
        assigneeName={
          selectedTask && selectedTask.assigned_to
            ? teamMap[selectedTask.team_id]?.members?.find(
                (m) => m.id === selectedTask.assigned_to
              )?.name || selectedTask.assigned_to_name || null
            : null
        }
        assigneeEmail={
          selectedTask && selectedTask.assigned_to
            ? teamMap[selectedTask.team_id]?.members?.find(
                (m) => m.id === selectedTask.assigned_to
              )?.email || selectedTask.assigned_to_email || null
            : null
        }
        teamName={selectedTask ? teamMap[selectedTask.team_id]?.name || selectedTask.team_name : null}
      />

      {/* Resolve Blocker Modal */}
      <ResolveBlockerModal
        isOpen={isResolveBlockerOpen}
        onClose={() => {
          setIsResolveBlockerOpen(false);
          setSelectedBlocker(null);
          setSelectedBlockerTask(null);
        }}
        onSubmit={handleResolveBlockerSubmit}
        task={selectedBlockerTask}
        blocker={selectedBlocker}
        isSubmitting={resolveBlockerSubmitting}
        error={resolveBlockerError}
      />
    </div>
  );
}
