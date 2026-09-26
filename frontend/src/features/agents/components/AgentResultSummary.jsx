import { sanitizePublicValue } from "../publicProse";
import React, { useState } from "react";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import ConfidenceIndicator from "./ConfidenceIndicator";
import SpecialistFindingCard from "./SpecialistFindingCard";
import RecommendedActions from "./RecommendedActions";
import AgentLimitations from "./AgentLimitations";
import TaskAssignmentDetailsView from "./TaskAssignmentDetailsView";
import { INTENT_DISPLAY_LABELS } from "../agentsApi";

const SPECIALIST_LABELS = {
  coordinator: "Coordinator",
  productivity: "Productivity Specialist",
  collaboration: "Collaboration Specialist",
  wellbeing: "Well-Being Specialist",
  task_assigning: "Task Assignment Specialist",
  task_assignment: "Task Assignment Specialist",
};

function formatErrorItem(err) {
  if (!err) return "Unspecified execution error";
  if (typeof err === "string") return err;
  if (typeof err === "object") {
    const rawAgent = err.agent && err.agent !== "unknown" ? String(err.agent).toLowerCase() : "";
    const friendlyAgent = rawAgent
      ? (SPECIALIST_LABELS[rawAgent] || "Unavailable specialist")
      : "";
    const agentPrefix = friendlyAgent ? `${friendlyAgent}: ` : "";
    // Render only the safe backend message. Keep error_code strictly unavailable in UI.
    const msg = err.message || "Specialist execution error";
    return `${agentPrefix}${msg}`;
  }
  return "Specialist execution error";
}

export default function AgentResultSummary({
  result,
  onRetry = null,
  className = "",
}) {
  const [copied, setCopied] = useState(false);

  if (!result) return null;
  result = sanitizePublicValue(result);

  const {
    correlation_id,
    status = "completed",
    summary = "Analysis execution finished.",
    findings = [],
    task_assignment_details = result.task_assignment_details ||
      (findings || []).find((f) => f?.task_assignment_details)?.task_assignment_details ||
      null,
    recommended_actions = [],
    limitations = [],
    errors = [],
    safe_error_message = null,
    executed_at,
    detected_intent = result.detected_intent || null,
    routing_confidence = null,
    consulted_specialists = [],
  } = result;

  // Canonical backend schema uses result.confidence only (no legacy fallback)
  const confidenceScore = result.confidence;
  const publicSummary = task_assignment_details
    ? `Task assignment review for ${task_assignment_details.task_title}. Advisory only; manager approval and capacity confirmation are required.`
    : summary;

  const isPartial = status === "partial";
  const isFailed = status === "failed";

  const statusBadges = {
    completed: { variant: "available", label: "Completed", text: "text-emerald-800" },
    partial: { variant: "busy", label: "Partial Result", text: "text-amber-800" },
    failed: { variant: "danger", label: "Failed", text: "text-rose-800" },
  };

  const statusConfig = statusBadges[status] || statusBadges.completed;

  const copyPublicSummary = async () => {
    if (!correlation_id) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(publicSummary);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // Fallback silent handle if clipboard API is restricted
    }
  };

  let formattedDate = "Recently executed";
  try {
    if (executed_at) {
      const parsedDate = new Date(executed_at);
      if (!isNaN(parsedDate.getTime())) {
        formattedDate = parsedDate.toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        });
      }
    }
  } catch {
    formattedDate = "Recently executed";
  }

  return (
    <div
      className={`space-y-6 ${className}`}
      data-testid="agent-result-summary"
      aria-label="Workforce Analysis Results"
    >
      {/* Result Header Card */}
      <div className="p-5 sm:p-6 rounded-xl bg-white border border-slate-200/90 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <Badge variant={statusConfig.variant} size="md" dot>
              {statusConfig.label}
            </Badge>
            <span className="text-xs text-slate-500 font-medium">
              Executed {formattedDate}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <ConfidenceIndicator score={confidenceScore} size="md" />

            {/* Correlation ID Pill with Copy Action */}
            {correlation_id && (
              <button
                type="button"
                onClick={copyPublicSummary}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-mono transition-colors"
                title="Copy public analysis summary"
                aria-label="Copy public analysis summary"
              >
                <span className="truncate max-w-[120px] sm:max-w-[160px]">
                  Copy summary
                </span>
                <svg className="w-3.5 h-3.5 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {copied ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  )}
                </svg>
                {copied && <span className="text-[10px] text-emerald-600 font-sans font-bold">Copied</span>}
              </button>
            )}
          </div>
        </div>

        {/* Detected Analysis & Routing Provenance */}
        {(detected_intent || consulted_specialists.length > 0) && (
          <div
            className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg bg-slate-50 border border-slate-200/80 text-xs"
            data-testid="routing-provenance-panel"
          >
            <div className="flex flex-wrap items-center gap-2">
              {detected_intent && (
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-slate-500 uppercase tracking-wider text-[11px]">
                    Detected Analysis:
                  </span>
                  <span className="px-2 py-0.5 rounded bg-blue-50 border border-blue-200 text-blue-800 font-semibold text-xs">
                    {INTENT_DISPLAY_LABELS[detected_intent] || "Unknown analysis"}
                  </span>
                </div>
              )}

              {routing_confidence !== null && routing_confidence !== undefined && (
                <div className="flex items-center gap-1 text-slate-600 font-medium">
                  <span className="text-slate-300">|</span>
                  <span>{Math.round(routing_confidence * 100)}% routing confidence</span>
                </div>
              )}
            </div>

            {consulted_specialists.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-slate-500 font-medium text-[11px] uppercase tracking-wider">
                  Consulted Specialists:
                </span>
                <div className="flex flex-wrap gap-1">
                  {consulted_specialists.map((spec, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700 font-medium text-[11px]"
                    >
                      {SPECIALIST_LABELS[spec] || "Unavailable specialist"}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Executive Summary */}
        {!task_assignment_details && <div className="space-y-1.5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Executive Synthesis
          </h4>
          <p className="text-sm sm:text-base text-slate-900 leading-relaxed font-normal whitespace-pre-line break-words">
            {summary}
          </p>
        </div>}

        {/* Partial Results Warning Panel */}
        {(isPartial || isFailed) && (
          <div
            className={`p-4 rounded-lg border text-xs space-y-2 ${
              isFailed
                ? "bg-rose-50 border-rose-200 text-rose-950"
                : "bg-amber-50 border-amber-200/90 text-amber-950"
            }`}
            role="alert"
          >
            <div
              className={`flex items-center gap-2 font-bold ${
                isFailed ? "text-rose-900" : "text-amber-900"
              }`}
            >
              <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>{isFailed ? "Workflow Execution Failed" : "Partial Multi-Agent Analysis"}</span>
            </div>

            {safe_error_message && (
              <p className="font-medium text-slate-800 leading-relaxed">
                {safe_error_message}
              </p>
            )}

            {!safe_error_message && (
              <p className="text-slate-700 leading-relaxed">
                {isFailed
                  ? "The agent coordinator encountered an unrecoverable condition while processing telemetry."
                  : "Some specialist findings were unavailable due to missing telemetry or upstream provider limits. Available domain findings are presented below."}
              </p>
            )}

            {errors && errors.length > 0 && (
              <ul className="list-disc list-inside space-y-1 text-slate-700 pt-1">
                {errors.map((err, idx) => (
                  <li key={idx} className="break-words">
                    {formatErrorItem(err)}
                  </li>
                ))}
              </ul>
            )}

            {onRetry && (
              <div className="pt-2">
                <Button variant={isFailed ? "primary" : "secondary"} size="sm" onClick={onRetry}>
                  {isFailed ? "Retry Analysis" : "Retry Incomplete Analysis"}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Overall Advisory Actions */}
        {recommended_actions && recommended_actions.length > 0 && (
          <div className="pt-2">
            <RecommendedActions
              actions={recommended_actions}
              title="Overall Coordinator Advisory Recommendations"
            />
          </div>
        )}

        {/* Overall Coordinator Limitations */}
        {limitations && limitations.length > 0 && (
          <div className="pt-2">
            <AgentLimitations
              limitations={limitations}
              title="Overall Workforce Scope & Data Constraints"
            />
          </div>
        )}
      </div>

      {/* Task Assignment Structured Candidate Details (Rendered when present) */}
      {task_assignment_details && (
        <TaskAssignmentDetailsView details={task_assignment_details} />
      )}

      {/* Specialist Findings Section */}
      {(() => {
        const specialistFindings = (findings || []).filter(
          (f) => f && f.agent !== "coordinator" && !(task_assignment_details && f.agent === "task_assigning")
        );
        return specialistFindings.length > 0 ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                Contributing Specialist Findings ({specialistFindings.length})
              </h3>
              <span className="text-xs text-slate-500">
                Autonomous domain telemetry evaluations
              </span>
            </div>

            <div className="grid grid-cols-1 gap-4">
              {specialistFindings.map((finding, index) => (
                <SpecialistFindingCard key={index} finding={finding} />
              ))}
            </div>
          </div>
        ) : isFailed ? (
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-500 text-center">
            No individual specialist findings were generated due to the execution failure.
          </div>
        ) : null;
      })()}
    </div>
  );
}
