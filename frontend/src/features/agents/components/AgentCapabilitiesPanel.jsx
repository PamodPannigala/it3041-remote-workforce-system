import { sanitizePublicValue } from "../publicProse";
import React from "react";
import Badge from "../../../components/ui/Badge";

export default function AgentCapabilitiesPanel({
  userRole = "employee",
  capabilities = null,
  className = "",
}) {
  capabilities = sanitizePublicValue(capabilities);
  const roleLabels = {
    employee: "Employee View",
    manager: "Manager Decision Support",
    admin: "Executive Workforce Insights",
  };

  const advisoryLimits = capabilities?.advisory_limitations || [];

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Header Info Banner */}
      <div className="p-5 sm:p-6 rounded-xl bg-white border border-slate-200/80 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1.5 max-w-3xl">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-xl sm:text-2xl font-bold font-heading text-slate-900 tracking-tight">
              AI Workforce Coordinator
            </h2>
            <Badge variant={userRole} size="md">
              {roleLabels[userRole] || userRole}
            </Badge>
          </div>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Ask a workforce question in natural language. The Coordinator will identify and consult the appropriate specialists.
          </p>
        </div>

        {/* Advisory Badge */}
        <div className="shrink-0 flex items-center gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200/70 text-slate-700 text-xs">
          <svg className="w-4 h-4 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="font-semibold text-slate-800">
            Advisory Only
          </span>
          <span className="text-slate-500 hidden sm:inline">
            — Human decisions govern all outcomes
          </span>
        </div>
      </div>

      {/* Privacy & Governance Notice */}
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 flex items-start gap-3">
        <div className="text-blue-600 shrink-0 mt-0.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        </div>
        <div className="space-y-1 leading-relaxed">
          <p className="font-semibold text-slate-900">
            Privacy Thresholds & Supportive-Use Governance
          </p>
          <p className="text-slate-600">
            All analysis operates strictly within your authorized team boundaries. Well-being metrics represent aggregated, anonymized team-level trends protected by a minimum 3-response threshold to safeguard individual privacy. Findings never constitute medical assessment or individual surveillance.
          </p>
          {advisoryLimits.length > 0 && (
            <ul className="list-disc list-inside space-y-0.5 text-slate-500 pt-1 text-[11px]">
              {advisoryLimits.map((lim, idx) => (
                <li key={idx} className="break-words">{lim}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
