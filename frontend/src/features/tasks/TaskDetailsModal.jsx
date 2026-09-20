import React from "react";
import Button from "../../components/ui/Button";
import TaskStatusBadge from "./TaskStatusBadge";
import TaskPriorityBadge from "./TaskPriorityBadge";
import TaskProgressTimeline from "./TaskProgressTimeline";

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

export default function TaskDetailsModal({
  task,
  isOpen,
  onClose,
  isManager = false,
  onResolveBlocker = null,
  assigneeName = null,
  assigneeEmail = null,
  teamName = null,
}) {
  if (!isOpen || !task) return null;

  const latestProgress =
    task.progress_history && task.progress_history.length > 0
      ? task.progress_history[task.progress_history.length - 1].percentage
      : task.status === "completed"
      ? 100
      : 0;

  const resolvedAssigneeName =
    assigneeName || task.assigned_to_name || (task.assigned_to ? "Assigned Employee" : null);
  const resolvedAssigneeEmail = assigneeEmail || task.assigned_to_email || null;
  const isUnassigned = !task.assigned_to && !assigneeName && !task.assigned_to_name;
  const finalAssigneeName = isUnassigned ? "Unassigned" : resolvedAssigneeName;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-details-modal-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-slate-200/80 z-10 flex flex-col max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="p-5 sm:p-6 border-b border-slate-200/80 flex items-start justify-between gap-4 bg-slate-50/50">
          <div className="space-y-1.5 min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <TaskStatusBadge status={task.status} />
              <TaskPriorityBadge priority={task.priority} />
              {teamName && (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">
                  {teamName}
                </span>
              )}
            </div>
            <h3
              id="task-details-modal-title"
              className="text-lg sm:text-xl font-extrabold text-slate-900 font-heading leading-snug break-words"
            >
              {task.title}
            </h3>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
            aria-label="Close task details"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-5 sm:p-6 space-y-6 overflow-y-auto">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                Assignee
              </span>
              <p className="text-xs font-bold text-slate-900 truncate">
                {finalAssigneeName}
              </p>
              {!isUnassigned && resolvedAssigneeEmail && (
                <span className="text-[11px] text-slate-500 block truncate">
                  {resolvedAssigneeEmail}
                </span>
              )}
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                Due Date
              </span>
              <p className="text-xs font-bold text-slate-900 truncate">
                {formatDate(task.due_date)}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                Est. Hours
              </span>
              <p className="text-xs font-bold text-slate-900 truncate">
                {task.estimated_hours ? `${task.estimated_hours} hrs` : "None"}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                Progress
              </span>
              <p className="text-xs font-bold text-blue-600 font-mono truncate">
                {latestProgress}%
              </p>
            </div>
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Description
            </h4>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-800 leading-relaxed whitespace-pre-wrap break-words">
              {task.description || <span className="italic text-slate-400">No description provided.</span>}
            </div>
          </div>

          {/* Required Skills */}
          {task.required_skills && task.required_skills.length > 0 && (
            <div className="space-y-1.5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Required Competencies ({task.required_skills.length})
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {task.required_skills.map((skill, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200/80"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Progress Timeline & Blockers */}
          <div className="space-y-2 pt-2 border-t border-slate-200/80">
            <TaskProgressTimeline
              progressHistory={task.progress_history}
              blockers={task.blockers}
              onResolveBlocker={onResolveBlocker}
              isManager={isManager}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 sm:p-5 border-t border-slate-200/80 bg-slate-50/50 flex justify-end">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
