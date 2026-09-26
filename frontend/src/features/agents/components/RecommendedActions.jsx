import React from "react";

export default function RecommendedActions({
  actions = [],
  title = "Recommended Advisory Actions",
  className = "",
}) {
  if (!actions || actions.length === 0) {
    return null;
  }

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex items-center gap-2">
        <svg
          className="w-4 h-4 text-blue-600 shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
          />
        </svg>
        <h5 className="text-xs font-bold uppercase tracking-wider text-slate-700">
          {title}
        </h5>
      </div>

      <ol className="space-y-2 list-none p-0 m-0" aria-label={title}>
        {actions.map((action, index) => (
          <li
            key={index}
            className="flex items-start gap-3 p-3 rounded-lg bg-slate-50/80 border border-slate-200/70 text-sm text-slate-800 leading-relaxed shadow-sm"
          >
            <span
              className="flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 text-blue-800 text-xs font-bold shrink-0 mt-0.5"
              aria-hidden="true"
            >
              {index + 1}
            </span>
            <span className="flex-1 break-words">{String(action)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
