import { sanitizePublicValue } from "../publicProse";
import React from "react";
import Badge from "../../../components/ui/Badge";
import ConfidenceIndicator from "./ConfidenceIndicator";
import RecommendedActions from "./RecommendedActions";
import AgentLimitations from "./AgentLimitations";

const SPECIALIST_CONFIG = {
  productivity: {
    label: "Productivity Specialist",
    badgeVariant: "employee",
    badgeText: "Productivity",
    icon: (
      <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
  },
  collaboration: {
    label: "Collaboration Specialist",
    badgeVariant: "available",
    badgeText: "Collaboration",
    icon: (
      <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
  },
  wellbeing: {
    label: "Well-being Specialist",
    badgeVariant: "info",
    badgeText: "Team Well-being",
    icon: (
      <svg className="w-4 h-4 text-cyan-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
      </svg>
    ),
  },
  task_assigning: {
    label: "Task Assignment Specialist",
    badgeVariant: "manager",
    badgeText: "Task Assignment",
    icon: (
      <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
};

function formatSpecialistKey(key) {
  if (!key) return "Specialist";
  const normalized = key.toLowerCase().replace(/_/g, " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export default function SpecialistFindingCard({ finding, className = "" }) {
  if (!finding) return null;
  finding = sanitizePublicValue(finding);

  // Canonical backend schema uses finding.agent only (no legacy fallback)
  const rawAgent = finding.agent || "";
  const key = rawAgent.toLowerCase();
  const isKnown = Boolean(SPECIALIST_CONFIG[key]);
  const config = isKnown
    ? SPECIALIST_CONFIG[key]
    : {
        label: "Unavailable specialist",
        badgeVariant: "slate",
        badgeText: "Unavailable specialist",
        icon: (
          <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        ),
      };

  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm space-y-4 hover:border-slate-300 transition-colors ${className}`}
      data-testid={isKnown ? `specialist-finding-${key}` : "specialist-finding-unknown"}
    >
      {/* Specialist Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-slate-50 border border-slate-200/80">
            {config.icon}
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-900 tracking-tight">
              {config.label}
            </h4>
            <span className="text-[11px] text-slate-500 font-medium">
              Domain Analysis
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ConfidenceIndicator score={finding.confidence} size="sm" />
          <Badge variant={config.badgeVariant} size="sm">
            {config.badgeText}
          </Badge>
        </div>
      </div>

      {/* Summary Narrative */}
      <div>
        <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1.5">
          Findings Summary
        </h5>
        <p className="text-sm text-slate-800 leading-relaxed break-words whitespace-pre-line">
          {finding.summary || "No specific summary provided for this specialist."}
        </p>
      </div>

      {/* Recommended Advisory Actions */}
      {finding.recommended_actions && finding.recommended_actions.length > 0 && (
        <RecommendedActions
          actions={finding.recommended_actions}
          title={`Advisory Actions (${config.badgeText})`}
        />
      )}

      {/* Limitations / Data Boundaries */}
      {finding.limitations && finding.limitations.length > 0 && (
        <AgentLimitations
          limitations={finding.limitations}
          title={`Specialist Boundaries (${config.badgeText})`}
        />
      )}
    </div>
  );
}
