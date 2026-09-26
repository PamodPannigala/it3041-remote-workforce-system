import { sanitizePublicText } from "../publicProse";
import React, { useState, useEffect } from "react";
import Button from "../../../components/ui/Button";

const EXAMPLE_QUERIES = [
  "Why are our sprint tasks being delayed?",
  "Where is the team experiencing collaboration blockers?",
  "How do task capacity and anonymous well-being compare?",
  "Summarize anonymous well-being trends for the last four weeks.",
  "Who is a suitable candidate for this task based on skills and workload?",
  "Give me a broad workforce overview for this team.",
];

export default function AgentRequestForm({
  question = "",
  onQuestionChange,
  targetTeamId = "",
  onTargetTeamIdChange,
  targetTaskId = "",
  onTargetTaskIdChange,
  weeksLookback = "",
  onWeeksLookbackChange,
  teams = [],
  tasks = [],
  onSubmit,
  loading = false,
  onCancel = null,
  clarification = null,
  className = "",
}) {
  const [internalQuestion, setInternalQuestion] = useState(question || "");
  const [internalTeamId, setInternalTeamId] = useState(targetTeamId || "");
  const [internalTaskId, setInternalTaskId] = useState(targetTaskId || "");
  const [internalWeeks, setInternalWeeks] = useState(weeksLookback || "");
  const [errors, setErrors] = useState({});
  const [isContextExpanded, setIsContextExpanded] = useState(
    Boolean(targetTeamId || targetTaskId || weeksLookback || clarification)
  );

  const requiredContext = Array.isArray(clarification?.required_context)
    ? clarification.required_context
    : [];
  const isTeamRequired = true;
  const isTaskRequired = requiredContext.includes("target_task_id");
  const isWeeksRequired = requiredContext.includes("weeks_lookback");

  // Sync with controlled props if provided
  useEffect(() => {
    if (question !== undefined && question !== internalQuestion) {
      setInternalQuestion(question);
    }
  }, [question]);

  useEffect(() => {
    if (targetTeamId !== undefined && targetTeamId !== internalTeamId) {
      setInternalTeamId(targetTeamId);
    }
  }, [targetTeamId]);

  useEffect(() => {
    if (targetTaskId !== undefined && targetTaskId !== internalTaskId) {
      setInternalTaskId(targetTaskId);
    }
  }, [targetTaskId]);

  useEffect(() => {
    if (weeksLookback !== undefined && weeksLookback !== internalWeeks) {
      setInternalWeeks(weeksLookback);
    }
  }, [weeksLookback]);

  // If a clarification is received, auto-expand context section
  useEffect(() => {
    if (clarification) {
      setIsContextExpanded(true);
    }
  }, [clarification]);

  // Filter tasks based on selected team scope
  const activeTeamId = onTargetTeamIdChange ? targetTeamId : internalTeamId;
  const scopedTasks = activeTeamId
    ? tasks.filter((t) => String(t.team_id) === String(activeTeamId))
    : tasks;

  const handleQuestionChange = (newVal) => {
    setInternalQuestion(newVal);
    if (onQuestionChange) onQuestionChange(newVal);
    if (errors.question) setErrors((prev) => ({ ...prev, question: null }));
  };

  const handleTeamChange = (newTeamId) => {
    setInternalTeamId(newTeamId);
    if (onTargetTeamIdChange) onTargetTeamIdChange(newTeamId);
    if (errors.targetTeamId) setErrors((prev) => ({ ...prev, targetTeamId: null }));

    // Changing target team always clears targetTaskId
    setInternalTaskId("");
    if (onTargetTaskIdChange) onTargetTaskIdChange("");
  };

  const handleTaskChange = (newTaskId) => {
    setInternalTaskId(newTaskId);
    if (onTargetTaskIdChange) onTargetTaskIdChange(newTaskId);
    if (errors.targetTaskId) setErrors((prev) => ({ ...prev, targetTaskId: null }));
  };

  const handleWeeksChange = (newWeeks) => {
    setInternalWeeks(newWeeks);
    if (onWeeksLookbackChange) onWeeksLookbackChange(newWeeks);
    if (errors.weeksLookback) setErrors((prev) => ({ ...prev, weeksLookback: null }));
  };

  const handleExampleChipClick = (example) => {
    handleQuestionChange(example);
    // Clearing stale target_task_id unless the selected inquiry is the Task Assignment example
    const isTaskAssignmentExample =
      example.toLowerCase().includes("suitable candidate") ||
      example.toLowerCase().includes("for this task");
    if (!isTaskAssignmentExample) {
      setInternalTaskId("");
      if (onTargetTaskIdChange) onTargetTaskIdChange("");
    }
  };

  const validate = () => {
    const newErrors = {};
    const activeQuestion = onQuestionChange ? question : internalQuestion;
    const trimmed = (activeQuestion || "").trim();

    if (!trimmed) {
      newErrors.question = "Please enter a workforce question.";
    } else if (trimmed.length > 2000) {
      newErrors.question = "Question cannot exceed 2000 characters.";
    }

    const activeTeam = onTargetTeamIdChange ? targetTeamId : internalTeamId;
    if (requiredContext.includes("target_team_id") && !(activeTeam || "").trim()) {
      newErrors.targetTeamId = "Please select the team you want analysed.";
    }

    const activeTask = onTargetTaskIdChange ? targetTaskId : internalTaskId;
    if (isTaskRequired && !(activeTask || "").trim()) {
      newErrors.targetTaskId = "Please select the task you want evaluated.";
    }

    const activeWeeks = onWeeksLookbackChange ? weeksLookback : internalWeeks;
    if (isWeeksRequired && !(activeWeeks || "").toString().trim()) {
      newErrors.weeksLookback = "Please select an analysis period between 1 and 12 weeks.";
    } else if (activeWeeks !== "" && activeWeeks !== null && activeWeeks !== undefined) {
      const parsed = parseInt(activeWeeks, 10);
      if (isNaN(parsed) || parsed < 1 || parsed > 12) {
        newErrors.weeksLookback = "Lookback period must be between 1 and 12 weeks.";
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (loading) return;

    if (!validate()) return;

    const activeQuestion = (onQuestionChange ? question : internalQuestion).trim();
    const activeTeam = (onTargetTeamIdChange ? targetTeamId : internalTeamId).trim();
    const activeTask = (onTargetTaskIdChange ? targetTaskId : internalTaskId).trim();
    const activeWeeksVal = onWeeksLookbackChange ? weeksLookback : internalWeeks;

    const payload = {
      question: activeQuestion,
    };

    if (activeTeam) {
      payload.target_team_id = activeTeam;
    }

    if (activeTask) {
      payload.target_task_id = activeTask;
    }

    if (activeWeeksVal !== "" && activeWeeksVal !== null && activeWeeksVal !== undefined) {
      const parsed = parseInt(activeWeeksVal, 10);
      if (!isNaN(parsed) && parsed >= 1 && parsed <= 12) {
        payload.weeks_lookback = parsed;
      }
    }

    onSubmit(payload);
  };

  const currentQuestionText = onQuestionChange ? question : internalQuestion;
  const currentTeamVal = onTargetTeamIdChange ? targetTeamId : internalTeamId;
  const currentTaskVal = onTargetTaskIdChange ? targetTaskId : internalTaskId;
  const currentWeeksVal = onWeeksLookbackChange ? weeksLookback : internalWeeks;

  const charCount = (currentQuestionText || "").length;
  const isOverLimit = charCount > 2000;

  return (
    <form
      onSubmit={handleSubmit}
      className={`space-y-5 bg-white p-5 sm:p-6 rounded-xl border border-slate-200/90 shadow-sm ${className}`}
      noValidate
      data-testid="agent-request-form"
    >
      {/* Clarification Alert State */}
      {clarification && (
        <div
          className="p-4 rounded-xl bg-blue-50/80 border border-blue-200 text-blue-950 text-xs sm:text-sm space-y-2"
          role="status"
          aria-live="polite"
          data-testid="clarification-notice"
        >
          <div className="flex items-center gap-2 font-bold text-blue-900">
            <svg
              className="w-4 h-4 shrink-0 text-blue-700"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Coordinator Clarification Requested</span>
          </div>
          <p className="text-blue-900 font-medium leading-relaxed">
            {sanitizePublicText(clarification.question)}
          </p>
          <p className="text-blue-700 text-xs leading-relaxed">
            Please refine your question above or provide target context below to help the Coordinator select the right specialists.
          </p>
        </div>
      )}

      {/* Query Composer */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label
            htmlFor="agent-question-input"
            className="block text-sm font-semibold text-slate-800"
          >
            What would you like to understand? <span className="text-rose-500">*</span>
          </label>
          <span
            className={`text-xs font-mono ${
              isOverLimit ? "text-rose-600 font-bold" : "text-slate-400"
            }`}
            aria-live="polite"
          >
            {charCount}/2000
          </span>
        </div>

        <textarea
          id="agent-question-input"
          name="question"
          rows={4}
          value={currentQuestionText}
          onChange={(e) => handleQuestionChange(e.target.value)}
          disabled={loading}
          placeholder="Ask a workforce question in natural language (e.g., 'Why are our sprint tasks delayed?' or 'How is team workload distributed?')..."
          className={`w-full px-3.5 py-3 bg-white border rounded-lg text-slate-900 placeholder-slate-400 text-sm leading-relaxed transition-all focus:outline-none focus:ring-2 disabled:opacity-50 disabled:bg-slate-50 ${
            errors.question || isOverLimit
              ? "border-rose-400 focus:border-rose-500 focus:ring-rose-500/20"
              : "border-slate-300 hover:border-slate-400 focus:border-blue-600 focus:ring-blue-500/20"
          }`}
          aria-required="true"
          aria-invalid={!!errors.question || isOverLimit}
          aria-describedby={errors.question ? "agent-question-error" : undefined}
        />

        {errors.question && (
          <p id="agent-question-error" className="text-xs text-rose-600 font-medium flex items-center gap-1 mt-1">
            <svg className="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <span>{errors.question}</span>
          </p>
        )}
      </div>

      {/* Example Query Chips (suggestions only, do not select intent) */}
      <div className="space-y-2">
        <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Suggested inquiries:
        </span>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUERIES.map((example, idx) => (
            <button
              key={idx}
              type="button"
              disabled={loading}
              onClick={() => handleExampleChipClick(example)}
              className="text-left text-xs px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200/80 text-slate-700 hover:text-slate-900 transition-colors border border-slate-200/60 disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {/* Expandable Optional Context Section */}
      <div className="pt-2 border-t border-slate-100">
        <button
          type="button"
          onClick={() => setIsContextExpanded((prev) => !prev)}
          className="flex items-center justify-between w-full py-2 text-left text-xs font-semibold text-slate-700 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 rounded"
          aria-expanded={isContextExpanded}
          aria-controls="agent-optional-context-panel"
          data-testid="toggle-optional-context-btn"
        >
          <span className="flex items-center gap-1.5">
            <svg
              className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isContextExpanded ? "rotate-90" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
            </svg>
            Select team and analysis context
          </span>
          <span className="text-[11px] text-slate-400 font-normal">
            {isContextExpanded ? "Hide context parameters" : "Team, task, lookback scope"}
          </span>
        </button>

        {isContextExpanded && (
          <div
            id="agent-optional-context-panel"
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-3 mt-1"
          >
            {/* Team Selector */}
            <div className="space-y-1.5">
              <label
                htmlFor="agent-team-select"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
              >
                Target Team {isTeamRequired ? (
                  <span className="text-rose-600 font-bold lowercase">* (required)</span>
                ) : (
                  <span className="text-slate-400 font-normal lowercase">(optional)</span>
                )}
              </label>
              <div className="relative">
                <select
                  id="agent-team-select"
                  name="target_team_id"
                  value={currentTeamVal}
                  onChange={(e) => handleTeamChange(e.target.value)}
                  disabled={loading || teams.length === 0}
                  aria-required={isTeamRequired ? "true" : undefined}
                  aria-invalid={!!errors.targetTeamId}
                  className={`w-full px-3.5 py-2.5 bg-white border rounded-lg text-slate-900 text-sm appearance-none pr-9 focus:outline-none focus:ring-2 disabled:opacity-50 disabled:bg-slate-50 ${
                    errors.targetTeamId
                      ? "border-rose-400 focus:border-rose-500 focus:ring-rose-500/20"
                      : "border-slate-300 hover:border-slate-400 focus:border-blue-600 focus:ring-blue-500/20"
                  }`}
                >
                  <option value="">
                    {teams.length === 0 ? "No teams available" : "Select an authorized team..."}
                  </option>
                  {teams.map((t) => {
                    const teamId = t.id || t._id;
                    return (
                      <option key={teamId} value={teamId}>
                        {sanitizePublicText(t.name, [teamId])}
                      </option>
                    );
                  })}
                </select>
                <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-400">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
              {errors.targetTeamId && (
                <p className="text-xs text-rose-600 font-medium mt-1">{errors.targetTeamId}</p>
              )}
            </div>

            {/* Task Selector (Filtered to selected team) */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="agent-task-select"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
                >
                  Target Task {isTaskRequired ? (
                    <span className="text-rose-600 font-bold lowercase">* (required)</span>
                  ) : (
                    <span className="text-slate-400 font-normal lowercase">(optional)</span>
                  )}
                </label>
                {currentTaskVal && (
                  <button
                    type="button"
                    onClick={() => {
                      setInternalTaskId("");
                      if (onTargetTaskIdChange) onTargetTaskIdChange("");
                    }}
                    className="text-[11px] font-medium text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                    data-testid="clear-task-btn"
                  >
                    Clear selected task
                  </button>
                )}
              </div>
              <div className="relative">
                <select
                  id="agent-task-select"
                  name="target_task_id"
                  value={currentTaskVal}
                  onChange={(e) => handleTaskChange(e.target.value)}
                  disabled={loading || scopedTasks.length === 0}
                  aria-required={isTaskRequired ? "true" : undefined}
                  aria-invalid={!!errors.targetTaskId}
                  className={`w-full px-3.5 py-2.5 bg-white border rounded-lg text-slate-900 text-sm appearance-none pr-9 focus:outline-none focus:ring-2 disabled:opacity-50 disabled:bg-slate-50 ${
                    errors.targetTaskId
                      ? "border-rose-400 focus:border-rose-500 focus:ring-rose-500/20"
                      : "border-slate-300 hover:border-slate-400 focus:border-blue-600 focus:ring-blue-500/20"
                  }`}
                >
                  <option value="">
                    {scopedTasks.length === 0
                      ? currentTeamVal
                        ? "No tasks found for selected team"
                        : "No tasks available"
                      : "Select a task (for assignment recommendation)..."}
                  </option>
                  {scopedTasks.map((task) => {
                    const taskId = task.id || task._id;
                    return (
                      <option key={taskId} value={taskId}>
                        {sanitizePublicText(task.title, [task.id, task._id, task.team_id].filter(Boolean))} ({sanitizePublicText(task.priority || "normal")} priority, {sanitizePublicText(task.status || "open")})
                      </option>
                    );
                  })}
                </select>
                <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-400">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
              {errors.targetTaskId && (
                <p className="text-xs text-rose-600 font-medium mt-1">{errors.targetTaskId}</p>
              )}
            </div>

            {/* Lookback Window (1-12 weeks) */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="agent-weeks-input"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
                >
                  Lookback Window {isWeeksRequired ? (
                    <span className="text-rose-600 font-bold lowercase">* (required)</span>
                  ) : (
                    <span className="text-slate-400 font-normal lowercase">(optional)</span>
                  )}
                </label>
                <span className="text-xs text-slate-500">1 to 12 weeks</span>
              </div>
              <input
                id="agent-weeks-input"
                name="weeks_lookback"
                type="number"
                min={1}
                max={12}
                placeholder="4"
                value={currentWeeksVal}
                onChange={(e) => handleWeeksChange(e.target.value)}
                disabled={loading}
                aria-required={isWeeksRequired ? "true" : undefined}
                aria-invalid={!!errors.weeksLookback}
                className={`w-full px-3.5 py-2.5 bg-white border rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 disabled:opacity-50 disabled:bg-slate-50 ${
                  errors.weeksLookback
                    ? "border-rose-400 focus:border-rose-500 focus:ring-rose-500/20"
                    : "border-slate-300 hover:border-slate-400 focus:border-blue-600 focus:ring-blue-500/20"
                }`}
              />
              {errors.weeksLookback && (
                <p className="text-xs text-rose-600 font-medium mt-1">{errors.weeksLookback}</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className="pt-3 border-t border-slate-100 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="text-xs text-slate-500">
          The Coordinator routes inquiries to specialists and grounds all findings.
        </div>

        <div className="flex items-center gap-3">
          {loading && onCancel && (
            <Button
              type="button"
              variant="outline"
              size="md"
              onClick={onCancel}
              className="text-slate-600"
            >
              Cancel
            </Button>
          )}

          {(() => {
            const isMissingRequiredContext =
              (requiredContext.includes("target_team_id") && !(currentTeamVal || "").trim()) ||
              (isTaskRequired && !(currentTaskVal || "").trim()) ||
              (isWeeksRequired && !(currentWeeksVal || "").toString().trim());

            return (
              <Button
                type="submit"
                variant="primary"
                size="md"
                loading={loading}
                disabled={
                  loading ||
                  isOverLimit ||
                  !(currentQuestionText || "").trim() ||
                  isMissingRequiredContext
                }
                className="w-full sm:w-auto min-w-[120px]"
                id="agent-submit-btn"
              >
                {loading ? "Analysing..." : "Analyse"}
              </Button>
            );
          })()}
        </div>
      </div>
    </form>
  );
}
