import { sanitizePublicValue } from "../publicProse";
import React from "react";
import Badge from "../../../components/ui/Badge";

const RECOMMENDATION_LABEL_CONFIG = {
  recommended: {
    label: "Recommended",
    badgeVariant: "available",
  },
  strong_alternative: {
    label: "Strong Alternative",
    badgeVariant: "employee",
  },
  possible_alternative: {
    label: "Possible Alternative",
    badgeVariant: "default",
  },
  capacity_review_required: {
    label: "Capacity review required",
    badgeVariant: "busy",
  },
};

const humanLabel = (value, fallback = "Not verified") => ({
  available: "Available", busy: "Busy", on_leave: "On leave", unspecified: "Not verified",
  todo: "Not started", in_progress: "In progress", blocked: "Blocked", completed: "Completed",
  low: "Low", medium: "Medium", high: "High", urgent: "Urgent",
}[value] || fallback);
const countLabel = (count, noun) => `${count} ${noun}${count === 1 ? "" : "s"}`;

export default function TaskAssignmentDetailsView({
  details,
  className = "",
}) {
  if (!details) return null;
  details = sanitizePublicValue(details);

  const {
    task_title = "Untitled Task",
    requested_candidate_count = 1,
    evaluated_candidate_count = 0,
    eligible_candidate_count = 0,
    candidate_recommendations = [],
    other_evaluated_candidates = [],
    ranking_factors = [],
  } = details;

  const hasRecommendations = candidate_recommendations.length > 0;

  return (
    <div
      className={`space-y-5 ${className}`}
      data-testid="task-assignment-details-view"
      aria-label="Task Assignment Recommendation Details"
    >
      {/* Header Panel */}
      <div className="p-5 rounded-xl bg-amber-50/70 border border-amber-200/90 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-amber-200/60">
          <div className="space-y-0.5">
            <span className="text-[11px] font-bold uppercase tracking-wider text-amber-900">
              Task Assignment Recommendation
            </span>
            <h3 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
              {task_title}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant="manager" size="md">
              Advisory only — Manager makes final decision
            </Badge>
          </div>
        </div>

        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div><dt className="text-slate-500">Priority</dt><dd className="font-semibold">{humanLabel(details.task_priority)}</dd></div>
          <div><dt className="text-slate-500">Status</dt><dd className="font-semibold">{humanLabel(details.task_status)}</dd></div>
          <div><dt className="text-slate-500">Current assignee</dt><dd>{details.current_assignee || "No verified current assignee"}</dd></div>
          <div><dt className="text-slate-500">Required skills</dt><dd>{details.required_skills?.join(", ") || "Requirements not verified"}</dd></div>
        </dl>

        {/* Count Metadata Summary */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-700 font-medium">
          <span className="px-2.5 py-1 rounded-md bg-white border border-amber-200/80 shadow-2xs">
            Requested: <strong className="text-slate-900">{requested_candidate_count}</strong>
          </span>
          <span className="px-2.5 py-1 rounded-md bg-white border border-amber-200/80 shadow-2xs">
            Eligible: <strong className="text-slate-900">{eligible_candidate_count}</strong>
          </span>
          <span className="px-2.5 py-1 rounded-md bg-white border border-amber-200/80 shadow-2xs">
            Evaluated: <strong className="text-slate-900">{evaluated_candidate_count}</strong>
          </span>
        </div>
        <p className="text-xs text-slate-600">{countLabel(evaluated_candidate_count, "candidate")} evaluated.</p>
      </div>

      {/* Recommended Candidates List */}
      {hasRecommendations ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              Recommended Candidates ({candidate_recommendations.length})
            </h4>
            <span className="text-xs text-slate-500">
              Ranked by deterministic skill coverage and workload capacity
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3.5">
            {candidate_recommendations.map((cand) => {
              const labelConfig =
                RECOMMENDATION_LABEL_CONFIG[cand.recommendation_label] ||
                RECOMMENDATION_LABEL_CONFIG.recommended;

              const pct = Math.round(cand.suitability_score * 100);
              const coveragePct = Math.round(cand.required_skill_coverage * 100);

              return (
                <div
                  key={cand.rank}
                  className="p-5 rounded-xl bg-white border border-slate-200 shadow-sm space-y-3.5 hover:border-slate-300 transition-colors"
                  data-testid={`candidate-card-rank-${cand.rank}`}
                >
                  {/* Card Header */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center justify-center w-7 h-7 rounded-full bg-slate-900 text-white font-bold text-xs">
                        #{cand.rank}
                      </span>
                      <div>
                        <h5 className="text-base font-bold text-slate-900 tracking-tight">
                          {cand.candidate_name}
                        </h5>
                        <div className="flex items-center gap-2 pt-0.5">
                          <Badge variant={labelConfig.badgeVariant} size="sm">
                            {labelConfig.label}
                          </Badge>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2.5">
                      {/* Task Suitability Score */}
                      <div className="px-3 py-1 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-900 font-semibold">
                        <span>Task suitability: </span>
                        <strong className="text-blue-950 font-bold">{pct}%</strong>
                      </div>

                      {/* Required Skill Coverage */}
                      <div className="px-3 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-900 font-medium">
                        <span>Required-skill coverage: </span>
                        <strong className="text-emerald-950 font-bold">
                          {cand.matched_required_skill_count}/{cand.required_skill_count} ({coveragePct}%)
                        </strong>
                      </div>
                    </div>
                  </div>

                  {!cand.missing_required_skills?.length && <p className="text-xs text-emerald-800">All required skills matched</p>}

                  {/* Skills Section */}
                  <div className="space-y-1.5 text-xs">
                    <span className="font-semibold text-slate-600">Verified Matched Skills:</span>
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {cand.matched_skills && cand.matched_skills.length > 0 ? (
                        cand.matched_skills.map((skill, sIdx) => (
                          <span
                            key={sIdx}
                            className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-medium text-[11px]"
                          >
                            ✓ {skill}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-500 italic">None required</span>
                      )}
                    </div>
                  </div>

                  {/* Workload Summary */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <section aria-label="Availability and capacity" className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
                      <h6 className="font-semibold">Availability and capacity</h6>
                      <p>{humanLabel(cand.availability_status)}</p>
                      <p>{Number.isFinite(cand.weekly_capacity_hours) ? `${cand.weekly_capacity_hours} hours per week recorded capacity` : "Capacity unverified"}</p>
                    </section>
                    <section aria-label="Active workload and overdue risk" className={`p-3 rounded-lg border space-y-1 ${cand.overdue_task_count > 0 ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-200"}`}>
                      <h6 className="font-semibold">Active workload and overdue risk</h6>
                      <p>{Number.isFinite(cand.active_task_count) ? `${countLabel(cand.active_task_count, "active task")}, ${cand.overdue_task_count ?? "unknown"} overdue` : "Active workload unverified"}</p>
                      {cand.overdue_task_count > 0 && <p className="font-semibold text-amber-900">Overdue work requires capacity review.</p>}
                    </section>
                  </div>

                  {/* Recommendation Rationale */}
                  <div className="text-xs space-y-1">
                    <span className="font-semibold text-slate-700">Recommendation Rationale:</span>
                    <p className="text-slate-800 leading-relaxed font-normal">
                      {cand.recommendation_reason}
                    </p>
                  </div>

                  {/* Candidate Specific Limitations / Risks */}
                  {cand.limitations && cand.limitations.length > 0 && (
                    <div className="text-xs space-y-1 pt-1 border-t border-slate-100">
                      <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px]">
                        Advisory Observations:
                      </span>
                      <ul className="list-disc list-inside space-y-0.5 text-slate-600 text-[11px]">
                        {cand.limitations.map((lim, lIdx) => (
                          <li key={lIdx}>{lim}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* Zero Eligible State */
        <div
          className="p-6 rounded-xl bg-slate-50 border border-slate-200 text-center space-y-2.5"
          data-testid="zero-eligible-notice"
        >
          <div className="w-10 h-10 mx-auto rounded-full bg-amber-100 flex items-center justify-center text-amber-700 font-bold">
            !
          </div>
          <h4 className="text-sm font-bold text-slate-800">
            No fully eligible candidate was found from the verified evidence.
          </h4>
          <p className="text-xs text-slate-600 max-w-md mx-auto leading-relaxed">
            The available evidence does not establish a fully eligible candidate.
            Review the task requirements and the candidate-specific reasons below before considering staffing options.
          </p>
        </div>
      )}

      {/* Other Evaluated Candidates (Ineligible) */}
      {other_evaluated_candidates && other_evaluated_candidates.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Other Evaluated Team Members ({other_evaluated_candidates.length})
            </h4>
            <span className="text-xs text-slate-500">Eligibility not established by verified evidence</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {other_evaluated_candidates.map((cand, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-lg bg-slate-50/80 border border-slate-200/90 text-xs space-y-2"
                data-testid={`ineligible-candidate-${idx}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-slate-800 truncate">{cand.candidate_name}</span>
                  <Badge variant="slate" size="sm">
                    Not currently eligible
                  </Badge>
                </div>

                <div className="text-[11px] text-slate-600">
                  <span>Coverage: </span>
                  <span className="font-semibold text-slate-700">
                    {cand.matched_required_skill_count}/{cand.required_skill_count} (
                    {Math.round(cand.required_skill_coverage * 100)}%)
                  </span>
                </div>

                <p className="text-[11px] text-slate-600 leading-relaxed">{cand.reason}</p>

                {cand.missing_required_skills && cand.missing_required_skills.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {cand.missing_required_skills.map((s, sIdx) => (
                      <span
                        key={sIdx}
                        className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-medium"
                      >
                        Missing: {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
