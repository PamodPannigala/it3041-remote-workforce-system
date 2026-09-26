import React from "react";

export default function ConfidenceIndicator({
  score,
  label = "Evidence confidence",
  size = "md",
  className = "",
  showBar = true,
}) {
  if (score === undefined || score === null || isNaN(score)) {
    return (
      <span className={`inline-flex items-center text-xs text-slate-500 font-medium ${className}`}>
        {label}: Not specified
      </span>
    );
  }

  // Normalize score between 0 and 1
  const normalized = Math.max(0, Math.min(1, Number(score)));
  const percentage = Math.round(normalized * 100);

  // Confidence category with accessible text description
  let level = "Low";
  let textColor = "text-rose-700";
  let barColor = "bg-rose-500";
  let badgeBg = "bg-rose-50 border-rose-200";

  if (percentage >= 80) {
    level = "High";
    textColor = "text-emerald-700";
    barColor = "bg-emerald-500";
    badgeBg = "bg-emerald-50 border-emerald-200";
  } else if (percentage >= 50) {
    level = "Moderate";
    textColor = "text-amber-800";
    barColor = "bg-amber-500";
    badgeBg = "bg-amber-50 border-amber-200";
  }

  return (
    <div
      className={`inline-flex items-center gap-2 ${className}`}
      role="meter"
      aria-label={`${label}: ${percentage}% (${level})`}
      aria-valuenow={percentage}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span className="text-xs text-slate-500 font-medium">{label}</span>
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-semibold ${badgeBg} ${textColor}`}
      >
        <span className="font-mono">{percentage}%</span>
        <span className="text-[11px] font-medium uppercase tracking-wider">({level})</span>
      </span>

      {showBar && (
        <div
          className={`bg-slate-200 rounded-full overflow-hidden shrink-0 ${
            size === "sm" ? "w-12 h-1.5" : "w-16 h-2"
          }`}
          aria-hidden="true"
        >
          <div
            className={`h-full transition-all duration-300 rounded-full ${barColor}`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      )}
    </div>
  );
}
