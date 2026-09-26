import React from "react";

export default function AgentLimitations({
  limitations = [],
  title = "Analysis Scope & Data Boundaries",
  className = "",
}) {
  if (!limitations || limitations.length === 0) {
    return null;
  }

  return (
    <div
      className={`p-3.5 rounded-lg bg-amber-50/70 border border-amber-200/80 text-amber-900 ${className}`}
      role="region"
      aria-label={title}
    >
      <div className="flex items-center gap-2 mb-2">
        <svg
          className="w-4 h-4 text-amber-700 shrink-0"
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
        <span className="text-xs font-bold uppercase tracking-wider text-amber-800">
          {title}
        </span>
      </div>

      <ul className="space-y-1.5 text-xs text-amber-900/90 leading-relaxed pl-1 list-disc list-inside">
        {limitations.map((limitation, index) => (
          <li key={index} className="break-words">
            <span>{String(limitation)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
