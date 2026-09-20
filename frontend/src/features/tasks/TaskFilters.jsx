import React from "react";
import Button from "../../components/ui/Button";

export default function TaskFilters({
  status,
  onStatusChange,
  priority,
  onPriorityChange,
  teamId,
  onTeamChange,
  teams = [],
  onReset,
  loading = false,
  className = "",
}) {
  const hasActiveFilters = Boolean(status || priority || (teamId && teams.length > 0));

  return (
    <div
      className={`p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex flex-wrap items-center justify-between gap-3 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        {/* Team Filter (if teams provided) */}
        {teams.length > 0 && onTeamChange && (
          <div className="flex items-center gap-1.5">
            <label htmlFor="task-filter-team" className="text-xs font-semibold text-slate-500">
              Team:
            </label>
            <select
              id="task-filter-team"
              value={teamId || ""}
              onChange={(e) => onTeamChange(e.target.value)}
              disabled={loading}
              className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            >
              <option value="">All Managed Teams</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Status Filter */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="task-filter-status" className="text-xs font-semibold text-slate-500">
            Status:
          </label>
          <select
            id="task-filter-status"
            value={status || ""}
            onChange={(e) => onStatusChange(e.target.value)}
            disabled={loading}
            className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            <option value="">All Statuses</option>
            <option value="todo">To Do</option>
            <option value="in_progress">In Progress</option>
            <option value="blocked">Blocked</option>
            <option value="completed">Completed</option>
          </select>
        </div>

        {/* Priority Filter */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="task-filter-priority" className="text-xs font-semibold text-slate-500">
            Priority:
          </label>
          <select
            id="task-filter-priority"
            value={priority || ""}
            onChange={(e) => onPriorityChange(e.target.value)}
            disabled={loading}
            className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            <option value="">All Priorities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
        </div>
      </div>

      {/* Reset Action */}
      {hasActiveFilters && (
        <Button
          variant="outline"
          size="sm"
          onClick={onReset}
          disabled={loading}
          className="text-slate-600 hover:text-slate-900 text-xs"
        >
          Reset Filters
        </Button>
      )}
    </div>
  );
}
