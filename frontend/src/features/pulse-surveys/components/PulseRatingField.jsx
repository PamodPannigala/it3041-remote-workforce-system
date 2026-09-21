import React from "react";

const RATING_LABELS = {
  1: "1 - Low",
  2: "2 - Fair",
  3: "3 - Moderate",
  4: "4 - Good",
  5: "5 - Excellent",
};

export default function PulseRatingField({
  id,
  label,
  description,
  value,
  onChange,
  disabled = false,
  required = true,
  lowLabel = "Low / Challenging",
  highLabel = "High / Thriving",
}) {
  const options = [1, 2, 3, 4, 5];

  return (
    <div className="space-y-2.5 p-4 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:border-slate-300 transition-colors">
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
        <label
          id={`${id}-label`}
          className="text-sm font-bold text-slate-900 font-heading flex items-center gap-1.5"
        >
          <span>{label}</span>
          {required && <span className="text-rose-500 font-bold" aria-hidden="true">*</span>}
        </label>
        {value ? (
          <span className="text-xs font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-100">
            Selected: {RATING_LABELS[value] || `${value}/5`}
          </span>
        ) : (
          <span className="text-xs text-slate-400 italic">Not selected</span>
        )}
      </div>

      {description && (
        <p className="text-xs text-slate-500 leading-relaxed">
          {description}
        </p>
      )}

      {/* 1-5 Button Segment Selector */}
      <div
        role="radiogroup"
        aria-labelledby={`${id}-label`}
        aria-required={required}
        className="grid grid-cols-5 gap-2 pt-1"
      >
        {options.map((score) => {
          const isSelected = value === score;
          return (
            <button
              key={score}
              type="button"
              id={`${id}-option-${score}`}
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => onChange(score)}
              className={`flex flex-col items-center justify-center py-2.5 px-2 rounded-xl text-sm font-bold transition-all duration-150 border focus:outline-none focus:ring-2 focus:ring-blue-500/40 ${
                isSelected
                  ? "bg-blue-600 border-blue-600 text-white shadow-md shadow-blue-500/25 scale-[1.02]"
                  : "bg-white border-slate-200 text-slate-700 hover:border-blue-300 hover:bg-blue-50/50 hover:text-blue-700"
              } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
            >
              <span className="text-base font-extrabold">{score}</span>
              <span className="text-[10px] font-medium tracking-tight mt-0.5 opacity-90 hidden sm:inline">
                {score === 1 ? "Poor" : score === 2 ? "Fair" : score === 3 ? "Mod" : score === 4 ? "Good" : "Great"}
              </span>
            </button>
          );
        })}
      </div>

      {/* Scale Guide Labels */}
      <div className="flex items-center justify-between text-[11px] text-slate-500 px-0.5 pt-0.5 font-medium">
        <span className="flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-slate-400" />
          1 = {lowLabel}
        </span>
        <span className="flex items-center gap-1 text-right">
          5 = {highLabel}
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500" />
        </span>
      </div>
    </div>
  );
}
