import React, { useState, useEffect } from "react";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";

export default function TaskFormModal({
  isOpen,
  onClose,
  onSubmit,
  managedTeams = [],
  task = null,
  isSubmitting = false,
  error = "",
}) {
  const isEditMode = Boolean(task);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [teamId, setTeamId] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [priority, setPriority] = useState("medium");
  const [estimatedHours, setEstimatedHours] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [skillInput, setSkillInput] = useState("");
  const [skills, setSkills] = useState([]);
  const [clientError, setClientError] = useState("");

  // Initialize or reset form when modal opens or task changes
  useEffect(() => {
    if (isOpen) {
      if (task) {
        setTitle(task.title || "");
        setDescription(task.description || "");
        setTeamId(task.team_id || "");
        setAssignedTo(task.assigned_to || "");
        setPriority(task.priority || "medium");
        setEstimatedHours(
          task.estimated_hours !== undefined && task.estimated_hours !== null && task.estimated_hours > 0
            ? String(task.estimated_hours)
            : ""
        );
        setDueDate(task.due_date ? task.due_date.substring(0, 10) : "");
        setSkills(task.required_skills ? [...task.required_skills] : []);
      } else {
        setTitle("");
        setDescription("");
        const defaultTeam = managedTeams.length > 0 ? managedTeams[0].id : "";
        setTeamId(defaultTeam);
        setAssignedTo("");
        setPriority("medium");
        setEstimatedHours("");
        setDueDate("");
        setSkills([]);
      }
      setSkillInput("");
      setClientError("");
    }
  }, [isOpen, task, managedTeams]);

  if (!isOpen) return null;

  // Selected team object to populate eligible team members in create mode
  const selectedTeam = managedTeams.find((t) => t.id === teamId);
  const eligibleMembers = selectedTeam?.members || [];

  const handleAddSkill = () => {
    const trimmed = skillInput.trim();
    if (!trimmed) return;
    if (trimmed.length > 50) {
      setClientError("Skill item cannot exceed 50 characters.");
      return;
    }
    const lower = trimmed.toLowerCase();
    if (!skills.some((s) => s.toLowerCase() === lower)) {
      setSkills([...skills, trimmed]);
    }
    setSkillInput("");
    setClientError("");
  };

  const handleRemoveSkill = (skillToRemove) => {
    setSkills(skills.filter((s) => s !== skillToRemove));
  };

  const handleKeyDownSkill = (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      handleAddSkill();
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setClientError("");

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setClientError("Task title is required.");
      return;
    }
    if (trimmedTitle.length > 200) {
      setClientError("Task title cannot exceed 200 characters.");
      return;
    }

    if (!isEditMode && !teamId) {
      setClientError("Please select a team for this task.");
      return;
    }

    let parsedHours = 0;
    if (estimatedHours !== "") {
      parsedHours = parseFloat(estimatedHours);
      if (isNaN(parsedHours) || parsedHours < 0 || parsedHours > 1000) {
        setClientError("Estimated hours must be a number between 0 and 1000.");
        return;
      }
    }

    let formattedDueDate = null;
    if (dueDate) {
      try {
        const d = new Date(dueDate);
        if (isNaN(d.getTime())) {
          setClientError("Please enter a valid due date.");
          return;
        }
        formattedDueDate = d.toISOString();
      } catch {
        setClientError("Invalid date format.");
        return;
      }
    }

    if (isEditMode) {
      const payload = {
        title: trimmedTitle,
        description: description.trim(),
        required_skills: skills,
        priority,
        due_date: formattedDueDate,
        estimated_hours: parsedHours,
      };
      onSubmit(payload);
    } else {
      const payload = {
        title: trimmedTitle,
        description: description.trim(),
        team_id: teamId,
        assigned_to: assignedTo ? assignedTo : null,
        required_skills: skills,
        priority,
        due_date: formattedDueDate,
        estimated_hours: parsedHours,
      };
      onSubmit(payload);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-form-modal-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={isSubmitting ? undefined : onClose}
        aria-hidden="true"
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-xl bg-white rounded-2xl shadow-2xl border border-slate-200/80 z-10 flex flex-col max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="p-5 sm:p-6 border-b border-slate-200/80 flex items-center justify-between bg-slate-50/50">
          <div>
            <h3
              id="task-form-modal-title"
              className="text-lg font-bold text-slate-900 font-heading"
            >
              {isEditMode ? "Edit Task" : "Create Team Task"}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {isEditMode
                ? "Update task metadata, requirements, priority, and schedule."
                : "Assign task deliverables and requirements to team members."}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors disabled:opacity-50"
            aria-label="Close form modal"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable Form Body */}
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="p-5 sm:p-6 space-y-4 overflow-y-auto">
            {/* Server / Client Errors */}
            {(error || clientError) && (
              <Alert variant="error" onDismiss={() => setClientError("")}>
                {clientError || error}
              </Alert>
            )}

            {/* Task Title */}
            <div className="space-y-1.5">
              <label
                htmlFor="task-title-input"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
              >
                Task Title <span className="text-rose-500">*</span>
              </label>
              <input
                id="task-title-input"
                type="text"
                required
                maxLength={200}
                placeholder="e.g., Implement authentication token refresh flow"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={isSubmitting}
                className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors disabled:bg-slate-50"
              />
            </div>

            {/* In Create mode only: Team Selection & Assignee Selection */}
            {!isEditMode && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label
                    htmlFor="task-team-select"
                    className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
                  >
                    Managed Team <span className="text-rose-500">*</span>
                  </label>
                  <select
                    id="task-team-select"
                    required
                    value={teamId}
                    onChange={(e) => {
                      setTeamId(e.target.value);
                      setAssignedTo(""); // Reset assignee when team changes
                    }}
                    disabled={isSubmitting || managedTeams.length === 0}
                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:bg-slate-50"
                  >
                    {managedTeams.length === 0 ? (
                      <option value="">No managed teams</option>
                    ) : (
                      managedTeams.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))
                    )}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label
                    htmlFor="task-assignee-select"
                    className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
                  >
                    Assign To
                  </label>
                  <select
                    id="task-assignee-select"
                    value={assignedTo}
                    onChange={(e) => setAssignedTo(e.target.value)}
                    disabled={isSubmitting || !teamId}
                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:bg-slate-50"
                  >
                    <option value="">Unassigned (Open for team)</option>
                    {eligibleMembers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.email})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* Description */}
            <div className="space-y-1.5">
              <label
                htmlFor="task-description-input"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
              >
                Description
              </label>
              <textarea
                id="task-description-input"
                rows={3}
                maxLength={2000}
                placeholder="Provide detailed instructions, deliverables, and acceptance criteria..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={isSubmitting}
                className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors disabled:bg-slate-50 resize-y"
              />
            </div>

            {/* Priority, Estimated Hours, Due Date */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <label
                  htmlFor="task-priority-select"
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
                >
                  Priority
                </label>
                <select
                  id="task-priority-select"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="task-hours-input"
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
                >
                  Est. Hours
                </label>
                <input
                  id="task-hours-input"
                  type="number"
                  step="0.5"
                  min="0"
                  max="1000"
                  placeholder="e.g., 8.0"
                  value={estimatedHours}
                  onChange={(e) => setEstimatedHours(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="task-due-date-input"
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
                >
                  Due Date
                </label>
                <input
                  id="task-due-date-input"
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
            </div>

            {/* Required Skills */}
            <div className="space-y-2">
              <label
                htmlFor="task-skill-input"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider"
              >
                Required Skills / Competencies
              </label>
              <div className="flex gap-2">
                <input
                  id="task-skill-input"
                  type="text"
                  placeholder="Type skill and press Enter..."
                  value={skillInput}
                  onChange={(e) => setSkillInput(e.target.value)}
                  onKeyDown={handleKeyDownSkill}
                  disabled={isSubmitting}
                  className="flex-1 px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleAddSkill}
                  disabled={isSubmitting || !skillInput.trim()}
                >
                  Add
                </Button>
              </div>

              {/* Skill Chips */}
              {skills.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {skills.map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="text-blue-400 hover:text-rose-600 focus:outline-none"
                        aria-label={`Remove skill ${skill}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Footer Actions */}
          <div className="p-4 sm:p-5 border-t border-slate-200/80 bg-slate-50/50 flex items-center justify-end gap-3 shrink-0">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              id={isEditMode ? "edit-task-submit-btn" : "create-task-submit-btn"}
              type="submit"
              variant="primary"
              size="sm"
              disabled={isSubmitting || (!isEditMode && managedTeams.length === 0)}
            >
              {isEditMode
                ? isSubmitting
                  ? "Saving Changes..."
                  : "Save Changes"
                : isSubmitting
                ? "Creating Task..."
                : "Create Task"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
